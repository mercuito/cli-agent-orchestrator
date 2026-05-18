"""Single FastAPI entry point for all HTTP routes."""

import asyncio
import fcntl
import json
import logging
import os
import pty
import signal
import struct
import subprocess
import termios
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, NoReturn, Optional

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from watchdog.observers.polling import PollingObserver

from cli_agent_orchestrator import agent as agent_config
from cli_agent_orchestrator.agent import (
    CAO_AGENTS_DIR_ENV,
    Agent,
    AgentConfigError,
    AgentPathError,
    AgentWorkspaceConfig,
    LinearConfig,
    LinearToolAccessConfig,
    configure_agents_root,
    load_agent,
    patch_agent_config,
    write_agent,
)
from cli_agent_orchestrator.clients.database import (
    TerminalAgentAlreadyRunningError,
    create_inbox_delivery,
    get_baton_record,
    get_terminal_metadata,
    init_db,
    list_baton_events,
    list_batons,
    list_inbox_deliveries,
)
from cli_agent_orchestrator.constants import (
    ALLOWED_HOSTS,
    CAO_HOME_DIR,
    CORS_ORIGINS,
    INBOX_POLLING_INTERVAL,
    SERVER_HOST,
    SERVER_PORT,
    SERVER_VERSION,
    TERMINAL_LOG_DIR,
)
from cli_agent_orchestrator.linear.routes import router as linear_router
from cli_agent_orchestrator.models.baton import Baton, BatonEvent, BatonStatus
from cli_agent_orchestrator.models.flow import Flow
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.models.terminal import Terminal, TerminalId
from cli_agent_orchestrator.providers.base import CatalogDiscoveryError
from cli_agent_orchestrator.providers.manager import provider_manager
from cli_agent_orchestrator.runtime.agent import AgentRuntimeHandle
from cli_agent_orchestrator.services import (
    baton_service,
    baton_watchdog_service,
    flow_service,
    inbox_service,
    monitoring_service,
    session_service,
    terminal_service,
)
from cli_agent_orchestrator.services.agent_manager import (
    AgentStatus,
    default_agent_manager,
)
from cli_agent_orchestrator.services.agent_timeline import (
    AgentTimelineRead,
    AgentTimelineService,
    CausationRelatedEventsRead,
    RelatedEventsRead,
    TimelineEventRead,
    UnknownTimelineEventError,
)
from cli_agent_orchestrator.services.baton_feature import is_baton_enabled
from cli_agent_orchestrator.services.cleanup_service import cleanup_old_data
from cli_agent_orchestrator.services.inbox_service import LogFileHandler
from cli_agent_orchestrator.services.terminal_service import OutputMode
from cli_agent_orchestrator.utils import monitoring_formatter
from cli_agent_orchestrator.utils.dashboard_links import (
    create_agent_dashboard_token,
    create_terminal_dashboard_token,
    validate_agent_dashboard_token,
    validate_terminal_dashboard_token,
)
from cli_agent_orchestrator.utils.logging import setup_logging
from cli_agent_orchestrator.utils.skills import (
    SkillNameError,
    load_skill_content,
    validate_skill_name,
)
from cli_agent_orchestrator.workspace_providers import (
    WorkspaceProviderConfigError,
    initialize_enabled_workspace_providers,
)
from cli_agent_orchestrator.workspace_setups import default_workspace_setup_manager

logger = logging.getLogger(__name__)


def _terminal_ws_authorized(websocket: WebSocket, terminal_id: str) -> bool:
    """Return whether a websocket may attach to a terminal."""

    client_host = websocket.client.host if websocket.client else None
    if client_host in (None, "127.0.0.1", "::1", "localhost"):
        return True

    token = websocket.query_params.get("terminal_token")
    return bool(token and validate_terminal_dashboard_token(token, terminal_id))


def _tmux_attach_environment() -> dict[str, str]:
    """Return an environment suitable for attaching tmux to the web PTY."""

    term = os.environ.get("TERM")
    if term is None or term.lower() in {"", "dumb", "unknown"}:
        term = "xterm-256color"
    return {**os.environ, "TERM": term}


def _client_is_loopback(request: Request) -> bool:
    client_host = request.client.host if request.client else None
    return client_host in (None, "127.0.0.1", "::1", "localhost")


def _agent_dashboard_request_authorized(
    request: Request,
    agent_id: str,
    agent_token: Optional[str],
) -> bool:
    """Return whether an HTTP request may resolve a durable agent dashboard link."""
    return _client_is_loopback(request) or bool(
        agent_token and validate_agent_dashboard_token(agent_token, agent_id)
    )


def _with_terminal_dashboard_tokens(session_data: Dict) -> Dict:
    """Attach websocket tokens to terminal rows returned to the dashboard.

    The dashboard may be opened through a Tailscale/Funnel host, where terminal
    websockets are not loopback requests. Session detail is the UI's source for
    "Open Terminal" buttons, so each listed terminal needs the same signed token
    that deep links already use.
    """

    terminals = session_data.get("terminals")
    if not isinstance(terminals, list):
        return session_data
    enriched = []
    for terminal in terminals:
        if isinstance(terminal, dict) and terminal.get("id"):
            terminal = {
                **terminal,
                "terminal_token": create_terminal_dashboard_token(str(terminal["id"])),
            }
        enriched.append(terminal)
    return {**session_data, "terminals": enriched}


def _terminal_rows_with_dashboard_tokens(terminals: List[Dict]) -> List[Dict]:
    """Attach websocket tokens to raw terminal-list rows for dashboard clients."""

    return [
        (
            {
                **terminal,
                "terminal_token": create_terminal_dashboard_token(str(terminal["id"])),
            }
            if isinstance(terminal, dict) and terminal.get("id")
            else terminal
        )
        for terminal in terminals
    ]


async def flow_daemon():
    """Background task to check and execute flows."""
    logger.info("Flow daemon started")
    while True:
        try:
            flows = flow_service.get_flows_to_run()
            for flow in flows:
                try:
                    executed = flow_service.execute_flow(flow.name)
                    if executed:
                        logger.info(f"Flow '{flow.name}' executed successfully")
                    else:
                        logger.info(f"Flow '{flow.name}' skipped (execute=false)")
                except Exception as e:
                    logger.error(f"Flow '{flow.name}' failed: {e}")
        except Exception as e:
            logger.error(f"Flow daemon error: {e}")

        await asyncio.sleep(60)


# Response Models
class TerminalOutputResponse(BaseModel):
    output: str
    mode: str


class AgentRuntimeTerminalResponse(BaseModel):
    """Current terminal manifestation for a durable CAO agent."""

    terminal: Terminal
    terminal_token: str


class AgentWorkspaceResponse(BaseModel):
    setup: Optional[str] = None
    diagnostics: List[str] = []


class LinearToolAccessResponse(BaseModel):
    access_id: str
    tools: List[str]
    issues: List[str]
    create_team_ids: List[str]
    create_project_ids: List[str]
    create_parent_issues: List[str]
    allow_top_level_create: bool
    update_fields: List[str]
    reason: Optional[str] = None


class LinearConfigResponse(BaseModel):
    app_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret_configured: bool
    webhook_secret_configured: bool
    oauth_redirect_uri: Optional[str] = None
    access_token_configured: bool
    refresh_token_configured: bool
    token_expires_at: Optional[str] = None
    app_user_id: Optional[str] = None
    app_user_name: Optional[str] = None
    oauth_state_configured: bool
    tool_access: List[LinearToolAccessResponse]


class AgentConfigResponse(BaseModel):
    """Full durable CAO agent configuration exposed by the read API."""

    id: str
    display_name: str
    cli_provider: str
    workdir: str
    session_name: str
    prompt: str
    description: Optional[str] = None
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    mcp_servers: Dict[str, Any]
    tools: List[str]
    tool_aliases: Dict[str, str]
    tools_settings: Dict[str, Any]
    cao_tools: Optional[List[str]] = None
    skills: List[str]
    tags: List[str]
    resources: List[str]
    hooks: Dict[str, Any]
    use_legacy_mcp_json: Optional[bool] = None
    runtime_capabilities: Optional[List[str]] = None
    codex_config: Dict[str, Any]
    workspace: AgentWorkspaceResponse
    linear: Optional[LinearConfigResponse] = None

    @classmethod
    def from_agent(cls, agent: Agent) -> "AgentConfigResponse":
        linear = None
        if agent.linear is not None:
            linear = LinearConfigResponse(
                app_key=agent.linear.app_key,
                client_id=agent.linear.client_id,
                client_secret_configured=agent.linear.client_secret is not None,
                webhook_secret_configured=agent.linear.webhook_secret is not None,
                oauth_redirect_uri=agent.linear.oauth_redirect_uri,
                access_token_configured=agent.linear.access_token is not None,
                refresh_token_configured=agent.linear.refresh_token is not None,
                token_expires_at=agent.linear.token_expires_at,
                app_user_id=agent.linear.app_user_id,
                app_user_name=agent.linear.app_user_name,
                oauth_state_configured=agent.linear.oauth_state is not None,
                tool_access=[
                    LinearToolAccessResponse(
                        access_id=access.access_id,
                        tools=list(access.tools),
                        issues=list(access.issues),
                        create_team_ids=list(access.create_team_ids),
                        create_project_ids=list(access.create_project_ids),
                        create_parent_issues=list(access.create_parent_issues),
                        allow_top_level_create=access.allow_top_level_create,
                        update_fields=list(access.update_fields),
                        reason=access.reason,
                    )
                    for access in agent.linear.tool_access
                ],
            )
        return cls(
            id=agent.id,
            display_name=agent.display_name,
            cli_provider=agent.cli_provider,
            workdir=agent.workdir,
            session_name=agent.session_name,
            prompt=agent.prompt,
            description=agent.description,
            model=agent.model,
            reasoning_effort=agent.reasoning_effort,
            mcp_servers=dict(agent.mcp_servers),
            tools=list(agent.tools),
            tool_aliases=dict(agent.tool_aliases),
            tools_settings=dict(agent.tools_settings),
            cao_tools=list(agent.cao_tools) if agent.cao_tools is not None else None,
            skills=list(agent.skills),
            tags=list(agent.tags),
            resources=list(agent.resources),
            hooks=dict(agent.hooks),
            use_legacy_mcp_json=agent.use_legacy_mcp_json,
            runtime_capabilities=(
                list(agent.runtime_capabilities) if agent.runtime_capabilities is not None else None
            ),
            codex_config=dict(agent.codex_config),
            workspace=AgentWorkspaceResponse(
                setup=agent.workspace.setup,
                diagnostics=list(agent.workspace.diagnostics),
            ),
            linear=linear,
        )


class AgentStatusResponse(BaseModel):
    """Current CAO agent config and runtime summary."""

    agent_id: str
    display_name: str
    cli_provider: str
    workdir: str
    session_name: str
    config: AgentConfigResponse
    active: bool
    agent_dashboard_token: str
    active_terminal_id: Optional[str] = None
    active_workspace_context_id: Optional[str] = None
    workspace_setup_id: Optional[str] = None
    workspace_setup_diagnostics: List[str] = []
    last_active_at: Optional[datetime] = None

    @classmethod
    def from_status(cls, status: AgentStatus) -> "AgentStatusResponse":
        return cls(
            agent_id=status.agent_id,
            display_name=status.display_name,
            cli_provider=status.cli_provider,
            workdir=status.workdir,
            session_name=status.session_name,
            config=AgentConfigResponse.from_agent(status.agent),
            active=status.active,
            agent_dashboard_token=create_agent_dashboard_token(status.agent_id),
            active_terminal_id=status.active_terminal_id,
            active_workspace_context_id=status.active_workspace_context_id,
            workspace_setup_id=status.workspace_setup_id,
            workspace_setup_diagnostics=list(status.workspace_setup_diagnostics),
            last_active_at=status.last_active_at,
        )


class WorkspaceSetupDiagnosticResponse(BaseModel):
    code: str
    message: str
    setup_id: Optional[str] = None
    agent_id: Optional[str] = None
    provider_name: Optional[str] = None


class AgentWorkspaceWriteRequest(BaseModel):
    setup: Optional[str] = None

    def to_config(
        self,
        existing: AgentWorkspaceConfig | None = None,
    ) -> AgentWorkspaceConfig:
        base = existing or AgentWorkspaceConfig()
        if "setup" in self.model_fields_set:
            return AgentWorkspaceConfig(setup=self.setup)
        return base


class LinearToolAccessWriteRequest(BaseModel):
    access_id: str
    tools: Optional[List[str]] = None
    issues: Optional[List[str]] = None
    create_team_ids: Optional[List[str]] = None
    create_project_ids: Optional[List[str]] = None
    create_parent_issues: Optional[List[str]] = None
    allow_top_level_create: Optional[bool] = None
    update_fields: Optional[List[str]] = None
    reason: Optional[str] = None

    def to_config(
        self,
        existing: LinearToolAccessConfig | None = None,
    ) -> LinearToolAccessConfig:
        return LinearToolAccessConfig(
            access_id=self.access_id,
            tools=tuple(
                self.tools if self.tools is not None else (existing.tools if existing else ())
            ),
            issues=tuple(
                self.issues if self.issues is not None else (existing.issues if existing else ())
            ),
            create_team_ids=tuple(
                self.create_team_ids
                if self.create_team_ids is not None
                else (existing.create_team_ids if existing else ())
            ),
            create_project_ids=tuple(
                self.create_project_ids
                if self.create_project_ids is not None
                else (existing.create_project_ids if existing else ())
            ),
            create_parent_issues=tuple(
                self.create_parent_issues
                if self.create_parent_issues is not None
                else (existing.create_parent_issues if existing else ())
            ),
            allow_top_level_create=(
                self.allow_top_level_create
                if self.allow_top_level_create is not None
                else (existing.allow_top_level_create if existing else False)
            ),
            update_fields=tuple(
                self.update_fields
                if self.update_fields is not None
                else (existing.update_fields if existing else ())
            ),
            reason=(
                self.reason if self.reason is not None else (existing.reason if existing else None)
            ),
        )


class LinearWriteRequest(BaseModel):
    app_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    oauth_redirect_uri: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[str] = None
    app_user_id: Optional[str] = None
    app_user_name: Optional[str] = None
    oauth_state: Optional[str] = None
    tool_access: Optional[List[LinearToolAccessWriteRequest]] = None

    def to_config(self, existing: LinearConfig | None = None) -> LinearConfig:
        existing_access = (
            {access.access_id: access for access in existing.tool_access} if existing else {}
        )
        if self.tool_access is None:
            tool_access = tuple(existing.tool_access) if existing else ()
        else:
            tool_access = tuple(
                access.to_config(existing_access.get(access.access_id))
                for access in self.tool_access
            )
        return LinearConfig(
            app_key=(
                self.app_key
                if self.app_key is not None
                else (existing.app_key if existing else None)
            ),
            client_id=(
                self.client_id
                if self.client_id is not None
                else (existing.client_id if existing else None)
            ),
            client_secret=(
                self.client_secret
                if self.client_secret is not None
                else (existing.client_secret if existing else None)
            ),
            webhook_secret=(
                self.webhook_secret
                if self.webhook_secret is not None
                else (existing.webhook_secret if existing else None)
            ),
            oauth_redirect_uri=(
                self.oauth_redirect_uri
                if self.oauth_redirect_uri is not None
                else (existing.oauth_redirect_uri if existing else None)
            ),
            access_token=(
                self.access_token
                if self.access_token is not None
                else (existing.access_token if existing else None)
            ),
            refresh_token=(
                self.refresh_token
                if self.refresh_token is not None
                else (existing.refresh_token if existing else None)
            ),
            token_expires_at=(
                self.token_expires_at
                if self.token_expires_at is not None
                else (existing.token_expires_at if existing else None)
            ),
            app_user_id=(
                self.app_user_id
                if self.app_user_id is not None
                else (existing.app_user_id if existing else None)
            ),
            app_user_name=(
                self.app_user_name
                if self.app_user_name is not None
                else (existing.app_user_name if existing else None)
            ),
            oauth_state=(
                self.oauth_state
                if self.oauth_state is not None
                else (existing.oauth_state if existing else None)
            ),
            tool_access=tool_access,
        )


class AgentWriteRequest(BaseModel):
    id: Optional[str] = None
    display_name: Optional[str] = None
    cli_provider: Optional[str] = None
    workdir: Optional[str] = None
    session_name: Optional[str] = None
    prompt: Optional[str] = None
    description: Optional[str] = None
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    mcp_servers: Optional[Dict[str, Any]] = None
    tools: Optional[List[str]] = None
    tool_aliases: Optional[Dict[str, str]] = None
    tools_settings: Optional[Dict[str, Any]] = None
    cao_tools: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    resources: Optional[List[str]] = None
    hooks: Optional[Dict[str, Any]] = None
    use_legacy_mcp_json: Optional[bool] = None
    runtime_capabilities: Optional[List[str]] = None
    codex_config: Optional[Dict[str, Any]] = None
    workspace: Optional[AgentWorkspaceWriteRequest] = None
    linear: Optional[LinearWriteRequest] = None

    def to_agent(self, agent_id: str, existing: Optional[Agent] = None) -> Agent:
        base = existing
        fields_set = self.model_fields_set

        def field_value(field_name: str, default: Any) -> Any:
            return getattr(self, field_name) if field_name in fields_set else default

        def mapping_value(field_name: str, default: Dict[str, Any]) -> Dict[str, Any]:
            value = field_value(field_name, default)
            if value is None:
                raise AgentConfigError(f"agents.{agent_id}.{field_name} must be a mapping")
            return dict(value)

        def tuple_value(field_name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            value = field_value(field_name, default)
            if value is None:
                raise AgentConfigError(f"agents.{agent_id}.{field_name} must be a list")
            return tuple(value)

        def nullable_tuple_value(
            field_name: str,
            default: tuple[str, ...] | None,
        ) -> tuple[str, ...] | None:
            value = field_value(field_name, default)
            return None if value is None else tuple(value)

        if "workspace" in fields_set:
            if self.workspace is None:
                raise AgentConfigError(f"agents.{agent_id}.workspace must be a table")
            workspace_config = self.workspace.to_config(base.workspace if base else None)
        else:
            workspace_config = base.workspace if base else AgentWorkspaceConfig()

        if "linear" in fields_set and self.linear is None:
            linear = None
        elif self.linear is not None:
            linear = self.linear.to_config(base.linear if base else None)
        else:
            linear = base.linear if base else None
        return Agent(
            id=agent_id,
            display_name=field_value(
                "display_name",
                base.display_name if base else agent_id,
            ),
            cli_provider=field_value("cli_provider", base.cli_provider if base else "codex"),
            workdir=field_value("workdir", base.workdir if base else str(Path.home())),
            session_name=field_value("session_name", base.session_name if base else agent_id),
            prompt=field_value("prompt", base.prompt if base else ""),
            description=field_value("description", base.description if base else None),
            model=field_value("model", base.model if base else None),
            reasoning_effort=(
                field_value("reasoning_effort", base.reasoning_effort if base else None)
            ),
            mcp_servers=mapping_value("mcp_servers", dict(base.mcp_servers) if base else {}),
            tools=tuple_value("tools", base.tools if base else ()),
            tool_aliases=mapping_value(
                "tool_aliases",
                dict(base.tool_aliases) if base else {},
            ),
            tools_settings=mapping_value(
                "tools_settings",
                dict(base.tools_settings) if base else {},
            ),
            cao_tools=nullable_tuple_value("cao_tools", base.cao_tools if base else None),
            skills=tuple_value("skills", base.skills if base else ()),
            tags=tuple_value("tags", base.tags if base else ()),
            resources=tuple_value("resources", base.resources if base else ()),
            hooks=mapping_value("hooks", dict(base.hooks) if base else {}),
            use_legacy_mcp_json=(
                field_value("use_legacy_mcp_json", base.use_legacy_mcp_json if base else None)
            ),
            runtime_capabilities=nullable_tuple_value(
                "runtime_capabilities",
                base.runtime_capabilities if base else None,
            ),
            codex_config=mapping_value("codex_config", dict(base.codex_config) if base else {}),
            workspace=workspace_config,
            linear=linear,
        )


class AgentTimelineEventResponse(BaseModel):
    """Envelope-level CAO event row for one agent timeline."""

    event_id: str
    event_name: str
    event_type_key: str
    source_type: str
    source_id: str
    occurred_at: datetime
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    event_data: Dict[str, Any]
    participant_role: Optional[str] = None

    @classmethod
    def from_read(cls, read: TimelineEventRead) -> "AgentTimelineEventResponse":
        return cls(
            event_id=read.event_id,
            event_name=read.event_name,
            event_type_key=read.event_type_key,
            source_type=read.source_type,
            source_id=read.source_id,
            occurred_at=read.occurred_at,
            correlation_id=read.correlation_id,
            causation_id=read.causation_id,
            event_data=read.event_data,
            participant_role=read.participant_role,
        )


class AgentTimelineResponse(BaseModel):
    """Timeline read response for one manager-resolved CAO agent."""

    agent: AgentStatusResponse
    events: List[AgentTimelineEventResponse]

    @classmethod
    def from_read(cls, read: AgentTimelineRead) -> "AgentTimelineResponse":
        return cls(
            agent=AgentStatusResponse.from_status(read.agent),
            events=[AgentTimelineEventResponse.from_read(event) for event in read.events],
        )


class AgentCausationRelatedEventsResponse(BaseModel):
    """Direct cause and direct effect event reads for a CAO event."""

    direct_cause: Optional[AgentTimelineEventResponse] = None
    direct_effects: List[AgentTimelineEventResponse]

    @classmethod
    def from_read(
        cls,
        read: CausationRelatedEventsRead,
    ) -> "AgentCausationRelatedEventsResponse":
        return cls(
            direct_cause=(
                AgentTimelineEventResponse.from_read(read.direct_cause)
                if read.direct_cause is not None
                else None
            ),
            direct_effects=[
                AgentTimelineEventResponse.from_read(event) for event in read.direct_effects
            ],
        )


class AgentRelatedEventsResponse(BaseModel):
    """Envelope-based related event threads for one canonical CAO event."""

    event: AgentTimelineEventResponse
    correlation_events: List[AgentTimelineEventResponse]
    causation_events: AgentCausationRelatedEventsResponse

    @classmethod
    def from_read(cls, read: RelatedEventsRead) -> "AgentRelatedEventsResponse":
        return cls(
            event=AgentTimelineEventResponse.from_read(read.event),
            correlation_events=[
                AgentTimelineEventResponse.from_read(event) for event in read.correlation_events
            ],
            causation_events=AgentCausationRelatedEventsResponse.from_read(read.causation_events),
        )


class SkillContentResponse(BaseModel):
    """Response model for a skill content lookup."""

    name: str
    content: str


class ProviderSchemaResponse(BaseModel):
    """Capability schema for one registered CAO provider.

    Backs the Agents tab structured form's provider-aware dropdowns. The
    schema is composed from authoritative sources only: the provider type
    comes from ``ProviderType``, the binary name comes from the provider
    class, install status is resolved at request time via ``shutil.which``,
    and catalog availability comes from the provider's opt-in discovery capability.
    """

    name: str
    binary: str
    installed: bool
    model_catalog_available: bool


class ProviderModelResponse(BaseModel):
    """One provider-discovered model exposed over HTTP."""

    id: str
    display_name: str
    reasoning_efforts: List[str]
    thinking_supported: bool
    max_input_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None


class ProviderCatalogResponse(BaseModel):
    """Provider-discovered model catalog exposed over HTTP."""

    provider_type: str
    models: List[ProviderModelResponse]
    discovered_at: datetime
    source: str


class WorkingDirectoryResponse(BaseModel):
    """Response model for terminal working directory."""

    working_directory: Optional[str] = Field(
        description="Current working directory of the terminal, or None if unavailable"
    )


class CreateMonitoringSessionRequest(BaseModel):
    """Request body for creating a monitoring session."""

    terminal_id: str
    label: Optional[str] = None


class MonitoringMessageEntry(BaseModel):
    """A single message in a monitoring session's window."""

    id: int
    sender_id: str
    receiver_id: str
    message: str
    status: str
    created_at: datetime


class MonitoringSessionResponse(BaseModel):
    """Response shape for monitoring session endpoints."""

    id: str
    terminal_id: str
    label: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    status: Literal["active", "ended"]


class BatonResponse(BaseModel):
    """Operator-facing baton state."""

    id: str
    title: str
    current_holder_id: Optional[str]
    originator_id: str
    status: str
    return_stack: List[str]
    expected_next_action: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_nudged_at: Optional[datetime]
    completed_at: Optional[datetime]


class BatonEventResponse(BaseModel):
    """Operator-facing baton audit event."""

    id: int
    baton_id: str
    event_type: str
    actor_id: str
    from_holder_id: Optional[str]
    to_holder_id: Optional[str]
    message: Optional[str]
    created_at: datetime


class CancelBatonRequest(BaseModel):
    """Operator recovery body for canceling a baton."""

    actor_id: str = "operator"
    message: Optional[str] = None


class ReassignBatonRequest(BaseModel):
    """Operator recovery body for reassigning a baton."""

    holder_id: str
    actor_id: str = "operator"
    message: Optional[str] = None
    expected_next_action: Optional[str] = None


class CreateFlowRequest(BaseModel):
    """Request model for creating a flow."""

    name: str
    schedule: str
    agent_id: str
    provider: str = "kiro_cli"
    prompt_template: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Prevent path traversal — flow name becomes a filename."""
        if "/" in v or "\\" in v or ".." in v:
            raise ValueError("Flow name must not contain '/', '\\', or '..'")
        return v


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting CLI Agent Orchestrator server...")
    setup_logging()
    init_db()
    try:
        app.state.workspace_providers = initialize_enabled_workspace_providers()
    except WorkspaceProviderConfigError as exc:
        logger.error("Workspace providers disabled after startup failure: %s", exc)
        app.state.workspace_providers = []

    # Run cleanup in background
    asyncio.create_task(asyncio.to_thread(cleanup_old_data))

    # Start flow daemon as background task
    daemon_task = asyncio.create_task(flow_daemon())

    # Start baton watchdog as background task only when the experimental
    # local baton feature is explicitly exposed.
    baton_watchdog_task = None
    if is_baton_enabled():
        baton_watchdog_task = asyncio.create_task(baton_watchdog_service.baton_watchdog_loop())

    # Start inbox watcher
    inbox_observer = PollingObserver(timeout=INBOX_POLLING_INTERVAL)
    inbox_observer.schedule(LogFileHandler(), str(TERMINAL_LOG_DIR), recursive=False)
    inbox_observer.start()
    logger.info("Inbox watcher started (PollingObserver)")

    yield

    # Stop inbox observer
    inbox_observer.stop()
    inbox_observer.join()
    logger.info("Inbox watcher stopped")

    # Cancel daemon on shutdown
    daemon_task.cancel()
    try:
        await daemon_task
    except asyncio.CancelledError:
        pass

    # Cancel baton watchdog on shutdown
    if baton_watchdog_task is not None:
        baton_watchdog_task.cancel()
        try:
            await baton_watchdog_task
        except asyncio.CancelledError:
            pass

    logger.info("Shutting down CLI Agent Orchestrator server...")


app = FastAPI(
    title="CLI Agent Orchestrator",
    description="Simplified CLI Agent Orchestrator API",
    version=SERVER_VERSION,
    lifespan=lifespan,
)

# Security: DNS Rebinding Protection
# Validate Host header to prevent DNS rebinding attacks (CVE mitigation)
# Only allow requests with localhost Host headers
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=ALLOWED_HOSTS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(linear_router)


def _is_agent_write_validation(request: Request) -> bool:
    if request.method == "POST" and request.url.path == "/agents":
        return True
    if request.method == "PUT":
        parts = [part for part in request.url.path.split("/") if part]
        return len(parts) == 2 and parts[0] == "agents"
    return False


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    status_code = status.HTTP_400_BAD_REQUEST if _is_agent_write_validation(request) else 422
    return JSONResponse(
        status_code=status_code,
        content={"detail": jsonable_encoder(exc.errors())},
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "cli-agent-orchestrator"}


@app.get("/providers", response_model=List[ProviderSchemaResponse])
async def list_providers_endpoint() -> List[ProviderSchemaResponse]:
    """Return the capability schema for every CAO-registered provider.

    Backs provider-aware dropdowns in the Agents tab structured form. The
    dashboard calls this once per session and caches the result.
    """
    return [
        ProviderSchemaResponse(
            name=schema.name,
            binary=schema.binary,
            installed=schema.installed,
            model_catalog_available=schema.model_catalog_available,
        )
        for schema in provider_manager.list_provider_schemas()
    ]


@app.get("/providers/{provider_type}/catalog", response_model=ProviderCatalogResponse)
async def get_provider_catalog_endpoint(provider_type: str) -> ProviderCatalogResponse:
    """Return a fresh runtime-discovered model catalog for one provider."""
    try:
        provider_cls = provider_manager.provider_class(provider_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    capability = provider_manager.model_discovery_capability(provider_type)
    if capability is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_type} has no model-discovery capability",
        )

    try:
        catalog = capability.discover_catalog()
    except CatalogDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    return ProviderCatalogResponse(
        provider_type=catalog.provider_type,
        models=[
            ProviderModelResponse(
                id=model.id,
                display_name=model.display_name,
                reasoning_efforts=list(model.reasoning_efforts),
                thinking_supported=model.thinking_supported,
                max_input_tokens=model.max_input_tokens,
                max_output_tokens=model.max_output_tokens,
            )
            for model in catalog.models
        ],
        discovered_at=catalog.discovered_at,
        source=catalog.source,
    )


@app.get("/workspace-setups/diagnostics", response_model=List[WorkspaceSetupDiagnosticResponse])
async def list_workspace_setup_diagnostics_endpoint() -> List[WorkspaceSetupDiagnosticResponse]:
    """Return workspace setup validation and pruning diagnostics."""
    try:
        return [
            WorkspaceSetupDiagnosticResponse(
                code=diagnostic.code,
                message=diagnostic.message,
                setup_id=diagnostic.setup_id,
                agent_id=diagnostic.agent_id,
                provider_name=diagnostic.provider_name,
            )
            for diagnostic in default_workspace_setup_manager().diagnostics()
        ]
    except (AgentConfigError, AgentPathError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/agents", response_model=List[AgentStatusResponse])
async def list_agents_endpoint(
    active: Optional[bool] = Query(default=None),
) -> List[AgentStatusResponse]:
    """List CAO agents and current terminal status."""
    try:
        return [
            AgentStatusResponse.from_status(agent_status)
            for agent_status in default_agent_manager().list_statuses(active=active)
        ]
    except (AgentConfigError, AgentPathError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}",
        )


@app.get("/agents/{agent_id}", response_model=AgentStatusResponse)
async def get_agent_endpoint(agent_id: str) -> AgentStatusResponse:
    """Resolve one CAO agent and current terminal status."""
    try:
        return AgentStatusResponse.from_status(default_agent_manager().status_for_agent(agent_id))
    except AgentConfigError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve agent: {str(e)}",
        )


@app.post("/agents", response_model=AgentStatusResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_endpoint(body: AgentWriteRequest) -> AgentStatusResponse:
    agent_id = body.id
    if not agent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="id is required")
    try:
        agent = body.to_agent(agent_id)
        write_agent(agent)
        return AgentStatusResponse.from_status(default_agent_manager().status_for_agent(agent.id))
    except (AgentConfigError, AgentPathError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.put("/agents/{agent_id}", response_model=AgentStatusResponse)
async def update_agent_endpoint(agent_id: str, body: AgentWriteRequest) -> AgentStatusResponse:
    try:
        existing = load_agent(agent_id)
        updated = body.to_agent(agent_id, existing)
        patch_agent_config(updated, changed_fields=set(body.model_fields_set))
        return AgentStatusResponse.from_status(default_agent_manager().status_for_agent(agent_id))
    except (AgentConfigError, AgentPathError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.delete("/agents/{agent_id}")
async def delete_agent_endpoint(
    agent_id: str, confirm: bool = Query(default=False)
) -> Dict[str, bool]:
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="confirm=true is required"
        )
    try:
        status_read = default_agent_manager().status_for_agent(agent_id)
        if status_read.active_terminal_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"Agent '{agent_id}' is running",
                    "terminal_id": status_read.active_terminal_id,
                },
            )
        target = agent_config.AGENTS_ROOT / load_agent(agent_id).id
        if target.is_dir():
            import shutil

            shutil.rmtree(target)
        return {"success": True}
    except HTTPException:
        raise
    except AgentConfigError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/agents/{agent_id}/start", response_model=AgentRuntimeTerminalResponse)
async def start_agent_endpoint(agent_id: str) -> AgentRuntimeTerminalResponse:
    """Start a configured agent, enforcing one live instance per agent."""
    manager = default_agent_manager()
    try:
        status_read = manager.status_for_agent(agent_id)
        if status_read.active_terminal_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"Agent '{agent_id}' is already running",
                    "terminal_id": status_read.active_terminal_id,
                },
            )
        agent = manager.resolve_agent(agent_id)
        terminal_ref = AgentRuntimeHandle(agent, agent_manager=manager).ensure_started()
        terminal = Terminal(**terminal_service.get_terminal(terminal_ref.id))
        return AgentRuntimeTerminalResponse(
            terminal=terminal,
            terminal_token=create_terminal_dashboard_token(terminal.id),
        )
    except HTTPException:
        raise
    except TerminalAgentAlreadyRunningError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Agent '{e.agent_id}' is already running",
                "terminal_id": e.terminal_id,
            },
        )
    except AgentConfigError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start agent {agent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start agent: {str(e)}",
        )


@app.post("/agents/{agent_id}/stop")
async def stop_agent_endpoint(agent_id: str) -> Dict[str, bool]:
    """Stop a configured agent's live terminal."""
    try:
        status_read = default_agent_manager().status_for_agent(agent_id)
        if not status_read.active_terminal_id:
            return {"success": True}
        terminal_service.delete_terminal(status_read.active_terminal_id, require_window_killed=True)
        return {"success": True}
    except AgentConfigError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop agent: {str(e)}",
        )


@app.get(
    "/agents/{agent_id}/timeline",
    response_model=AgentTimelineResponse,
)
async def get_agent_timeline_endpoint(agent_id: str) -> AgentTimelineResponse:
    """Resolve one CAO agent timeline from the durable event participant index."""
    try:
        timeline = AgentTimelineService(default_agent_manager()).timeline_for_agent(agent_id)
        return AgentTimelineResponse.from_read(timeline)
    except AgentConfigError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve agent timeline: {str(e)}",
        )


@app.get(
    "/agents/{agent_id}/events/{event_id}/related",
    response_model=AgentRelatedEventsResponse,
)
async def get_agent_related_events_endpoint(
    agent_id: str,
    event_id: str,
) -> AgentRelatedEventsResponse:
    """Resolve correlation and causation threads for one canonical CAO event."""
    try:
        related_events = AgentTimelineService(
            default_agent_manager()
        ).related_events_for_agent_event(agent_id, event_id)
        return AgentRelatedEventsResponse.from_read(related_events)
    except AgentConfigError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnknownTimelineEventError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve agent related events: {str(e)}",
        )


@app.get("/skills/{name}", response_model=SkillContentResponse)
async def get_skill_content(name: str) -> SkillContentResponse:
    """Return the full Markdown body for an installed skill."""
    try:
        skill_name = validate_skill_name(name)
        content = load_skill_content(skill_name)
        return SkillContentResponse(name=name, content=content)
    except SkillNameError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid skill name: {name}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load skill: {str(e)}",
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill not found: {name}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load skill: {str(e)}",
        )


@app.get("/sessions")
async def list_sessions() -> List[Dict]:
    try:
        return session_service.list_sessions()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}",
        )


@app.get("/sessions/{session_name}")
async def get_session(session_name: str) -> Dict:
    try:
        return _with_terminal_dashboard_tokens(session_service.get_session(session_name))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}",
        )


@app.delete("/sessions/{session_name}")
async def delete_session(session_name: str) -> Dict:
    try:
        result = session_service.delete_session(session_name)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )


@app.get("/sessions/{session_name}/terminals")
async def list_terminals_in_session(session_name: str) -> List[Dict]:
    """List all terminals in a session."""
    try:
        from cli_agent_orchestrator.clients.database import list_terminals_by_session

        return _terminal_rows_with_dashboard_tokens(list_terminals_by_session(session_name))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list terminals: {str(e)}",
        )


@app.get("/terminals/{terminal_id}", response_model=Terminal)
async def get_terminal(terminal_id: TerminalId) -> Terminal:
    try:
        terminal = terminal_service.get_terminal(terminal_id)
        return Terminal(**terminal)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get terminal: {str(e)}",
        )


@app.get("/agents/runtime/{agent_id}/terminal", response_model=AgentRuntimeTerminalResponse)
async def get_agent_runtime_terminal(
    agent_id: str,
    request: Request,
    agent_token: Optional[str] = Query(default=None),
) -> AgentRuntimeTerminalResponse:
    """Resolve a durable CAO agent to its current terminal manifestation."""
    if not _agent_dashboard_request_authorized(request, agent_id, agent_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent dashboard link token is required",
        )
    try:
        agent_status = default_agent_manager().status_for_agent(agent_id)
        if not agent_status.active_terminal_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent runtime '{agent_id}' has no running terminal",
            )
        terminal = Terminal(**terminal_service.get_terminal(agent_status.active_terminal_id))
        return AgentRuntimeTerminalResponse(
            terminal=terminal,
            terminal_token=create_terminal_dashboard_token(agent_status.active_terminal_id),
        )
    except HTTPException:
        raise
    except AgentConfigError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to resolve agent runtime {agent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve agent runtime: {str(e)}",
        )


@app.get("/terminals/{terminal_id}/working-directory", response_model=WorkingDirectoryResponse)
async def get_terminal_working_directory(terminal_id: TerminalId) -> WorkingDirectoryResponse:
    """Get the current working directory of a terminal's pane."""
    try:
        working_directory = terminal_service.get_working_directory(terminal_id)
        return WorkingDirectoryResponse(working_directory=working_directory)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get working directory: {str(e)}",
        )


@app.post("/terminals/{terminal_id}/input")
async def send_terminal_input(terminal_id: TerminalId, message: str) -> Dict:
    try:
        success = terminal_service.send_input(terminal_id, message)
        return {"success": success}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send input: {str(e)}",
        )


@app.get("/terminals/{terminal_id}/output", response_model=TerminalOutputResponse)
async def get_terminal_output(
    terminal_id: TerminalId, mode: OutputMode = OutputMode.FULL
) -> TerminalOutputResponse:
    try:
        output = terminal_service.get_output(terminal_id, mode)
        return TerminalOutputResponse(output=output, mode=mode)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get output: {str(e)}",
        )


@app.post("/terminals/{terminal_id}/exit")
async def exit_terminal(terminal_id: TerminalId) -> Dict:
    """Send provider-specific exit command to terminal."""
    try:
        provider = provider_manager.get_provider(terminal_id)
        if provider is None:
            raise ValueError(f"Provider not found for terminal {terminal_id}")
        exit_command = provider.exit_cli()
        # Some providers use tmux key sequences (e.g., "C-d" for Ctrl+D) instead
        # of text commands (e.g., "/exit"). Key sequences must be sent via
        # send_special_key() to be interpreted by tmux, not as literal text.
        if exit_command.startswith(("C-", "M-")):
            terminal_service.send_special_key(terminal_id, exit_command)
        else:
            terminal_service.send_input(terminal_id, exit_command)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to exit terminal: {str(e)}",
        )


@app.delete("/terminals/{terminal_id}")
async def delete_terminal(terminal_id: TerminalId) -> Dict:
    """Delete a terminal."""
    try:
        success = terminal_service.delete_terminal(terminal_id)
        return {"success": success}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete terminal: {str(e)}",
        )


@app.post("/terminals/{receiver_id}/inbox/messages")
async def create_inbox_message_endpoint(
    receiver_id: TerminalId, sender_id: str, message: str
) -> Dict:
    """Create inbox message and attempt immediate delivery."""
    try:
        delivery = create_inbox_delivery(sender_id, receiver_id, message)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create inbox message: {str(e)}",
        )

    # Best-effort immediate delivery. If the receiver terminal is idle, the
    # message is delivered now; otherwise the watchdog will deliver it when
    # the terminal becomes idle. Delivery failures must not cause the API
    # to report an error — the message was already persisted above.
    try:
        inbox_service.check_and_send_pending_messages(receiver_id)
    except Exception as e:
        logger.warning(f"Immediate delivery attempt failed for {receiver_id}: {e}")

    return {
        "success": True,
        "notification_id": delivery.notification.id,
        "message_id": delivery.message.id if delivery.message is not None else None,
        "sender_id": delivery.message.sender_id if delivery.message is not None else None,
        "receiver_id": delivery.notification.receiver_id,
        "source_kind": delivery.notification.source_kind,
        "source_id": delivery.notification.source_id,
        "created_at": delivery.notification.created_at.isoformat(),
    }


@app.get("/terminals/{terminal_id}/inbox/messages")
async def get_inbox_messages_endpoint(
    terminal_id: TerminalId,
    limit: int = Query(default=10, le=100, description="Maximum number of messages to retrieve"),
    status_param: Optional[str] = Query(
        default=None, alias="status", description="Filter by message status"
    ),
) -> List[Dict]:
    """Get inbox messages for a terminal.

    Args:
        terminal_id: Terminal ID to get messages for
        limit: Maximum number of messages to return (default: 10, max: 100)
        status_param: Optional filter by message status ('pending', 'delivered', 'failed')

    Returns:
        List of inbox messages with sender_id, message, created_at, status
    """
    try:
        # Convert status filter if provided
        status_filter = None
        if status_param:
            try:
                status_filter = MessageStatus(status_param)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_param}. Valid values: pending, delivered, failed",
                )

        deliveries = list_inbox_deliveries(terminal_id, limit=limit, status=status_filter)

        result = []
        for delivery in deliveries:
            result.append(
                {
                    "notification_id": delivery.notification.id,
                    "message_id": delivery.message.id if delivery.message is not None else None,
                    "sender_id": (
                        delivery.message.sender_id if delivery.message is not None else None
                    ),
                    "receiver_id": delivery.notification.receiver_id,
                    "message": delivery.notification.body,
                    "source_kind": delivery.notification.source_kind,
                    "source_id": delivery.notification.source_id,
                    "status": delivery.notification.status.value,
                    "created_at": (
                        delivery.notification.created_at.isoformat()
                        if delivery.notification.created_at
                        else None
                    ),
                }
            )

        return result

    except HTTPException:
        # Re-raise HTTPException (validation errors)
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve inbox messages: {str(e)}",
        )


@app.websocket("/terminals/{terminal_id}/ws")
async def terminal_ws(websocket: WebSocket, terminal_id: str):
    """WebSocket endpoint for live terminal streaming via tmux attach.

    Security: This endpoint provides full PTY access with no authentication.
    It is intended for localhost-only use. Do NOT expose the server to
    untrusted networks (e.g. --host 0.0.0.0) without adding authentication.
    """
    # Reject non-loopback clients unless they came through a signed dashboard link.
    if not _terminal_ws_authorized(websocket, terminal_id):
        logger.warning(
            "Rejected terminal websocket for %s from %s without a valid dashboard token",
            terminal_id,
            websocket.client.host if websocket.client else None,
        )
        await websocket.close(code=4003, reason="WebSocket access is restricted to localhost")
        return

    await websocket.accept()

    metadata = get_terminal_metadata(terminal_id)
    if not metadata:
        logger.warning("Rejected terminal websocket for missing terminal %s", terminal_id)
        await websocket.close(code=4004, reason="Terminal not found")
        return

    session_name = metadata["tmux_session"]
    window_name = metadata["tmux_window"]

    # Create PTY pair for tmux attach
    master_fd, slave_fd = pty.openpty()

    # Set initial terminal size
    winsize = struct.pack("HHHH", 24, 80, 0, 0)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

    # Start tmux attach inside the PTY.
    # Force a known TERM so tmux can initialize its terminfo regardless of
    # how cao-server was launched (GUI/daemon contexts may inherit TERM=dumb,
    # which surfaces as "terminal does not support clear" on attach).
    tmux_env = _tmux_attach_environment()
    proc = subprocess.Popen(
        ["tmux", "-u", "attach-session", "-t", f"{session_name}:{window_name}"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
        preexec_fn=os.setsid,
        env=tmux_env,
    )
    os.close(slave_fd)

    # Make master_fd non-blocking for event-driven reads
    flag = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flag | os.O_NONBLOCK)

    loop = asyncio.get_event_loop()
    output_queue: asyncio.Queue[bytes] = asyncio.Queue()
    done = asyncio.Event()

    def _on_pty_data():
        """Callback when PTY has data available."""
        try:
            data = os.read(master_fd, 65536)
            if data:
                output_queue.put_nowait(data)
            else:
                done.set()
        except BlockingIOError:
            pass
        except OSError:
            done.set()

    loop.add_reader(master_fd, _on_pty_data)

    async def _forward_output():
        """Read from PTY queue and send to WebSocket."""
        while not done.is_set():
            try:
                data = await asyncio.wait_for(output_queue.get(), timeout=1.0)
                # Drain any additional pending data for batching
                while not output_queue.empty():
                    try:
                        data += output_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                await websocket.send_bytes(data)
            except asyncio.TimeoutError:
                if proc.poll() is not None:
                    logger.info(
                        "Terminal websocket output ended for %s because tmux attach exited with %s",
                        terminal_id,
                        proc.returncode,
                    )
                    break
            except asyncio.CancelledError:
                logger.info("Terminal websocket output cancelled for %s", terminal_id)
                break
            except RuntimeError as exc:
                if "websocket.close" in str(exc):
                    logger.info(
                        "Terminal websocket output stopped for %s after client close",
                        terminal_id,
                    )
                else:
                    logger.exception("Terminal websocket output failed for %s", terminal_id)
                break
            except Exception:
                logger.exception("Terminal websocket output failed for %s", terminal_id)
                break

    async def _forward_input():
        """Receive from WebSocket and write to PTY."""
        try:
            while not done.is_set():
                msg = await websocket.receive_text()
                payload = json.loads(msg)
                if payload.get("type") == "input":
                    raw = payload["data"].encode()
                    # Write in chunks to avoid overflowing the PTY buffer
                    chunk_size = 1024
                    for i in range(0, len(raw), chunk_size):
                        os.write(master_fd, raw[i : i + chunk_size])
                        if i + chunk_size < len(raw):
                            await asyncio.sleep(0.01)
                elif payload.get("type") == "resize":
                    rows = payload.get("rows", 24)
                    cols = payload.get("cols", 80)
                    winsize_data = struct.pack("HHHH", rows, cols, 0, 0)
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize_data)
                    # Explicitly notify tmux of the size change —
                    # TIOCSWINSZ on the master doesn't always deliver
                    # SIGWINCH to the child process group.
                    try:
                        os.kill(proc.pid, signal.SIGWINCH)
                    except OSError:
                        pass
        except WebSocketDisconnect as exc:
            logger.info(
                "Terminal websocket client disconnected for %s with code %s",
                terminal_id,
                getattr(exc, "code", None),
            )
            pass
        except asyncio.CancelledError:
            logger.info("Terminal websocket input cancelled for %s", terminal_id)
            pass
        except Exception:
            logger.exception("Terminal websocket input failed for %s", terminal_id)
            pass
        finally:
            done.set()

    try:
        await asyncio.gather(_forward_output(), _forward_input())
    except (Exception, asyncio.CancelledError):
        pass
    finally:
        done.set()
        try:
            loop.remove_reader(master_fd)
        except Exception:
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
        # Terminate tmux attach (just detaches, doesn't kill the session)
        proc.terminate()
        try:
            await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=3.0)
        except asyncio.TimeoutError:
            proc.kill()
            await asyncio.to_thread(proc.wait)


# -----------------------------------------------------------------------------
# Baton routes (operator inspection and recovery)
#
# ``GET /batons`` defaults to active batons because the primary operator and
# dashboard need is current ownership visibility. Pass a concrete status to
# inspect another lifecycle bucket.
# -----------------------------------------------------------------------------


def _baton_response(baton: Baton) -> BatonResponse:
    return BatonResponse(**baton.model_dump())


def _baton_event_response(event: BatonEvent) -> BatonEventResponse:
    return BatonEventResponse(**event.model_dump())


def _raise_baton_http_error(exc: Exception) -> NoReturn:
    if isinstance(exc, baton_service.BatonNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Baton not found: {str(exc)}",
        )
    if isinstance(exc, baton_service.BatonAuthorizationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    if isinstance(exc, baton_service.BatonInvalidTransition):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to process baton request: {str(exc)}",
    )


def _require_baton_http_enabled() -> None:
    if not is_baton_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Baton feature is disabled. Set CAO_BATON_ENABLED=true to expose it.",
        )


@app.get("/batons", response_model=List[BatonResponse], include_in_schema=is_baton_enabled())
async def list_batons_endpoint(
    status_filter: Optional[BatonStatus] = Query(
        default=BatonStatus.ACTIVE,
        alias="status",
        description="Filter by lifecycle status. Defaults to active for dashboard ownership visibility.",
    ),
    holder_id: Optional[str] = None,
    originator_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> List[BatonResponse]:
    _require_baton_http_enabled()
    batons = list_batons(
        status=status_filter,
        holder_id=holder_id,
        originator_id=originator_id,
        limit=limit,
        offset=offset,
    )
    return [_baton_response(baton) for baton in batons]


@app.get(
    "/batons/{baton_id}",
    response_model=BatonResponse,
    include_in_schema=is_baton_enabled(),
)
async def get_baton_endpoint(baton_id: str) -> BatonResponse:
    _require_baton_http_enabled()
    baton = get_baton_record(baton_id)
    if baton is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Baton not found: {baton_id}",
        )
    return _baton_response(baton)


@app.get(
    "/batons/{baton_id}/events",
    response_model=List[BatonEventResponse],
    include_in_schema=is_baton_enabled(),
)
async def get_baton_events_endpoint(baton_id: str) -> List[BatonEventResponse]:
    _require_baton_http_enabled()
    if get_baton_record(baton_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Baton not found: {baton_id}",
        )
    return [_baton_event_response(event) for event in list_baton_events(baton_id)]


@app.post(
    "/batons/{baton_id}/cancel",
    response_model=BatonResponse,
    include_in_schema=is_baton_enabled(),
)
async def cancel_baton_endpoint(baton_id: str, body: CancelBatonRequest) -> BatonResponse:
    _require_baton_http_enabled()
    try:
        baton = baton_service.cancel_baton(
            baton_id=baton_id,
            actor_id=body.actor_id,
            message=body.message,
            operator_recovery=True,
        )
        return _baton_response(baton)
    except Exception as exc:
        _raise_baton_http_error(exc)


@app.post(
    "/batons/{baton_id}/reassign",
    response_model=BatonResponse,
    include_in_schema=is_baton_enabled(),
)
async def reassign_baton_endpoint(baton_id: str, body: ReassignBatonRequest) -> BatonResponse:
    _require_baton_http_enabled()
    try:
        baton = baton_service.reassign_baton(
            baton_id=baton_id,
            actor_id=body.actor_id,
            receiver_id=body.holder_id,
            message=body.message,
            expected_next_action=body.expected_next_action,
            operator_recovery=True,
        )
        return _baton_response(baton)
    except Exception as exc:
        _raise_baton_http_error(exc)


# ── Flow management endpoints ────────────────────────────────────────


@app.get("/flows", response_model=List[Flow])
async def list_flows() -> List[Flow]:
    """List all flows."""
    try:
        return flow_service.list_flows()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list flows: {str(e)}",
        )


@app.get("/flows/{name}", response_model=Flow)
async def get_flow(name: str) -> Flow:
    """Get a specific flow by name."""
    try:
        return flow_service.get_flow(name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get flow: {str(e)}",
        )


@app.post("/flows", response_model=Flow, status_code=status.HTTP_201_CREATED)
async def create_flow(body: CreateFlowRequest) -> Flow:
    """Create a new flow.

    Writes a .flow.md file with YAML frontmatter and prompt body, then
    registers it via flow_service.add_flow().
    """
    try:
        flows_dir = CAO_HOME_DIR / "flows"
        flows_dir.mkdir(parents=True, exist_ok=True)

        file_path = flows_dir / f"{body.name}.flow.md"

        # Build YAML frontmatter content
        frontmatter_lines = [
            "---",
            f"name: {body.name}",
            f'schedule: "{body.schedule}"',
            f"agent_id: {body.agent_id}",
            f"provider: {body.provider}",
            "---",
        ]
        file_content = "\n".join(frontmatter_lines) + "\n" + body.prompt_template

        file_path.write_text(file_content)

        return flow_service.add_flow(str(file_path))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create flow: {str(e)}",
        )


@app.delete("/flows/{name}")
async def remove_flow(name: str) -> Dict:
    """Remove a flow."""
    try:
        flow_service.remove_flow(name)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove flow: {str(e)}",
        )


@app.post("/flows/{name}/enable")
async def enable_flow(name: str) -> Dict:
    """Enable a flow."""
    try:
        flow_service.enable_flow(name)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable flow: {str(e)}",
        )


@app.post("/flows/{name}/disable")
async def disable_flow(name: str) -> Dict:
    """Disable a flow."""
    try:
        flow_service.disable_flow(name)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable flow: {str(e)}",
        )


@app.post("/flows/{name}/run")
async def run_flow(name: str) -> Dict:
    """Manually execute a flow."""
    try:
        executed = flow_service.execute_flow(name)
        return {"executed": executed}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute flow: {str(e)}",
        )


# -----------------------------------------------------------------------------
# Monitoring session routes (single-session, query-time filtering)
#
# Thin adapter over ``monitoring_service``. Sessions record everything
# involving a terminal; filtering (by peer, by time sub-window) is a
# query-time concern on ``/messages`` and ``/log``. Intentionally NOT exposed
# as MCP tools — monitoring is operator / procedure concern, not agent.
# See docs/plans/monitoring-sessions.md.
# -----------------------------------------------------------------------------


@app.post(
    "/monitoring/sessions",
    response_model=MonitoringSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitoring_session(
    body: CreateMonitoringSessionRequest,
) -> MonitoringSessionResponse:
    """Start monitoring a terminal, or return the existing active session.

    Idempotent on active state: calling this for a terminal that already
    has an active session returns that session unchanged — the label
    argument is ignored in that case. Clients that want to check state
    first can call ``GET /monitoring/sessions?terminal_id=X&status=active``.
    """
    result = monitoring_service.create_session(
        terminal_id=body.terminal_id,
        label=body.label,
    )
    return MonitoringSessionResponse(**result)


@app.get("/monitoring/sessions", response_model=List[MonitoringSessionResponse])
async def list_monitoring_sessions(
    terminal_id: Optional[str] = None,
    status: Optional[Literal["active", "ended"]] = None,
    label: Optional[str] = None,
    started_after: Optional[datetime] = None,
    started_before: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> List[MonitoringSessionResponse]:
    rows = monitoring_service.list_sessions(
        terminal_id=terminal_id,
        status=status,
        label=label,
        started_after=started_after,
        started_before=started_before,
        limit=limit,
        offset=offset,
    )
    return [MonitoringSessionResponse(**r) for r in rows]


@app.get("/monitoring/sessions/{session_id}", response_model=MonitoringSessionResponse)
async def get_monitoring_session(session_id: str) -> MonitoringSessionResponse:
    result = monitoring_service.get_session(session_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring session not found: {session_id}",
        )
    return MonitoringSessionResponse(**result)


@app.post(
    "/monitoring/sessions/{session_id}/end",
    response_model=MonitoringSessionResponse,
)
async def end_monitoring_session(session_id: str) -> MonitoringSessionResponse:
    try:
        result = monitoring_service.end_session(session_id)
    except monitoring_service.SessionNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring session not found: {session_id}",
        )
    except monitoring_service.SessionAlreadyEnded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Monitoring session already ended: {session_id}",
        )
    return MonitoringSessionResponse(**result)


@app.get(
    "/monitoring/sessions/{session_id}/messages",
    response_model=List[MonitoringMessageEntry],
)
async def get_monitoring_messages(
    session_id: str,
    peer: List[str] = Query(default_factory=list),
    started_after: Optional[datetime] = None,
    started_before: Optional[datetime] = None,
) -> List[MonitoringMessageEntry]:
    """Return messages captured by the session, with optional query filters.

    Query params:
      peer: repeatable — match messages whose sender OR receiver is one of
        the listed peers. Omit for no peer filter.
      started_after / started_before: narrow to a sub-window inside the
        session's bounds.
    """
    try:
        rows = monitoring_service.get_session_messages(
            session_id,
            peers=peer,
            started_after=started_after,
            started_before=started_before,
        )
    except monitoring_service.SessionNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring session not found: {session_id}",
        )
    return [MonitoringMessageEntry(**r) for r in rows]


@app.get("/monitoring/sessions/{session_id}/log")
async def get_monitoring_log(
    session_id: str,
    format: Literal["markdown", "json"] = "markdown",
    peer: List[str] = Query(default_factory=list),
    started_after: Optional[datetime] = None,
    started_before: Optional[datetime] = None,
):
    """Render a monitoring session as a drop-in artifact.

    Default is Markdown (intended to sit next to a review document).
    ``format=json`` returns a structured ``{session, messages, filter}``
    payload for programmatic use.

    The same ``peer`` / ``started_after`` / ``started_before`` filters as
    ``/messages`` apply at rendering time — so you can generate multiple
    distinct artifacts (one per peer, or one per step time window) from a
    single recording.
    """
    from fastapi.responses import JSONResponse, PlainTextResponse

    session = monitoring_service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring session not found: {session_id}",
        )
    messages = monitoring_service.get_session_messages(
        session_id,
        peers=peer,
        started_after=started_after,
        started_before=started_before,
    )

    # Capture the filter (if any was applied) so the artifact self-describes
    # what slice of the recording it represents.
    applied_filter = None
    if peer or started_after or started_before:
        applied_filter = {
            "peers": peer or None,
            "started_after": started_after,
            "started_before": started_before,
        }

    if format == "json":
        payload = monitoring_formatter.format_json(session, messages, applied_filter=applied_filter)
        return JSONResponse(content=jsonable_encoder(payload))
    body = monitoring_formatter.format_markdown(session, messages, applied_filter=applied_filter)
    return PlainTextResponse(body, media_type="text/markdown; charset=utf-8")


@app.delete(
    "/monitoring/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_monitoring_session(session_id: str) -> Response:
    try:
        monitoring_service.delete_session(session_id)
    except monitoring_service.SessionNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring session not found: {session_id}",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Static file serving for built web UI.
# Anchored to the package via importlib.resources so it works for both
# editable installs (uv sync) and wheel installs (uv tool install, pip install).
from importlib.resources import files as _pkg_files

WEB_DIST = Path(str(_pkg_files("cli_agent_orchestrator") / "web_ui"))
if (WEB_DIST / "index.html").exists():
    from starlette.staticfiles import StaticFiles
    from starlette.types import Scope

    class NoCacheStaticFiles(StaticFiles):
        """Serve the dashboard without browser caching.

        The dashboard is often rebuilt while the local CAO server is running.
        Safari can otherwise keep an older HTML/JS pair alive and continue using
        stale websocket behavior even after the server and bundle are patched.
        """

        async def get_response(self, path: str, scope: Scope) -> Response:
            response = await super().get_response(path, scope)
            response.headers["Cache-Control"] = "no-store"
            return response

    app.mount("/", NoCacheStaticFiles(directory=str(WEB_DIST), html=True), name="web")


def main():
    """Entry point for cao-server command."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="CLI Agent Orchestrator Server")
    parser.add_argument(
        "--agents-dir",
        type=str,
        default=None,
        help="Path to agents directory (overrides CAO_AGENTS_DIR env var)",
    )
    parser.add_argument("--host", type=str, default=None, help="Server host")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    args = parser.parse_args()

    if args.agents_dir:
        configured_agents_root = configure_agents_root(args.agents_dir)
        os.environ[CAO_AGENTS_DIR_ENV] = str(configured_agents_root)
        import cli_agent_orchestrator.constants as constants

        constants.KIRO_AGENTS_DIR = configured_agents_root
        logger.info("Using agents directory: %s", configured_agents_root)

    host = args.host or SERVER_HOST
    port = args.port or SERVER_PORT
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

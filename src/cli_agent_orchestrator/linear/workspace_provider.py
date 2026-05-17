"""Linear workspace-provider config, presence mapping, and lifecycle."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from cli_agent_orchestrator.agent import (
    Agent,
    AgentConfigError,
    AgentRegistry,
    load_agent_registry,
    patch_agent_section,
)
from cli_agent_orchestrator.constants import SESSION_PREFIX
from cli_agent_orchestrator.linear.provider_tools import (
    CREATE_ISSUE_TOOL,
    CREATE_PROJECT_TOOL,
    ISSUE_TARGETING_TOOLS,
    LINEAR_PROVIDER_TOOLS,
    LinearToolAccess,
    LinearToolProvider,
    UPDATE_ISSUE_FIELDS,
    UPDATE_ISSUE_TOOL,
)
from cli_agent_orchestrator.linear.workspace_events import LINEAR_CAO_EVENTS
from cli_agent_orchestrator.utils.env import load_env_vars
from cli_agent_orchestrator.workspace_providers.tool_access import ProviderToolAccessPolicy

APP_KEY_PATTERN = re.compile(r"[^A-Za-z0-9]+")
_default_linear_workspace_provider: Optional["LinearWorkspaceProvider"] = None


class LinearWorkspaceProviderConfigError(ValueError):
    """Raised when Linear workspace-provider configuration is invalid."""


@dataclass(frozen=True)
class LinearPresence:
    """A Linear app-user presence mapped to a durable CAO agent."""

    presence_id: str
    agent_id: str
    app_key: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    oauth_redirect_uri: Optional[str] = None
    oauth_state: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    app_user_id: Optional[str] = None
    app_user_name: Optional[str] = None
    token_expires_at: Optional[str] = None


LinearCredentialChecker = Callable[[LinearPresence], Mapping[str, Any]]


@dataclass(frozen=True)
class LinearProviderConfig:
    """Linear workspace-provider config loaded from durable agent configs."""

    public_url: Optional[str]
    presences: dict[str, LinearPresence]
    tool_access: dict[str, LinearToolAccess]
    agent_policies_enabled: bool = False
    source: str = "agents"

    def presence_by_app_key(self, app_key: str) -> Optional[LinearPresence]:
        normalized = normalize_app_key(app_key)
        return next(
            (presence for presence in self.presences.values() if presence.app_key == normalized),
            None,
        )

    def presence_by_app_user_id(self, app_user_id: str) -> Optional[LinearPresence]:
        return next(
            (
                presence
                for presence in self.presences.values()
                if presence.app_user_id == app_user_id
            ),
            None,
        )

    def presence_by_app_user_name(self, app_user_name: str) -> Optional[LinearPresence]:
        return next(
            (
                presence
                for presence in self.presences.values()
                if presence.app_user_name == app_user_name
            ),
            None,
        )

    def presence_by_oauth_state(self, oauth_state: str) -> Optional[LinearPresence]:
        return next(
            (
                presence
                for presence in self.presences.values()
                if presence.oauth_state == oauth_state
            ),
            None,
        )


@dataclass(frozen=True)
class LinearResolvedPresence:
    """Resolved Linear presence plus the CAO runtime agent it maps to."""

    presence: LinearPresence
    agent: Agent


def linear_env(name: str) -> Optional[str]:
    """Read Linear process config from CAO's env file."""
    return load_env_vars().get(name)


def normalize_app_key(app_key: str) -> str:
    """Return a stable provider-native app key for Linear presence lookup."""
    normalized = APP_KEY_PATTERN.sub("_", app_key.strip().lower()).strip("_")
    if not normalized:
        raise LinearWorkspaceProviderConfigError(
            "Linear app key must contain at least one letter or digit"
        )
    return normalized


def app_env_prefix(app_key: str) -> str:
    """Return the env prefix for a configured Linear app key."""
    return f"LINEAR_APP_{APP_KEY_PATTERN.sub('_', normalize_app_key(app_key)).upper()}"


def linear_app_env(
    app_key: Optional[str],
    name: str,
    *,
    agents_root: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> Optional[str]:
    """Read a Linear presence field from an agent's ``[linear]`` config."""
    config = load_linear_provider_config(
        agents_root=agents_root,
        env_reader=env_reader,
    )
    if config is not None:
        if not app_key:
            return None
        presence = config.presence_by_app_key(app_key)
        return _presence_field(presence, name) if presence is not None else None
    return None


def configured_app_keys(
    *,
    agents_root: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> list[str]:
    """Return Linear app keys configured in agent directories."""
    config = load_linear_provider_config(
        agents_root=agents_root,
        env_reader=env_reader,
    )
    if config is not None:
        return [presence.app_key for presence in config.presences.values()]
    return []


def configured_app_key_for_oauth_state(
    state: Optional[str],
    *,
    agents_root: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> Optional[str]:
    """Resolve a Linear app key from an agent-owned OAuth nonce."""
    if not state:
        return None
    config = load_linear_provider_config(
        agents_root=agents_root,
        env_reader=env_reader,
    )
    if config is None:
        return None
    presence = config.presence_by_oauth_state(state)
    return presence.app_key if presence is not None else None


def required_linear_app_env(
    app_key: Optional[str],
    name: str,
    *,
    agents_root: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> str:
    """Read a required Linear config value from an agent's ``[linear]`` config."""
    value = linear_app_env(app_key, name, agents_root=agents_root, env_reader=env_reader)
    if value:
        return value
    if app_key:
        raise LinearWorkspaceProviderConfigError(f"{app_env_prefix(app_key)}_{name} is required")
    raise LinearWorkspaceProviderConfigError(f"LINEAR_{name} is required")


def _presence_field(presence: LinearPresence, env_name: str) -> Optional[str]:
    field_name = env_name.lower()
    if field_name == "oauth_redirect_uri":
        return presence.oauth_redirect_uri
    if field_name == "oauth_state":
        return presence.oauth_state
    value = getattr(presence, field_name, None)
    return str(value) if value else None


def _require_str(table: Mapping[str, Any], key: str, *, presence_id: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LinearWorkspaceProviderConfigError(
            f"presences.{presence_id}.{key} must be a non-empty string"
        )
    return value.strip()


def _optional_str(table: Mapping[str, Any], key: str) -> Optional[str]:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise LinearWorkspaceProviderConfigError(f"{key} must be a string")
    value = value.strip()
    return value or None


def _linear_presence_from_agent(agent: Agent) -> Optional[LinearPresence]:
    linear = agent.linear
    if linear is None or linear.app_key is None:
        return None
    return LinearPresence(
        presence_id=agent.id,
        agent_id=agent.id,
        app_key=normalize_app_key(linear.app_key),
        client_id=linear.client_id,
        client_secret=linear.client_secret,
        webhook_secret=linear.webhook_secret,
        oauth_redirect_uri=linear.oauth_redirect_uri,
        oauth_state=linear.oauth_state,
        access_token=linear.access_token,
        refresh_token=linear.refresh_token,
        app_user_id=linear.app_user_id,
        app_user_name=linear.app_user_name,
        token_expires_at=linear.token_expires_at,
    )


def _linear_tool_access_from_agent(agent: Agent) -> tuple[LinearToolAccess, ...]:
    linear = agent.linear
    if linear is None:
        return ()
    for access in linear.tool_access:
        _validate_linear_tool_access(agent, access)
    return tuple(
        LinearToolAccess(
            access_id=access.access_id,
            agent_id=agent.id,
            tools=access.tools,
            issues=access.issues,
            create_team_ids=access.create_team_ids,
            create_project_ids=access.create_project_ids,
            create_parent_issues=access.create_parent_issues,
            allow_top_level_create=access.allow_top_level_create,
            update_fields=access.update_fields,
            reason=access.reason,
            source_location=f"agents.{agent.id}.linear.tool_access.{access.access_id}",
        )
        for access in linear.tool_access
    )


def _validate_linear_tool_access(agent: Agent, access: Any) -> None:
    location = f"agents.{agent.id}.linear.tool_access.{access.access_id}"
    for index, tool in enumerate(access.tools):
        if tool not in LINEAR_PROVIDER_TOOLS:
            raise LinearWorkspaceProviderConfigError(
                f"{location}.tools[{index}] unknown Linear tool: {tool}"
            )
    if any(tool in ISSUE_TARGETING_TOOLS for tool in access.tools) and not access.issues:
        raise LinearWorkspaceProviderConfigError(
            f"{location}.issues must be a non-empty string list"
        )
    if (
        CREATE_ISSUE_TOOL in access.tools or CREATE_PROJECT_TOOL in access.tools
    ) and not access.create_team_ids:
        raise LinearWorkspaceProviderConfigError(
            f"{location}.create_team_ids must be a non-empty string list"
        )
    if (
        CREATE_ISSUE_TOOL in access.tools
        and not access.allow_top_level_create
        and not access.create_parent_issues
    ):
        raise LinearWorkspaceProviderConfigError(
            f"{location} must allow top-level issue creation or configure "
            "create_parent_issues for cao_linear.create_issue"
        )
    if UPDATE_ISSUE_TOOL in access.tools and not access.update_fields:
        raise LinearWorkspaceProviderConfigError(
            f"{location}.update_fields must be a non-empty string list"
        )
    for index, field in enumerate(access.update_fields):
        if field not in UPDATE_ISSUE_FIELDS:
            raise LinearWorkspaceProviderConfigError(
                f"{location}.update_fields[{index}] unknown Linear update field: {field}"
            )


def load_linear_provider_config(
    *,
    agents_root: Optional[Path] = None,
    agent_registry: Optional[AgentRegistry] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> Optional[LinearProviderConfig]:
    """Load Linear workspace-provider config from durable agent directories."""
    registry = agent_registry or load_agent_registry(agents_root)
    agents = registry.all()
    presences: dict[str, LinearPresence] = {}
    tool_access: dict[str, LinearToolAccess] = {}
    for agent in agents.values():
        presence = _linear_presence_from_agent(agent)
        if presence is not None:
            presences[presence.presence_id] = presence
        for access in _linear_tool_access_from_agent(agent):
            tool_access[access.location] = access
    if not presences and not tool_access:
        return None
    config = LinearProviderConfig(
        public_url=None,
        presences=presences,
        tool_access=tool_access,
        agent_policies_enabled=False,
        source="agents",
    )
    validate_linear_provider_config(config, agent_registry=registry)
    return config


def validate_linear_provider_config(
    config: LinearProviderConfig,
    *,
    agent_registry: Optional[AgentRegistry] = None,
) -> None:
    """Validate Linear presence uniqueness and optional CAO agent references."""
    app_keys: set[str] = set()
    app_user_ids: set[str] = set()
    app_user_names: set[str] = set()
    oauth_states: set[str] = set()
    webhook_secrets: set[str] = set()
    agent_ids: set[str] = set()

    for presence in config.presences.values():
        if presence.app_key in app_keys:
            raise LinearWorkspaceProviderConfigError(
                f"Duplicate Linear app_key mapping: {presence.app_key}"
            )
        app_keys.add(presence.app_key)

        if presence.app_user_id:
            if presence.app_user_id in app_user_ids:
                raise LinearWorkspaceProviderConfigError(
                    f"Duplicate Linear app_user_id mapping: {presence.app_user_id}"
                )
            app_user_ids.add(presence.app_user_id)

        if presence.app_user_name:
            if presence.app_user_name in app_user_names:
                raise LinearWorkspaceProviderConfigError(
                    f"Duplicate Linear app_user_name mapping: {presence.app_user_name}"
                )
            app_user_names.add(presence.app_user_name)

        if presence.oauth_state:
            if presence.oauth_state in oauth_states:
                raise LinearWorkspaceProviderConfigError("Duplicate Linear oauth_state mapping")
            oauth_states.add(presence.oauth_state)

        if presence.webhook_secret:
            if presence.webhook_secret in webhook_secrets:
                raise LinearWorkspaceProviderConfigError("Duplicate Linear webhook_secret mapping")
            webhook_secrets.add(presence.webhook_secret)

        if presence.agent_id in agent_ids:
            raise LinearWorkspaceProviderConfigError(
                f"Duplicate Linear CAO agent_id mapping: {presence.agent_id}"
            )
        agent_ids.add(presence.agent_id)

        if agent_registry is not None:
            try:
                agent_registry.get(presence.agent_id)
            except AgentConfigError as exc:
                raise LinearWorkspaceProviderConfigError(
                    f"Linear presence {presence.presence_id} references missing CAO agent "
                    f"agent: {presence.agent_id}"
                ) from exc

    for access in config.tool_access.values():
        if access.agent_id and access.agent_id not in agent_ids:
            raise LinearWorkspaceProviderConfigError(
                f"{access.location}.agent_id references missing Linear presence: {access.agent_id}"
            )


def parse_linear_token_expires_at(presence: LinearPresence) -> Optional[datetime]:
    if not presence.token_expires_at:
        return None
    raw = presence.token_expires_at.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LinearWorkspaceProviderConfigError(
            f"Linear presence {presence.presence_id} token_expires_at is not a valid ISO datetime"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_check_linear_presence_credentials(presence: LinearPresence) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    try:
        access_token = app_client.access_token_for_presence(presence)
        viewer = app_client.fetch_viewer(access_token)
    except app_client.LinearOAuthError as exc:
        raise LinearWorkspaceProviderConfigError(
            f"Linear presence {presence.presence_id} could not obtain a valid access token; "
            "reauthorize the Linear app if token refresh is unavailable"
        ) from exc
    return viewer


def preflight_linear_provider_credentials(
    config: LinearProviderConfig,
    *,
    credential_checker: LinearCredentialChecker = _default_check_linear_presence_credentials,
) -> None:
    """Verify configured Linear app credentials before the provider accepts traffic."""
    for presence in config.presences.values():
        if not presence.access_token and not presence.refresh_token:
            raise LinearWorkspaceProviderConfigError(
                f"Linear presence {presence.presence_id} is missing access_token and "
                "refresh_token; reauthorize the Linear app before starting the provider"
            )
        expires_at = parse_linear_token_expires_at(presence)
        if (
            expires_at is not None
            and expires_at <= datetime.now(timezone.utc)
            and not presence.refresh_token
        ):
            raise LinearWorkspaceProviderConfigError(
                f"Linear presence {presence.presence_id} access token expired at "
                f"{expires_at.isoformat()} and no refresh_token is configured; reauthorize the "
                "Linear app before starting the provider"
            )
        viewer = credential_checker(presence)
        viewer_id = viewer.get("id")
        if not viewer_id:
            raise LinearWorkspaceProviderConfigError(
                f"Linear presence {presence.presence_id} credential check did not return a "
                "viewer id"
            )
        if presence.app_user_id and presence.app_user_id != str(viewer_id):
            raise LinearWorkspaceProviderConfigError(
                f"Linear presence {presence.presence_id} app_user_id does not match the "
                "authenticated Linear app user"
            )


def update_linear_presence_tokens(
    app_key: str,
    *,
    access_token: str,
    refresh_token: Optional[str] = None,
    app_user_id: Optional[str] = None,
    app_user_name: Optional[str] = None,
    token_expires_at: Optional[str] = None,
    agents_root: Optional[Path] = None,
) -> bool:
    """Persist OAuth token data into the matching agent's ``[linear]`` config."""
    config = load_linear_provider_config(agents_root=agents_root)
    if config is None:
        return False
    presence = config.presence_by_app_key(app_key)
    if presence is None:
        return False
    updates: dict[str, str] = {"access_token": access_token}
    if refresh_token:
        updates["refresh_token"] = refresh_token
    if app_user_id:
        updates["app_user_id"] = app_user_id
    if app_user_name:
        updates["app_user_name"] = app_user_name
    if token_expires_at:
        updates["token_expires_at"] = token_expires_at
    patch_agent_section(
        presence.agent_id,
        "linear",
        updates,
        agents_root=agents_root,
    )
    return True


def persist_linear_oauth_install(
    *,
    app_key: Optional[str],
    access_token: str,
    refresh_token: Optional[str] = None,
    app_user_id: Optional[str] = None,
    app_user_name: Optional[str] = None,
    token_expires_at: Optional[str] = None,
    agents_root: Optional[Path] = None,
    env_writer: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """Persist Linear OAuth install data at the agent config edge."""
    if app_key and update_linear_presence_tokens(
        app_key,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
        app_user_id=app_user_id,
        app_user_name=app_user_name,
        agents_root=agents_root,
    ):
        return True
    return False


def _extract_app_user_id(payload: Mapping[str, Any]) -> Optional[str]:
    keys = ("_cao_linear_app_user_id", "appUserId", "app_user_id", "agentAppUserId")
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)

    data = payload.get("data")
    if isinstance(data, Mapping):
        found = _extract_app_user_id(data)
        if found:
            return found

    for key in ("appUser", "agentUser", "viewer", "actor"):
        value = payload.get(key)
        if isinstance(value, Mapping) and value.get("id"):
            return str(value["id"])
    return None


def _extract_app_user_name(payload: Mapping[str, Any]) -> Optional[str]:
    for key in ("_cao_linear_app_user_name", "appUserName", "app_user_name"):
        value = payload.get(key)
        if value:
            return str(value)
    for key in ("appUser", "agentUser", "viewer", "actor"):
        value = payload.get(key)
        if isinstance(value, Mapping) and value.get("name"):
            return str(value["name"])
    data = payload.get("data")
    if isinstance(data, Mapping):
        return _extract_app_user_name(data)
    return None


def _extract_app_key(payload: Mapping[str, Any]) -> Optional[str]:
    value = payload.get("_cao_linear_app_key") or payload.get("appKey") or payload.get("app_key")
    return normalize_app_key(str(value)) if value else None


class LinearWorkspaceProvider:
    """Linear workspace-provider lifecycle and presence resolver."""

    name = "linear"

    def __init__(
        self,
        *,
        agent_registry: Optional[AgentRegistry] = None,
        agents_root: Optional[Path] = None,
        env_reader: Callable[[str], Optional[str]] = linear_env,
        preflight_credentials: bool = True,
        credential_checker: Optional[LinearCredentialChecker] = None,
    ) -> None:
        self._agent_registry = agent_registry or load_agent_registry(agents_root)
        self._agents_root = agents_root
        self._env_reader = env_reader
        self._preflight_credentials = preflight_credentials
        self._credential_checker = credential_checker or _default_check_linear_presence_credentials
        self._config: Optional[LinearProviderConfig] = None

    @property
    def config(self) -> Optional[LinearProviderConfig]:
        return self._config

    @property
    def agent_registry(self) -> AgentRegistry:
        """Return the agent registry used to resolve this provider's presences."""
        return self._agent_registry

    def has_provider_tool_access_config(self) -> bool:
        """Return whether Linear config declares CAO-mediated tool access."""
        try:
            config = load_linear_provider_config(
                agents_root=self._agents_root,
                agent_registry=self._agent_registry,
                env_reader=self._env_reader,
            )
        except LinearWorkspaceProviderConfigError:
            return True
        return bool(config and config.tool_access)

    def published_cao_events(self):
        """Return Linear CAO events subscribers may handle."""

        return LINEAR_CAO_EVENTS

    def agent_policies_enabled(self) -> bool:
        """Return whether Linear's WIP agent-presence policy guardrails are enabled."""
        return self._load_config().agent_policies_enabled

    def initialize(self) -> None:
        self._config = load_linear_provider_config(
            agents_root=self._agents_root,
            agent_registry=self._agent_registry,
            env_reader=self._env_reader,
        )
        if self._config is None:
            raise LinearWorkspaceProviderConfigError(
                "Linear workspace provider is enabled but no Linear config was found"
            )
        if self._preflight_credentials:
            preflight_linear_provider_credentials(
                self._config,
                credential_checker=self._credential_checker,
            )

    def provider_tool_access(self) -> ProviderToolAccessPolicy:
        """Return Linear CAO-mediated MCP tool access."""
        config = self._load_config()
        return LinearToolProvider(
            config=config,
            agent_registry=self._agent_registry,
        ).provider_tool_access()

    def _load_config(self) -> LinearProviderConfig:
        if self._config is None:
            self.initialize()
        if self._config is None:
            raise LinearWorkspaceProviderConfigError("Linear workspace provider is not configured")
        return self._config

    def resolve_presence(
        self,
        *,
        app_key: Optional[str] = None,
        app_user_id: Optional[str] = None,
        app_user_name: Optional[str] = None,
    ) -> LinearPresence:
        config = self._load_config()
        presence: Optional[LinearPresence] = None
        if app_key:
            presence = config.presence_by_app_key(app_key)
            if presence is None:
                raise LinearWorkspaceProviderConfigError(f"Unknown Linear app key: {app_key}")
        if app_user_id:
            by_user = config.presence_by_app_user_id(app_user_id)
            if by_user is None and presence is None:
                raise LinearWorkspaceProviderConfigError(
                    f"Unknown Linear app user id: {app_user_id}"
                )
            if by_user is not None and presence is not None and presence != by_user:
                raise LinearWorkspaceProviderConfigError(
                    "Linear app key and app user id resolve to different CAO identities"
                )
            if by_user is not None:
                presence = by_user
        if app_user_name:
            by_name = config.presence_by_app_user_name(app_user_name)
            if by_name is not None and presence is not None and presence != by_name:
                raise LinearWorkspaceProviderConfigError(
                    "Linear app key and app user name resolve to different CAO identities"
                )
            if presence is None:
                presence = by_name
        if presence is None:
            raise LinearWorkspaceProviderConfigError(
                "Linear presence could not be resolved from app key or app user id"
            )
        return presence

    def resolve_presence_from_payload(self, payload: Mapping[str, Any]) -> LinearPresence:
        return self.resolve_presence(
            app_key=_extract_app_key(payload),
            app_user_id=_extract_app_user_id(payload),
            app_user_name=_extract_app_user_name(payload),
        )

    def resolve_agent_for_presence(self, presence: LinearPresence) -> Agent:
        return self._agent_registry.get(presence.agent_id)

    def resolve_agent_for_agent_id(self, agent_id: str) -> Agent:
        """Resolve a CAO agent through this provider's presence mapping."""
        config = self._load_config()
        presence = next(
            (
                candidate
                for candidate in config.presences.values()
                if candidate.agent_id == agent_id
            ),
            None,
        )
        if presence is None:
            raise LinearWorkspaceProviderConfigError(
                f"Linear provider has no presence for CAO agent: {agent_id}"
            )
        return self.resolve_agent_for_presence(presence)

    def list_agents(self) -> tuple[Agent, ...]:
        """Return provider-backed CAO agents from configured Linear presences."""
        config = self._load_config()
        identities: dict[str, Agent] = {}
        for presence in config.presences.values():
            agent = self.resolve_agent_for_presence(presence)
            identities[agent.id] = agent
        return tuple(identities[key] for key in sorted(identities))

    def resolve_event(self, payload: Mapping[str, Any]) -> LinearResolvedPresence:
        presence = self.resolve_presence_from_payload(payload)
        return LinearResolvedPresence(
            presence=presence,
            agent=self.resolve_agent_for_presence(presence),
        )


def canonical_session_name(session_name: str) -> str:
    """Return a CAO tmux session name with the managed prefix."""
    if session_name.startswith(SESSION_PREFIX):
        return session_name
    return f"{SESSION_PREFIX}{session_name}"


def set_default_linear_workspace_provider(provider: LinearWorkspaceProvider) -> None:
    """Set the startup-validated Linear provider used by routes/runtime."""
    global _default_linear_workspace_provider
    _default_linear_workspace_provider = provider


def get_linear_workspace_provider() -> LinearWorkspaceProvider:
    """Return the startup provider when available, else a lazy compatibility provider."""
    if _default_linear_workspace_provider is not None:
        return _default_linear_workspace_provider
    return LinearWorkspaceProvider()


def should_enable_linear_agent_policies() -> bool:
    """Return whether Linear's WIP agent-presence policy guardrails should run."""
    try:
        return get_linear_workspace_provider().agent_policies_enabled()
    except LinearWorkspaceProviderConfigError:
        return False


def webhook_secret_presences(
    *,
    agents_root: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> Iterable[LinearPresence]:
    """Yield configured Linear presences that can verify webhooks."""
    config = load_linear_provider_config(
        agents_root=agents_root,
        env_reader=env_reader,
    )
    if config is None:
        return []
    return [presence for presence in config.presences.values() if presence.webhook_secret]


def should_enable_linear_routes() -> bool:
    """Return whether Linear routes should be available for this CAO process.

    Agent-owned Linear config is the hard-cutover route source.
    """
    try:
        return load_linear_provider_config() is not None
    except LinearWorkspaceProviderConfigError:
        raise
    except Exception:
        return False

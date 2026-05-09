"""Integration proof for provider-owned runtime state across terminal refresh."""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import NotFoundError

from cli_agent_orchestrator.agent_identity import AgentIdentity, AgentIdentityRegistry
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear import runtime as linear_runtime
from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider
from cli_agent_orchestrator.linear.provider_tools import (
    CREATE_COMMENT_TOOL,
    CREATE_ISSUE_TOOL,
    GET_ISSUE_TOOL,
    LIST_COMMENTS_TOOL,
    UPDATE_ISSUE_TOOL,
)
from cli_agent_orchestrator.linear.workspace_provider import LinearWorkspaceProvider
from cli_agent_orchestrator.mcp_server.provider_tools import register_provider_mediated_mcp_tools
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.presence.manager import PresenceProviderManager
from cli_agent_orchestrator.providers.base import (
    BaseProvider,
    ProviderRuntimeDescriptor,
    ProviderRuntimePreparation,
    ProviderRuntimeState,
)
from cli_agent_orchestrator.runtime import agent as runtime_agent
from cli_agent_orchestrator.runtime.agent import AgentRuntimeFreshnessAction, AgentRuntimeHandle

pytestmark = pytest.mark.integration


TEST_RUNTIME_SCHEMA_VERSION = "integration-test-provider-runtime-state.v1"


def _payload(thread_id: str) -> dict[str, str]:
    return {
        "schema_version": TEST_RUNTIME_SCHEMA_VERSION,
        "thread_id": thread_id,
    }


class TmuxRuntimeStateCapability:
    """Test provider capability that discovers state through real tmux output."""

    def __init__(self) -> None:
        self.discovered_terminal_ids: list[str] = []
        self.deserialized_payloads: list[dict[str, str]] = []
        self.resume_args: list[list[str]] = []

    def discover_current_runtime_state(
        self,
        *,
        terminal_id: str,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState | None:
        self.discovered_terminal_ids.append(terminal_id)
        metadata = db_module.get_terminal_metadata(terminal_id)
        if metadata is None:
            raise ValueError(f"Terminal {terminal_id} not found")
        output = tmux_client.get_history(metadata["tmux_session"], metadata["tmux_window"])
        match = re.search(r"READY thread=(\S+)", output)
        if match is None:
            return None
        return ProviderRuntimeState(
            provider_type="codex",
            provider_data_dir=provider_data_dir,
            payload=_payload(match.group(1)),
        )

    def deserialize_runtime_state(
        self,
        payload,
        *,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState:
        self.deserialized_payloads.append(dict(payload))
        if payload.get("schema_version") != TEST_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unexpected test provider runtime schema")
        thread_id = payload.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            raise ValueError("test provider runtime requires thread_id")
        return ProviderRuntimeState(
            provider_type="codex",
            provider_data_dir=provider_data_dir,
            payload=_payload(thread_id),
        )

    def serialize_runtime_state(self, state: ProviderRuntimeState):
        return dict(state.payload)

    def launch_resume_args(
        self,
        state: ProviderRuntimeState,
        *,
        provider_data_dir: Path,
    ) -> list[str]:
        args = ["--resume-thread", str(state.payload["thread_id"])]
        self.resume_args.append(args)
        return args


class TmuxTestProvider(BaseProvider):
    """Small provider that proves CAO composition without launching model CLIs."""

    provider_type = "codex"

    def __init__(
        self,
        terminal_id: str,
        session_name: str,
        window_name: str,
        *,
        runtime_resume_args: list[str] | None,
    ) -> None:
        super().__init__(terminal_id, session_name, window_name)
        self._runtime_resume_args = runtime_resume_args or []

    def initialize(self) -> bool:
        thread_id = "session-a"
        if self._runtime_resume_args:
            thread_id = self._runtime_resume_args[-1]
        tmux_client.send_keys(
            self.session_name,
            self.window_name,
            f"printf 'READY thread={thread_id} terminal={self.terminal_id}\\n'",
        )
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if "READY thread=" in tmux_client.get_history(self.session_name, self.window_name):
                break
            time.sleep(0.1)
        return True

    def get_status(self, tail_lines=None) -> TerminalStatus:
        output = tmux_client.get_history(self.session_name, self.window_name)
        return TerminalStatus.IDLE if "READY thread=" in output else TerminalStatus.PROCESSING

    def get_idle_pattern_for_log(self) -> str:
        return "READY thread="

    def extract_last_message_from_script(self, script_output: str) -> str:
        return script_output

    def exit_cli(self) -> str:
        return "exit"

    def cleanup(self) -> None:
        return None


@dataclass
class TmuxRuntimeProviderWorld:
    """Installed test provider wiring shared by runtime and Linear boundary tests."""

    capability: TmuxRuntimeStateCapability
    runtime_version: dict[str, str]
    created_providers: dict[str, TmuxTestProvider]


@pytest.fixture
def tmux_runtime_provider_world(monkeypatch: pytest.MonkeyPatch) -> TmuxRuntimeProviderWorld:
    capability = TmuxRuntimeStateCapability()
    runtime_version = {"value": "v1"}
    created_providers: dict[str, TmuxTestProvider] = {}

    def runtime_descriptor(provider_type: str, *, launch_context):
        return ProviderRuntimeDescriptor(
            schema_version="integration-test-provider-runtime.v1",
            material={"runtime_version": runtime_version["value"]},
        )

    def create_provider(
        provider_type,
        terminal_id,
        tmux_session,
        tmux_window,
        agent_profile=None,
        allowed_tools=None,
        skill_prompt=None,
        runtime_resume_args=None,
    ):
        provider = TmuxTestProvider(
            terminal_id,
            tmux_session,
            tmux_window,
            runtime_resume_args=runtime_resume_args,
        )
        created_providers[terminal_id] = provider
        return provider

    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.provider_manager.prepare_terminal_runtime",
        lambda *args, **kwargs: ProviderRuntimePreparation(),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
        create_provider,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.provider_manager.runtime_fingerprint_contribution",
        runtime_descriptor,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.provider_manager.runtime_state_capability",
        lambda provider_type: capability,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.provider_manager.runtime_state_capability",
        lambda provider_type: capability,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.provider_manager.cleanup_provider",
        lambda terminal_id: created_providers.pop(terminal_id, None),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.provider_manager.cleanup_terminal_runtime",
        lambda provider_type, terminal_id: None,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.provider_manager.get_provider",
        lambda terminal_id: created_providers.get(terminal_id),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.provider_manager.get_provider",
        lambda terminal_id: created_providers.get(terminal_id),
    )

    return TmuxRuntimeProviderWorld(
        capability=capability,
        runtime_version=runtime_version,
        created_providers=created_providers,
    )


@pytest.fixture
def integration_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AgentIdentity:
    monkeypatch.setattr(
        "cli_agent_orchestrator.agent_identity.AGENT_IDENTITY_DATA_ROOT",
        tmp_path / "agents",
    )
    workdir = tmp_path / "repo"
    workdir.mkdir()
    return AgentIdentity(
        id="cao47_integration_agent",
        display_name="CAO-47 Integration Agent",
        agent_profile="developer",
        cli_provider="codex",
        workdir=str(workdir),
        session_name=f"cao47-runtime-{uuid.uuid4().hex[:8]}",
    )


def _linear_agent_session_payload(
    *,
    session_id: str,
    activity_id: str,
    body: str,
    prompt_context: str,
    issue_id: str = "issue-49",
    issue_identifier: str = "CAO-49",
    issue_title: str = "Prove resume-aware refresh at the Linear delivery boundary",
) -> dict[str, object]:
    return {
        "type": "AgentSessionEvent",
        "action": "prompted",
        "_cao_linear_app_key": "discovery_partner",
        "data": {
            "promptContext": prompt_context,
            "agentSession": {
                "id": session_id,
                "url": f"https://linear.app/agent-session/{session_id}",
                "issue": {
                    "id": issue_id,
                    "identifier": issue_identifier,
                    "title": issue_title,
                    "url": f"https://linear.app/yards-framework/issue/{issue_identifier}",
                },
            },
            "agentActivity": {
                "id": activity_id,
                "actor": {"name": "RJ Wilson"},
                "content": {
                    "type": "prompt",
                    "body": body,
                },
            },
        },
    }


def _install_linear_workspace_provider(
    *,
    identity: AgentIdentity,
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_access: str = "",
) -> LinearWorkspaceProvider:
    config_path.write_text("""
[presences.discovery_partner]
agent_id = "{agent_id}"
app_key = "discovery_partner"
app_user_name = "Discovery Partner"
access_token = "integration-access-token"

{tool_access}
""".format(agent_id=identity.id, tool_access=tool_access))
    workspace_provider = LinearWorkspaceProvider(
        agent_registry=AgentIdentityRegistry({identity.id: identity}),
        config_path=config_path,
        preflight_credentials=False,
    )
    monkeypatch.setattr(
        linear_runtime,
        "get_linear_workspace_provider",
        lambda: workspace_provider,
    )
    return workspace_provider


def _history_contains(session_name: str, window_name: str, expected: str) -> bool:
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if expected in tmux_client.get_history(session_name, window_name):
            return True
        time.sleep(0.1)
    return False


async def _registered_tool_names(mcp: FastMCP) -> set[str]:
    return {tool.name for tool in await mcp.list_tools()}


def _issue_payload(
    *,
    id: str = "issue-52",
    identifier: str = "CAO-52",
    title: str = "Prove CAO-mediated Linear tooling end to end",
) -> dict[str, object]:
    return {
        "id": id,
        "identifier": identifier,
        "title": title,
        "description": "Vertical proof for CAO-mediated Linear tooling.",
        "url": f"https://linear.app/yards-framework/issue/{identifier.lower()}/example",
        "createdAt": "2026-05-08T12:23:34.210Z",
        "updatedAt": "2026-05-09T03:57:31.884Z",
        "archivedAt": None,
        "state": {"name": "In Progress", "type": "started"},
        "team": {"key": "CAO", "name": "CAO"},
        "project": {"name": "Linear-backed CAO agent bridge"},
        "assignee": {"name": "CAO-52 Agent"},
    }


def _comments_payload() -> dict[str, object]:
    return {
        **_issue_payload(),
        "comments": {
            "nodes": [
                {
                    "id": "comment-plan",
                    "body": "Use real runtime and provider-mediated MCP surfaces.",
                    "createdAt": "2026-05-09T03:57:31.911Z",
                    "updatedAt": "2026-05-09T03:57:31.884Z",
                    "user": {"id": "user-rj", "name": "RJ Wilson"},
                }
            ]
        },
    }


def _mutated_issue_payload(
    *,
    id: str = "issue-created-52",
    identifier: str = "CAO-520",
    title: str = "CAO-52 follow-up",
) -> dict[str, object]:
    return {
        "id": id,
        "identifier": identifier,
        "title": title,
        "url": f"https://linear.app/yards-framework/issue/{identifier.lower()}/example",
        "state": {"name": "Todo", "type": "unstarted"},
        "team": {"key": "CAO", "name": "CAO"},
        "project": {"name": "Linear-backed CAO agent bridge"},
    }


def test_stale_identity_refresh_restores_provider_runtime_with_real_tmux_delivery(
    runtime_inbox_db_session,
    integration_identity: AgentIdentity,
    tmux_runtime_provider_world: TmuxRuntimeProviderWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    handle = AgentRuntimeHandle(integration_identity)
    session_name = handle.session_name
    try:
        initial_start = handle.ensure_fresh_started()
        assert initial_start.ready is True
        initial_terminal = handle.current_terminal()
        assert initial_terminal is not None
        assert initial_terminal.id in tmux_runtime_provider_world.created_providers
        initial_output = tmux_client.get_history(
            initial_terminal.session_name,
            initial_terminal.window_name,
        )
        assert "READY thread=session-a" in initial_output
        initial_state = json.loads(handle._runtime_state_path().read_text())
        assert initial_state["provider_runtime"] == _payload("session-a")

        tmux_runtime_provider_world.runtime_version["value"] = "v2"
        result = handle.notify(
            "echo CAO47_DELIVERED_THROUGH_REFRESH",
            source_kind="integration",
            source_id="cao-47-real-tmux-delivery",
        )

        assert result.freshness is not None
        assert result.freshness.action == AgentRuntimeFreshnessAction.RESTARTED
        assert result.delivery.delivered is True
        assert result.terminal_id is not None
        assert result.terminal_id != initial_terminal.id
        assert tmux_runtime_provider_world.capability.deserialized_payloads == [
            _payload("session-a")
        ]
        assert tmux_runtime_provider_world.capability.resume_args == [
            ["--resume-thread", "session-a"]
        ]

        refreshed_terminal = handle.current_terminal()
        assert refreshed_terminal is not None
        refreshed_output = tmux_client.get_history(
            refreshed_terminal.session_name,
            refreshed_terminal.window_name,
        )
        assert "READY thread=session-a" in refreshed_output
        assert "CAO47_DELIVERED_THROUGH_REFRESH" in refreshed_output

        final_state = json.loads(handle._runtime_state_path().read_text())
        assert final_state["terminal_id"] == refreshed_terminal.id
        assert final_state["provider_runtime"] == _payload("session-a")
    finally:
        tmux_client.kill_session(session_name)


def test_stale_mcp_runtime_generation_refreshes_and_resumes_before_delivery(
    runtime_inbox_db_session,
    integration_identity: AgentIdentity,
    tmux_runtime_provider_world: TmuxRuntimeProviderWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    mcp_runtime_generation = {"value": "mcp-v1"}
    monkeypatch.setattr(
        runtime_agent,
        "_mcp_surface_fingerprint_for_identity",
        lambda identity: "mcp-surface-v1",
    )
    monkeypatch.setattr(
        runtime_agent,
        "_mcp_runtime_generation_fingerprint_for_identity",
        lambda identity: mcp_runtime_generation["value"],
    )

    handle = AgentRuntimeHandle(integration_identity)
    session_name = handle.session_name
    try:
        initial_start = handle.ensure_fresh_started()
        assert initial_start.ready is True
        initial_terminal = handle.current_terminal()
        assert initial_terminal is not None

        mcp_runtime_generation["value"] = "mcp-v2"
        result = handle.notify(
            "echo CAO59_DELIVERED_AFTER_MCP_REFRESH",
            source_kind="integration",
            source_id="cao-59-mcp-runtime-generation-refresh",
        )

        assert result.freshness is not None
        assert result.freshness.action == AgentRuntimeFreshnessAction.RESTARTED
        assert result.delivery.delivered is True
        assert result.terminal_id is not None
        assert result.terminal_id != initial_terminal.id
        assert tmux_runtime_provider_world.capability.resume_args == [
            ["--resume-thread", "session-a"]
        ]

        refreshed_terminal = handle.current_terminal()
        assert refreshed_terminal is not None
        refreshed_output = tmux_client.get_history(
            refreshed_terminal.session_name,
            refreshed_terminal.window_name,
        )
        assert "READY thread=session-a" in refreshed_output
        assert "CAO59_DELIVERED_AFTER_MCP_REFRESH" in refreshed_output
    finally:
        tmux_client.kill_session(session_name)


def test_linear_agent_session_prompt_survives_stale_refresh_with_exact_body(
    runtime_inbox_db_session,
    integration_identity: AgentIdentity,
    tmux_runtime_provider_world: TmuxRuntimeProviderWorld,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    _install_linear_workspace_provider(
        identity=integration_identity,
        config_path=tmp_path / "linear.toml",
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(
        linear_runtime.app_client,
        "public_cao_runtime_url",
        lambda terminal_id, agent_id=None: f"https://cao.local/terminals/{terminal_id}",
    )
    monkeypatch.setattr(
        linear_runtime.app_client,
        "update_agent_session_external_url",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        linear_runtime.app_client,
        "create_agent_activity",
        lambda *args, **kwargs: {"id": "activity-accepted"},
    )

    handle = AgentRuntimeHandle(integration_identity)
    session_name = handle.session_name
    try:
        assert handle.ensure_fresh_started().ready is True
        initial_terminal = handle.current_terminal()
        assert initial_terminal is not None

        tmux_runtime_provider_world.runtime_version["value"] = "linear-boundary-v2"
        prompt_body = "testing"
        prompt_context = (
            '<issue identifier="CAO-49"><title>Should stay breadcrumb context only</title>'
            "<description>Do not deliver this description as the prompt body.</description></issue>"
        )
        payload = _linear_agent_session_payload(
            session_id=f"linear-session-{uuid.uuid4().hex}",
            activity_id=f"activity-{uuid.uuid4().hex}",
            body=prompt_body,
            prompt_context=prompt_context,
        )
        manager = PresenceProviderManager({"linear": LinearPresenceProvider()})
        persisted_event = manager.ingest_event(
            "linear",
            payload,
            delivery_id=f"delivery-{uuid.uuid4().hex}",
        )
        event = manager.normalize_event("linear", payload)

        result = linear_runtime.notify_agent_for_persisted_event(persisted_event, event)

        assert result is not None
        assert result.freshness is not None
        assert result.freshness.action == AgentRuntimeFreshnessAction.RESTARTED
        assert result.delivery.delivered is True
        assert result.terminal_id is not None
        assert result.terminal_id != initial_terminal.id
        assert result.notification.delivery.message is not None
        assert result.notification.delivery.message.body == prompt_body
        assert result.notification.delivery.message.sender_id == "presence"

        refreshed_terminal = handle.current_terminal()
        assert refreshed_terminal is not None
        assert refreshed_terminal.id == result.terminal_id
        assert _history_contains(
            refreshed_terminal.session_name,
            refreshed_terminal.window_name,
            "Preview: testing",
        )
        refreshed_output = tmux_client.get_history(
            refreshed_terminal.session_name,
            refreshed_terminal.window_name,
        )
        assert "From: RJ Wilson" in refreshed_output
        assert "Issue: CAO-49 - Prove resume-aware refresh at the Linear delivery boundary" in (
            refreshed_output
        )
        assert "Linear started an AgentSession with prompt context" not in refreshed_output
        assert "Do not deliver this description as the prompt body" not in refreshed_output
        assert tmux_runtime_provider_world.capability.resume_args == [
            ["--resume-thread", "session-a"]
        ]
    finally:
        tmux_client.kill_session(session_name)


@pytest.mark.asyncio
async def test_linear_agent_session_terminal_uses_provider_mediated_linear_mcp_tools(
    runtime_inbox_db_session,
    integration_identity: AgentIdentity,
    tmux_runtime_provider_world: TmuxRuntimeProviderWorld,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    provider = _install_linear_workspace_provider(
        identity=integration_identity,
        config_path=tmp_path / "linear.toml",
        monkeypatch=monkeypatch,
        tool_access=f"""
[tool_access.cao52_vertical_proof]
agent_id = "{integration_identity.id}"
tools = [
  "{GET_ISSUE_TOOL}",
  "{LIST_COMMENTS_TOOL}",
  "{CREATE_COMMENT_TOOL}",
  "{CREATE_ISSUE_TOOL}",
  "{UPDATE_ISSUE_TOOL}",
]
issues = ["CAO-52", "issue-52"]
create_team_ids = ["CAO"]
allow_top_level_create = true
update_fields = ["title"]
""",
    )
    monkeypatch.setattr(
        linear_runtime.app_client,
        "public_cao_runtime_url",
        lambda terminal_id, agent_id=None: f"https://cao.local/terminals/{terminal_id}",
    )
    monkeypatch.setattr(
        linear_runtime.app_client,
        "update_agent_session_external_url",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        linear_runtime.app_client,
        "create_agent_activity",
        lambda *args, **kwargs: {"id": "activity-accepted"},
    )

    graphql_calls: list[dict[str, object]] = []

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        graphql_calls.append(
            {
                "query": query,
                "variables": variables,
                "access_token": access_token,
                "app_key": app_key,
            }
        )
        assert access_token == "integration-access-token"
        assert app_key == "discovery_partner"
        if "CaoLinearIssueComments" in query:
            assert variables == {"id": "CAO-52", "first": 5}
            return {"data": {"issue": _comments_payload()}}
        if "CaoLinearCreateComment" in query:
            assert variables == {
                "input": {"issueId": "issue-52", "body": "CAO-52 vertical proof comment."}
            }
            return {
                "data": {
                    "commentCreate": {
                        "success": True,
                        "comment": {
                            "id": "comment-created-52",
                            "url": "https://linear.app/yards-framework/issue/cao-52/example#comment",
                            "body": "CAO-52 vertical proof comment.",
                            "createdAt": "2026-05-09T04:10:00.000Z",
                            "updatedAt": "2026-05-09T04:10:00.000Z",
                            "issue": {
                                "id": "issue-52",
                                "identifier": "CAO-52",
                                "url": "https://linear.app/yards-framework/issue/cao-52/example",
                            },
                        },
                    }
                }
            }
        if "CaoLinearTeams" in query:
            assert variables == {}
            return {"data": {"teams": {"nodes": [{"id": "team-cao", "key": "CAO"}]}}}
        if "CaoLinearCreateIssue" in query:
            assert variables == {
                "input": {
                    "teamId": "team-cao",
                    "title": "CAO-52 follow-up",
                    "description": "Created through the CAO-mediated Linear MCP surface.",
                }
            }
            return {
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": _mutated_issue_payload(),
                    }
                }
            }
        if "CaoLinearUpdateIssue" in query:
            assert variables == {"id": "issue-52", "input": {"title": "CAO-52 proof updated"}}
            return {
                "data": {
                    "issueUpdate": {
                        "success": True,
                        "issue": _mutated_issue_payload(
                            id="issue-52",
                            identifier="CAO-52",
                            title="CAO-52 proof updated",
                        ),
                    }
                }
            }
        if "CaoLinearIssue" in query:
            assert variables == {"id": "CAO-52"}
            return {"data": {"issue": _issue_payload()}}
        raise AssertionError(f"unexpected Linear GraphQL query: {query}")

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)

    handle = AgentRuntimeHandle(integration_identity)
    session_name = handle.session_name
    try:
        assert handle.ensure_fresh_started().ready is True
        initial_terminal = handle.current_terminal()
        assert initial_terminal is not None

        tmux_runtime_provider_world.runtime_version["value"] = "linear-tools-v2"
        prompt_body = "Please prove CAO-52 Linear tool access."
        prompt_context = (
            '<issue identifier="CAO-52"><title>CAO-mediated Linear tooling</title>'
            "<description>This promptContext must stay out of the terminal body.</description>"
            "</issue>"
        )
        manager = PresenceProviderManager({"linear": LinearPresenceProvider()})
        payload = _linear_agent_session_payload(
            session_id=f"linear-session-{uuid.uuid4().hex}",
            activity_id=f"activity-{uuid.uuid4().hex}",
            body=prompt_body,
            prompt_context=prompt_context,
            issue_id="issue-52",
            issue_identifier="CAO-52",
            issue_title="Prove CAO-mediated Linear tooling end to end",
        )
        persisted_event = manager.ingest_event(
            "linear",
            payload,
            delivery_id=f"delivery-{uuid.uuid4().hex}",
        )
        event = manager.normalize_event("linear", payload)

        result = linear_runtime.notify_agent_for_persisted_event(persisted_event, event)

        assert result is not None
        assert result.freshness is not None
        assert result.freshness.action == AgentRuntimeFreshnessAction.RESTARTED
        assert result.delivery.delivered is True
        assert result.terminal_id is not None
        assert result.terminal_id != initial_terminal.id
        assert result.notification.delivery.message is not None
        assert result.notification.delivery.message.body == prompt_body
        assert result.notification.delivery.message.sender_id == "presence"

        refreshed_terminal = handle.current_terminal()
        assert refreshed_terminal is not None
        assert refreshed_terminal.id == result.terminal_id
        assert _history_contains(
            refreshed_terminal.session_name,
            refreshed_terminal.window_name,
            "Preview: Please prove CAO-52 Linear tool access.",
        )
        refreshed_output = tmux_client.get_history(
            refreshed_terminal.session_name,
            refreshed_terminal.window_name,
        )
        assert "From: RJ Wilson" in refreshed_output
        assert "Issue: CAO-52 - Prove CAO-mediated Linear tooling end to end" in (refreshed_output)
        assert "Linear started an AgentSession with prompt context" not in refreshed_output
        assert "This promptContext must stay out of the terminal body" not in refreshed_output

        policy = provider.provider_tool_access()
        mcp = FastMCP("cao52-linear-vertical", mask_error_details=False)
        registered = register_provider_mediated_mcp_tools(
            terminal_id=refreshed_terminal.id,
            mcp_instance=mcp,
            policies={"linear": policy},
            agent_registry=AgentIdentityRegistry({integration_identity.id: integration_identity}),
        )

        assert registered == [
            CREATE_COMMENT_TOOL,
            CREATE_ISSUE_TOOL,
            GET_ISSUE_TOOL,
            LIST_COMMENTS_TOOL,
            UPDATE_ISSUE_TOOL,
        ]
        assert await _registered_tool_names(mcp) == set(registered)

        issue_result = await mcp.call_tool(GET_ISSUE_TOOL, {"issue": "CAO-52"})
        comments_result = await mcp.call_tool(
            LIST_COMMENTS_TOOL,
            {"issue": "CAO-52", "limit": 5},
        )
        comment_result = await mcp.call_tool(
            CREATE_COMMENT_TOOL,
            {"issue": "CAO-52", "body": "CAO-52 vertical proof comment."},
        )
        created_issue_result = await mcp.call_tool(
            CREATE_ISSUE_TOOL,
            {
                "team_id": "CAO",
                "title": "CAO-52 follow-up",
                "description": "Created through the CAO-mediated Linear MCP surface.",
            },
        )
        updated_issue_result = await mcp.call_tool(
            UPDATE_ISSUE_TOOL,
            {"issue": "CAO-52", "title": "CAO-52 proof updated"},
        )

        assert json.loads(issue_result.content[0].text)["identifier"] == "CAO-52"
        assert json.loads(comments_result.content[0].text)["comments"] == [
            {
                "id": "comment-plan",
                "body": "Use real runtime and provider-mediated MCP surfaces.",
                "author": {"id": "user-rj", "name": "RJ Wilson"},
                "created_at": "2026-05-09T03:57:31.911Z",
                "updated_at": "2026-05-09T03:57:31.884Z",
            }
        ]
        assert json.loads(comment_result.content[0].text)["id"] == "comment-created-52"
        assert json.loads(created_issue_result.content[0].text)["status"] == "created"
        assert json.loads(updated_issue_result.content[0].text) == {
            "status": "updated",
            "id": "issue-52",
            "identifier": "CAO-52",
            "title": "CAO-52 proof updated",
            "url": "https://linear.app/yards-framework/issue/cao-52/example",
            "team": {"key": "CAO", "name": "CAO"},
            "project": {"name": "Linear-backed CAO agent bridge"},
            "state": {"name": "Todo", "type": "unstarted"},
            "changed_fields": ["title"],
        }

        raw_terminal_id = f"raw-cao52-{uuid.uuid4().hex}"
        db_module.create_terminal(
            raw_terminal_id,
            "cao52-raw-session",
            "cao52-raw-window",
            "codex",
            "developer",
        )
        raw_mcp = FastMCP("cao52-linear-raw", mask_error_details=False)
        raw_registered = register_provider_mediated_mcp_tools(
            terminal_id=raw_terminal_id,
            mcp_instance=raw_mcp,
            policies={"linear": policy},
            agent_registry=AgentIdentityRegistry({integration_identity.id: integration_identity}),
        )

        assert raw_registered == []
        assert await _registered_tool_names(raw_mcp) == set()
        with pytest.raises(NotFoundError, match=GET_ISSUE_TOOL):
            await raw_mcp.call_tool(GET_ISSUE_TOOL, {"issue": "CAO-52"})
        assert all(call["app_key"] == "discovery_partner" for call in graphql_calls)
    finally:
        tmux_client.kill_session(session_name)

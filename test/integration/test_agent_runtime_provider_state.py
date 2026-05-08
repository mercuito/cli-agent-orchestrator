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

from cli_agent_orchestrator.agent_identity import AgentIdentity, AgentIdentityRegistry
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.linear import runtime as linear_runtime
from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider
from cli_agent_orchestrator.linear.workspace_provider import LinearWorkspaceProvider
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.presence.manager import PresenceProviderManager
from cli_agent_orchestrator.providers.base import (
    BaseProvider,
    ProviderRuntimeDescriptor,
    ProviderRuntimePreparation,
    ProviderRuntimeState,
)
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
                    "id": "issue-49",
                    "identifier": "CAO-49",
                    "title": "Prove resume-aware refresh at the Linear delivery boundary",
                    "url": "https://linear.app/yards-framework/issue/CAO-49",
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
) -> None:
    config_path.write_text("""
[presences.discovery_partner]
agent_id = "{agent_id}"
app_key = "discovery_partner"
app_user_name = "Discovery Partner"
""".format(agent_id=identity.id))
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


def _history_contains(session_name: str, window_name: str, expected: str) -> bool:
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if expected in tmux_client.get_history(session_name, window_name):
            return True
        time.sleep(0.1)
    return False


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

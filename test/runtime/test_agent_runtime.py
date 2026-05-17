"""Tests for the CAO-owned provider-facing agent runtime handle."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from cli_agent_orchestrator.agent import write_agent
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import create_inbox_delivery
from cli_agent_orchestrator.events import CaoCorrelationId, CaoEventDispatcher, CaoEventId
from cli_agent_orchestrator.linear.workspace_events import LinearAgentMentionedEvent
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.base import ProviderRuntimeDescriptor, ProviderRuntimeState
from cli_agent_orchestrator.runtime import agent as runtime_agent
from cli_agent_orchestrator.runtime import events as runtime_events
from cli_agent_orchestrator.runtime.agent import (
    AgentRuntimeFreshnessAction,
    AgentRuntimeHandle,
    AgentRuntimeInvariantError,
    AgentRuntimeNotification,
    AgentRuntimeStatus,
)
from cli_agent_orchestrator.runtime.events import (
    AgentRuntimeLifecycleEvent,
    AgentRuntimeNotificationAcceptedEvent,
    AgentRuntimeNotificationDeliveryEvent,
    AgentRuntimeWorkspaceContextSwitchEvent,
)
from cli_agent_orchestrator.services import inbox_service


@pytest.fixture
def test_session(
    runtime_inbox_db_session,
    tmp_path,
    monkeypatch,
    implementation_partner_agent_factory,
    agent_manager_factory,
):
    monkeypatch.setattr(
        "cli_agent_orchestrator.agent.AGENTS_ROOT",
        tmp_path / "agents",
    )
    monkeypatch.setattr(runtime_agent.provider_manager, "runtime_state_capability", lambda _: None)
    agent = implementation_partner_agent_factory()
    write_agent(agent, agents_root=tmp_path / "agents")
    agent_manager = agent_manager_factory(agent)
    monkeypatch.setattr(
        runtime_agent,
        "default_agent_manager",
        lambda: agent_manager,
    )
    monkeypatch.setattr(
        runtime_agent,
        "_mcp_surface_fingerprint_for_agent",
        lambda agent: "surface-v1",
    )
    monkeypatch.setattr(
        runtime_agent,
        "_mcp_runtime_generation_fingerprint_for_agent",
        lambda agent: "runtime-generation-v1",
    )
    return runtime_inbox_db_session


@pytest.fixture
def agent(implementation_partner_agent_factory):
    return implementation_partner_agent_factory()


@pytest.fixture
def handle(agent) -> AgentRuntimeHandle:
    return AgentRuntimeHandle(agent)


@pytest.fixture
def recorded_runtime_events(monkeypatch):
    dispatcher = CaoEventDispatcher()
    runtime_events.register_runtime_cao_events(dispatcher)
    published = []
    dispatcher.subscribe_all(
        handler=lambda event: published.append(event),
        subscription_id="test-runtime-events",
    )
    monkeypatch.setattr(runtime_events, "default_cao_event_dispatcher", lambda: dispatcher)
    return published


def _create_terminal(session_name: str = "cao-implementation-partner") -> str:
    return db_module.create_terminal(
        "terminal-1",
        session_name,
        "developer-1234",
        "codex",
        agent_id="implementation_partner",
        workspace_context_id=_default_workspace_context_id(),
    )["id"]


def _default_workspace_context_id(agent_id: str = "implementation_partner") -> str:
    return db_module.ensure_default_workspace_context(agent_id).id


def _mark_terminal_fresh(handle: AgentRuntimeHandle, terminal_id: str = "terminal-1") -> None:
    handle._write_applied_runtime_state(terminal_id, handle._desired_runtime_fingerprint())


def _created_terminal_result(terminal_id: str, window_name: str = "developer-5678") -> Mock:
    return Mock(
        id=terminal_id,
        session_name="cao-implementation-partner",
        name=window_name,
        provider=Mock(value="codex"),
        agent_id="developer",
    )


def _provider(terminal_provider_patcher, status: TerminalStatus | Exception | None) -> None:
    terminal_provider_patcher(runtime_agent.provider_manager, status)


def _pending_deliveries(receiver_id: str):
    return db_module.list_pending_inbox_notifications(receiver_id, limit=10)


def _all_delivery_statuses(receiver_id: str) -> list[MessageStatus]:
    with db_module.SessionLocal() as session:
        rows = (
            session.query(db_module.InboxNotificationModel)
            .filter(db_module.InboxNotificationModel.receiver_id == receiver_id)
            .order_by(
                db_module.InboxNotificationModel.created_at.asc(),
                db_module.InboxNotificationModel.id.asc(),
            )
            .all()
        )
    return [MessageStatus(row.status) for row in rows]


def _provider_runtime_payload(thread_id: str) -> dict[str, str]:
    return {
        "schema_version": "test-provider-runtime-state.v1",
        "thread_id": thread_id,
    }


def _linear_causing_event() -> LinearAgentMentionedEvent:
    return LinearAgentMentionedEvent(
        event_id=CaoEventId("linear:event:mention-1"),
        correlation_id=CaoCorrelationId("linear-session-1"),
        agent_id="implementation_partner",
        message_id="message-1",
        thread_id="linear-session-1",
        message_body="Please handle this.",
    )


class RecordingRuntimeStateCapability:
    def __init__(self, *discover_results):
        self.discover_results = list(discover_results)
        self.discovered_terminal_ids: list[str] = []
        self.deserialized_payloads: list[dict[str, str]] = []
        self.serialized_payloads: list[dict[str, str]] = []
        self.resume_states: list[ProviderRuntimeState] = []
        self.saved_states: list[ProviderRuntimeState] = []
        self.cleared_provider_data_dirs = []

    def discover_current_runtime_state(self, *, terminal_id, provider_data_dir):
        self.discovered_terminal_ids.append(terminal_id)
        result = self.discover_results.pop(0) if self.discover_results else None
        if isinstance(result, Exception):
            raise result
        if result is None:
            return None
        return ProviderRuntimeState(
            provider_type="codex",
            provider_data_dir=provider_data_dir,
            payload=result,
        )

    def deserialize_runtime_state(self, payload, *, provider_data_dir):
        self.deserialized_payloads.append(dict(payload))
        if payload.get("schema_version") != "test-provider-runtime-state.v1":
            raise ValueError("bad test provider runtime schema")
        return ProviderRuntimeState(
            provider_type="codex",
            provider_data_dir=provider_data_dir,
            payload=dict(payload),
        )

    def serialize_runtime_state(self, state):
        payload = dict(state.payload)
        self.serialized_payloads.append(payload)
        return payload

    def launch_resume_args(self, state, *, provider_data_dir):
        self.resume_states.append(state)
        return ["--resume-thread", state.payload["thread_id"]]

    def load_runtime_state(self, *, provider_data_dir):
        for state in reversed(self.saved_states):
            if state.provider_data_dir == provider_data_dir:
                return state
        return None

    def save_runtime_state(self, state):
        self.saved_states.append(state)
        self.serialize_runtime_state(state)

    def clear_runtime_state(self, *, provider_data_dir):
        self.cleared_provider_data_dirs.append(provider_data_dir)


def test_status_reports_not_started_without_terminal_metadata(test_session, handle):
    assert handle.status() == AgentRuntimeStatus.NOT_STARTED


def test_agent_runtime_handle_uses_stable_default_workspace_context(test_session, agent):
    handle = AgentRuntimeHandle(agent)
    expected_context_id = db_module.default_workspace_context_id("implementation_partner")

    assert handle.workspace_context_id == expected_context_id
    assert handle.inbox_receiver_id == f"agent:implementation_partner:context:{expected_context_id}"
    assert (
        db_module.get_workspace_context_for_object(
            provider_id="cao",
            object_type="agent_default",
            object_id="implementation_partner",
        ).id
        == expected_context_id
    )


def test_current_terminal_ignores_raw_terminal_in_agent_session(test_session, handle):
    db_module.create_terminal(
        "terminal-1",
        "cao-implementation-partner",
        "developer-raw",
        "codex",
        agent_id="raw_agent",
        workspace_context_id=_default_workspace_context_id("raw_agent"),
    )

    assert handle.current_terminal() is None


@pytest.mark.parametrize(
    ("terminal_status", "runtime_status"),
    [
        (TerminalStatus.IDLE, AgentRuntimeStatus.IDLE),
        (TerminalStatus.PROCESSING, AgentRuntimeStatus.BUSY),
        (TerminalStatus.WAITING_USER_ANSWER, AgentRuntimeStatus.WAITING_USER),
        (TerminalStatus.COMPLETED, AgentRuntimeStatus.COMPLETED),
        (TerminalStatus.ERROR, AgentRuntimeStatus.ERROR),
    ],
)
def test_status_maps_terminal_state_to_provider_friendly_runtime_state(
    test_session,
    handle,
    terminal_status,
    runtime_status,
    terminal_provider_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, terminal_status)

    assert handle.status() == runtime_status


def test_status_reports_unreachable_when_provider_cannot_be_queried(
    test_session,
    handle,
    terminal_provider_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, RuntimeError("tmux unavailable"))

    assert handle.status() == AgentRuntimeStatus.UNREACHABLE


def test_ensure_started_creates_terminal_from_agent_when_not_started(
    test_session,
    monkeypatch,
    agent,
    handle,
):
    created = Mock(
        id="terminal-1",
        session_name="cao-implementation-partner",
        name="developer-1234",
        provider=Mock(value="codex"),
        agent_id="developer",
    )
    create_terminal_for_agent = Mock(return_value=created)
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.tmux_client.session_exists",
        lambda session: False,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.terminal_service.create_terminal_for_agent",
        create_terminal_for_agent,
    )

    terminal = handle.ensure_started()

    assert terminal.id == "terminal-1"
    create_terminal_for_agent.assert_called_once_with(
        agent.for_workspace_context(handle.workspace_context_id)
    )


def test_ensure_started_publishes_lifecycle_event_for_direct_start(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    recorded_runtime_events,
):
    monkeypatch.setattr(
        runtime_agent.tmux_client,
        "session_exists",
        lambda session: False,
    )
    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "create_terminal_for_agent",
        Mock(return_value=_created_terminal_result("terminal-1")),
    )
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)

    terminal = handle.ensure_started()

    assert terminal.id == "terminal-1"
    assert [type(event) for event in recorded_runtime_events] == [AgentRuntimeLifecycleEvent]
    lifecycle = recorded_runtime_events[0]
    assert isinstance(lifecycle, AgentRuntimeLifecycleEvent)
    assert lifecycle.action == AgentRuntimeFreshnessAction.STARTED.value
    assert lifecycle.runtime_status == AgentRuntimeStatus.IDLE.value
    assert lifecycle.terminal_id == "terminal-1"
    assert lifecycle.ready is True
    assert lifecycle.fresh is True
    assert lifecycle.agent_participants[0].agent_id == "implementation_partner"


def test_ensure_started_publishes_lifecycle_event_for_direct_reuse(
    test_session,
    handle,
    terminal_provider_patcher,
    recorded_runtime_events,
):
    _create_terminal()
    _mark_terminal_fresh(handle)
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)

    terminal = handle.ensure_started()

    assert terminal.id == "terminal-1"
    assert [type(event) for event in recorded_runtime_events] == [AgentRuntimeLifecycleEvent]
    lifecycle = recorded_runtime_events[0]
    assert isinstance(lifecycle, AgentRuntimeLifecycleEvent)
    assert lifecycle.action == AgentRuntimeFreshnessAction.REUSED.value
    assert lifecycle.runtime_status == AgentRuntimeStatus.IDLE.value
    assert lifecycle.terminal_id == "terminal-1"
    assert lifecycle.ready is True
    assert lifecycle.fresh is True
    assert lifecycle.agent_participants[0].agent_id == "implementation_partner"


def test_current_terminal_rejects_multiple_manifestations_for_agent(test_session, handle):
    db_module.create_terminal(
        "terminal-1",
        "cao-implementation-partner",
        "developer-1",
        "codex",
        agent_id="implementation_partner",
        workspace_context_id=_default_workspace_context_id(),
    )
    db_module.create_terminal(
        "terminal-2",
        "cao-implementation-partner",
        "developer-2",
        "codex",
        agent_id="implementation_partner",
        workspace_context_id=_default_workspace_context_id(),
    )

    with pytest.raises(AgentRuntimeInvariantError, match="Multiple terminal manifestations"):
        handle.current_terminal()


def test_context_runtime_uses_agent_and_workspace_context_route(
    test_session,
    monkeypatch,
    agent,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    context = db_module.ensure_workspace_context_for_boundary(
        resolver_id="linear_planning",
        provider_id="linear",
        object_type="issue",
        object_id="CAO-79",
    )
    handle = AgentRuntimeHandle(agent, workspace_context_id=context.id)
    db_module.create_terminal(
        "terminal-1",
        "cao-implementation-partner",
        "developer-context",
        "codex",
        agent_id="implementation_partner",
        workspace_context_id=context.id,
    )
    _mark_terminal_fresh(handle)
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)

    result = handle.notify(
        "Context-routed delivery.",
        source_kind="linear_event",
        source_id="event-context-a",
    )

    assert handle.inbox_receiver_id == f"agent:implementation_partner:context:{context.id}"
    assert result.terminal_id == "terminal-1"
    assert result.delivery.delivered is True
    send_input.assert_called_once_with("terminal-1", "Context-routed delivery.")


def test_context_runtime_ignores_terminals_for_other_contexts(test_session, agent):
    context_a = db_module.ensure_workspace_context_for_boundary(
        resolver_id="linear_planning",
        provider_id="linear",
        object_type="issue",
        object_id="CAO-79",
    )
    context_b = db_module.ensure_workspace_context_for_boundary(
        resolver_id="linear_planning",
        provider_id="linear",
        object_type="issue",
        object_id="CAO-80",
    )
    db_module.create_terminal(
        "terminal-1",
        "cao-implementation-partner",
        "developer-context-a",
        "codex",
        agent_id="implementation_partner",
        workspace_context_id=context_a.id,
    )

    assert (
        AgentRuntimeHandle(agent, workspace_context_id=context_b.id).current_terminal() is None
    )


def test_context_runtime_switches_by_stopping_other_agent_terminal(
    test_session,
    monkeypatch,
    agent,
    terminal_provider_patcher,
    terminal_send_patcher,
    recorded_runtime_events,
):
    context_a = db_module.ensure_workspace_context_for_boundary(
        resolver_id="linear_planning",
        provider_id="linear",
        object_type="issue",
        object_id="CAO-79",
    )
    context_b = db_module.ensure_workspace_context_for_boundary(
        resolver_id="linear_planning",
        provider_id="linear",
        object_type="issue",
        object_id="CAO-80",
    )
    handle_a = AgentRuntimeHandle(agent, workspace_context_id=context_a.id)
    handle_b = AgentRuntimeHandle(agent, workspace_context_id=context_b.id)
    db_module.create_terminal(
        "terminal-1",
        "cao-implementation-partner",
        "developer-context-a",
        "codex",
        agent_id="implementation_partner",
        workspace_context_id=context_a.id,
    )
    _mark_terminal_fresh(handle_a)
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    capability = RecordingRuntimeStateCapability(_provider_runtime_payload("session-a"), None)
    monkeypatch.setattr(
        runtime_agent.provider_manager,
        "runtime_state_capability",
        lambda provider: capability,
    )
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    monkeypatch.setattr(runtime_agent.tmux_client, "session_exists", lambda session: True)
    delete_terminal = Mock(
        side_effect=lambda terminal_id, **kwargs: db_module.delete_terminal(terminal_id)
    )
    monkeypatch.setattr(runtime_agent.terminal_service, "delete_terminal", delete_terminal)
    create_terminal = Mock()

    def create_target(agent):
        create_terminal(agent)
        db_module.create_terminal(
            "terminal-2",
            "cao-implementation-partner",
            "developer-context-b",
            "codex",
            agent_id="implementation_partner",
            workspace_context_id=context_b.id,
        )
        return _created_terminal_result("terminal-2", window_name="developer-context-b")

    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "create_terminal_for_agent",
        Mock(side_effect=create_target),
    )

    result = handle_b.notify(
        "Deliver in context B.",
        source_kind="linear_event",
        source_id="event-context-b",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.STARTED
    assert result.terminal_id == "terminal-2"
    assert result.delivery.delivered is True
    delete_terminal.assert_called_once_with("terminal-1", require_window_killed=True)
    assert capability.discovered_terminal_ids == ["terminal-1", "terminal-2"]
    assert capability.saved_states[0].payload == _provider_runtime_payload("session-a")
    assert db_module.get_terminal_metadata("terminal-1") is None
    assert db_module.get_terminal_metadata("terminal-2") is not None
    create_terminal.assert_called_once()
    assert create_terminal.call_args.args[0].current_workspace_context_id == context_b.id
    send_input.assert_called_once_with("terminal-2", "Deliver in context B.")
    switch_event = next(
        event
        for event in recorded_runtime_events
        if isinstance(event, AgentRuntimeWorkspaceContextSwitchEvent)
    )
    assert switch_event.agent_id == "implementation_partner"
    assert switch_event.from_workspace_context_id == context_a.id
    assert switch_event.to_workspace_context_id == context_b.id
    assert switch_event.terminal_id == "terminal-1"
    assert switch_event.runtime_status == AgentRuntimeStatus.IDLE.value
    assert switch_event.outcome == "succeeded"
    assert switch_event.agent_participants[0].agent_id == "implementation_partner"
    assert switch_event.agent_participants[0].role == (
        runtime_events.RUNTIME_AGENT_PARTICIPANT_ROLE_CONTEXT_SWITCH_AGENT
    )


def test_context_runtime_defers_switch_when_other_agent_terminal_is_busy(
    test_session,
    monkeypatch,
    agent,
    terminal_provider_patcher,
    terminal_send_patcher,
    recorded_runtime_events,
):
    context_a = db_module.ensure_workspace_context_for_boundary(
        resolver_id="linear_planning",
        provider_id="linear",
        object_type="issue",
        object_id="CAO-79",
    )
    context_b = db_module.ensure_workspace_context_for_boundary(
        resolver_id="linear_planning",
        provider_id="linear",
        object_type="issue",
        object_id="CAO-80",
    )
    db_module.create_terminal(
        "terminal-1",
        "cao-implementation-partner",
        "developer-context-a",
        "codex",
        agent_id="implementation_partner",
        workspace_context_id=context_a.id,
    )
    _provider(terminal_provider_patcher, TerminalStatus.PROCESSING)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    delete_terminal = Mock()
    create_terminal = Mock()
    monkeypatch.setattr(runtime_agent.terminal_service, "delete_terminal", delete_terminal)
    monkeypatch.setattr(runtime_agent.terminal_service, "create_terminal_for_agent", create_terminal)

    result = AgentRuntimeHandle(agent, workspace_context_id=context_b.id).notify(
        "Deliver later in context B.",
        source_kind="linear_event",
        source_id="event-context-b-busy",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.DEFERRED
    assert result.status == AgentRuntimeStatus.BUSY
    assert result.terminal_id == "terminal-1"
    assert result.delivery.delivered is False
    delete_terminal.assert_not_called()
    create_terminal.assert_not_called()
    send_input.assert_not_called()
    switch_event = next(
        event
        for event in recorded_runtime_events
        if isinstance(event, AgentRuntimeWorkspaceContextSwitchEvent)
    )
    assert switch_event.from_workspace_context_id == context_a.id
    assert switch_event.to_workspace_context_id == context_b.id
    assert switch_event.runtime_status == AgentRuntimeStatus.BUSY.value
    assert switch_event.outcome == "deferred"
    assert switch_event.agent_participants[0].agent_id == "implementation_partner"


def test_current_terminal_reports_resume_unsupported_for_provider_without_resume(
    test_session,
    implementation_partner_agent_factory,
    agent_manager_factory,
):
    agent = implementation_partner_agent_factory(cli_provider="kiro_cli")
    handle = AgentRuntimeHandle(
        agent,
        agent_manager=agent_manager_factory(agent),
    )
    db_module.create_terminal(
        "terminal-1",
        "cao-implementation-partner",
        "developer-1",
        "kiro_cli",
        agent_id="implementation_partner",
        workspace_context_id=_default_workspace_context_id(),
    )

    terminal = handle.current_terminal()

    assert terminal is not None
    assert terminal.resume_supported is False
    assert "does not support resume" in terminal.context_preservation


def test_notify_accepts_durable_inbox_state_when_startup_fails(
    test_session,
    monkeypatch,
    handle,
    recorded_runtime_events,
):
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.tmux_client.session_exists",
        lambda session: False,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.terminal_service.create_terminal_for_agent",
        Mock(side_effect=RuntimeError("cannot start")),
    )

    result = handle.notify(
        "Please inspect Linear session CAO-31.",
        source_kind="linear_event",
        source_id="event-1",
    )

    assert result.notification.created is True
    assert result.status == AgentRuntimeStatus.NOT_STARTED
    assert result.terminal_id is None
    assert "cannot start" in result.error
    deliveries = _pending_deliveries(handle.inbox_receiver_id)
    assert [(delivery.message.body, delivery.notification.status) for delivery in deliveries] == [
        ("Please inspect Linear session CAO-31.", MessageStatus.PENDING)
    ]
    assert [type(event) for event in recorded_runtime_events] == [
        AgentRuntimeNotificationAcceptedEvent,
        AgentRuntimeLifecycleEvent,
        AgentRuntimeNotificationDeliveryEvent,
    ]
    lifecycle = recorded_runtime_events[1]
    assert isinstance(lifecycle, AgentRuntimeLifecycleEvent)
    assert lifecycle.action == AgentRuntimeFreshnessAction.FAILED.value
    assert lifecycle.runtime_status == AgentRuntimeStatus.NOT_STARTED.value
    assert lifecycle.error == "cannot start"
    assert lifecycle.agent_participants[0].agent_id == "implementation_partner"
    delivery = recorded_runtime_events[2]
    assert isinstance(delivery, AgentRuntimeNotificationDeliveryEvent)
    assert delivery.outcome == "failed"
    assert delivery.attempted is False
    assert delivery.error == "cannot start"
    assert delivery.agent_participants[0].agent_id == "implementation_partner"


def test_offline_notification_moves_to_terminal_inbox_when_runtime_later_starts(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.terminal_service.create_terminal_for_agent",
        Mock(side_effect=RuntimeError("cannot start")),
    )
    handle.notify(
        "Persist me while the agent is offline.",
        source_kind="linear_event",
        source_id="event-offline",
    )
    assert _pending_deliveries(handle.inbox_receiver_id)[0].notification.status == (
        MessageStatus.PENDING
    )

    _create_terminal()
    _mark_terminal_fresh(handle)
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(inbox_service.terminal_service)

    result = handle.try_deliver_pending()

    assert result.delivered is True
    assert _pending_deliveries(handle.inbox_receiver_id) == []
    assert _all_delivery_statuses("terminal-1") == [MessageStatus.DELIVERED]
    send_input.assert_called_once_with("terminal-1", "Persist me while the agent is offline.")


def test_fresh_idle_runtime_is_reused_for_delivery(
    test_session,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _mark_terminal_fresh(handle)
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)

    result = handle.notify(
        "Deliver through a fresh terminal.",
        source_kind="linear_event",
        source_id="event-fresh",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.REUSED
    assert result.delivery.delivered is True
    send_input.assert_called_once_with("terminal-1", "Deliver through a fresh terminal.")


def test_notify_publishes_typed_runtime_events_with_provider_causation(
    test_session,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
    recorded_runtime_events,
):
    _create_terminal()
    _mark_terminal_fresh(handle)
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    terminal_send_patcher(runtime_agent.terminal_service)
    causing_event = _linear_causing_event()

    result = handle.notify(
        "Deliver provider-caused notification.",
        source_kind="linear_event",
        source_id="event-runtime-causation",
        causing_event=causing_event,
    )

    assert result.delivery.delivered is True
    assert [type(event) for event in recorded_runtime_events] == [
        AgentRuntimeNotificationAcceptedEvent,
        AgentRuntimeLifecycleEvent,
        AgentRuntimeNotificationDeliveryEvent,
    ]
    accepted = recorded_runtime_events[0]
    assert isinstance(accepted, AgentRuntimeNotificationAcceptedEvent)
    assert accepted.agent_id == "implementation_partner"
    assert accepted.workspace_context_id == handle.workspace_context_id
    assert accepted.inbox_notification_id == result.notification.delivery.notification.id
    assert accepted.source_kind == "linear_event"
    assert accepted.source_id == "event-runtime-causation"
    assert accepted.agent_participants[0].agent_id == "implementation_partner"
    assert accepted.agent_participants[0].role == (
        runtime_events.RUNTIME_AGENT_PARTICIPANT_ROLE_NOTIFICATION_RECEIVER
    )
    assert accepted.correlation_id == CaoCorrelationId("linear-session-1")
    assert accepted.causation_id == "linear:event:mention-1"

    lifecycle = recorded_runtime_events[1]
    assert isinstance(lifecycle, AgentRuntimeLifecycleEvent)
    assert lifecycle.action == AgentRuntimeFreshnessAction.REUSED.value
    assert lifecycle.runtime_status == AgentRuntimeStatus.IDLE.value
    assert lifecycle.terminal_id == "terminal-1"
    assert lifecycle.ready is True
    assert lifecycle.fresh is True
    assert lifecycle.agent_participants[0].role == (
        runtime_events.RUNTIME_AGENT_PARTICIPANT_ROLE_LIFECYCLE_AGENT
    )
    assert lifecycle.agent_participants[0].agent_id == "implementation_partner"
    assert lifecycle.correlation_id == CaoCorrelationId("linear-session-1")
    assert lifecycle.causation_id == "linear:event:mention-1"

    delivery = recorded_runtime_events[2]
    assert isinstance(delivery, AgentRuntimeNotificationDeliveryEvent)
    assert delivery.inbox_notification_id == result.notification.delivery.notification.id
    assert delivery.source_kind == "linear_event"
    assert delivery.message_body == "Deliver provider-caused notification."
    assert delivery.runtime_status == AgentRuntimeStatus.IDLE.value
    assert delivery.outcome == "delivered"
    assert delivery.attempted is True
    assert delivery.delivered is True
    assert delivery.error is None
    assert delivery.agent_participants[0].role == (
        runtime_events.RUNTIME_AGENT_PARTICIPANT_ROLE_DELIVERY_TARGET
    )
    assert delivery.agent_participants[0].agent_id == "implementation_partner"
    assert delivery.correlation_id == CaoCorrelationId("linear-session-1")
    assert delivery.causation_id == "linear:event:mention-1"


def test_changed_runtime_inputs_restart_idle_terminal_before_delivery(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    runtime_inputs_v1 = runtime_agent.terminal_service.TerminalRuntimeInputs(
        allowed_tools=["Read"],
        profile_material={"name": "developer", "system_prompt": "old prompt"},
    )
    runtime_inputs_v2 = runtime_agent.terminal_service.TerminalRuntimeInputs(
        allowed_tools=["Read"],
        profile_material={"name": "developer", "system_prompt": "new prompt"},
    )
    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "resolve_terminal_runtime_inputs",
        Mock(side_effect=[runtime_inputs_v1, runtime_inputs_v2]),
    )
    monkeypatch.setattr(
        runtime_agent.provider_manager,
        "runtime_fingerprint_contribution",
        Mock(
            return_value=ProviderRuntimeDescriptor(
                schema_version="test-provider-runtime.v1",
                material={"provider": "stable"},
            )
        ),
    )
    handle._write_applied_runtime_state("terminal-1", handle._desired_runtime_fingerprint())
    monkeypatch.setattr(runtime_agent.tmux_client, "session_exists", lambda session: True)
    delete_terminal = Mock(
        side_effect=lambda terminal_id, **kwargs: db_module.delete_terminal(terminal_id)
    )
    monkeypatch.setattr(runtime_agent.terminal_service, "delete_terminal", delete_terminal)

    def create_replacement(agent):
        db_module.create_terminal(
            "terminal-2",
            "cao-implementation-partner",
            "developer-5678",
            "codex",
            agent_id="implementation_partner",
            workspace_context_id=_default_workspace_context_id(),
        )
        return _created_terminal_result("terminal-2")

    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "create_terminal_for_agent",
        Mock(side_effect=create_replacement),
    )

    result = handle.notify(
        "Deliver after profile refresh.",
        source_kind="linear_event",
        source_id="event-profile-refresh",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.RESTARTED
    assert result.terminal_id == "terminal-2"
    assert result.delivery.delivered is True
    delete_terminal.assert_called_once_with("terminal-1", require_window_killed=True)
    send_input.assert_called_once_with("terminal-2", "Deliver after profile refresh.")


@pytest.mark.parametrize(
    ("surface_v2", "runtime_generation_v2", "message"),
    (
        ("surface-v2", "runtime-generation-v1", "Deliver after MCP surface refresh."),
        ("surface-v1", "runtime-generation-v2", "Deliver after MCP runtime refresh."),
    ),
)
def test_changed_mcp_freshness_restarts_idle_terminal_before_delivery(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
    surface_v2,
    runtime_generation_v2,
    message,
):
    _create_terminal()
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    handle._write_applied_runtime_state("terminal-1", handle._desired_runtime_fingerprint())
    monkeypatch.setattr(
        runtime_agent,
        "_mcp_surface_fingerprint_for_agent",
        lambda agent: surface_v2,
    )
    monkeypatch.setattr(
        runtime_agent,
        "_mcp_runtime_generation_fingerprint_for_agent",
        lambda agent: runtime_generation_v2,
    )
    monkeypatch.setattr(runtime_agent.tmux_client, "session_exists", lambda session: True)
    delete_terminal = Mock(
        side_effect=lambda terminal_id, **kwargs: db_module.delete_terminal(terminal_id)
    )
    monkeypatch.setattr(runtime_agent.terminal_service, "delete_terminal", delete_terminal)

    def create_replacement(agent):
        db_module.create_terminal(
            "terminal-2",
            "cao-implementation-partner",
            "developer-5678",
            "codex",
            agent_id="implementation_partner",
            workspace_context_id=_default_workspace_context_id(),
        )
        return _created_terminal_result("terminal-2")

    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "create_terminal_for_agent",
        Mock(side_effect=create_replacement),
    )

    result = handle.notify(
        message,
        source_kind="linear_event",
        source_id=f"event-{message}",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.RESTARTED
    assert result.terminal_id == "terminal-2"
    assert result.delivery.delivered is True
    delete_terminal.assert_called_once_with("terminal-1", require_window_killed=True)
    send_input.assert_called_once_with("terminal-2", message)


def test_stale_refresh_discovers_serializes_and_resumes_provider_runtime(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    capability = RecordingRuntimeStateCapability(
        _provider_runtime_payload("session-a"),
        _provider_runtime_payload("session-a"),
    )
    monkeypatch.setattr(
        runtime_agent.provider_manager,
        "runtime_state_capability",
        lambda provider: capability,
    )
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    monkeypatch.setattr(runtime_agent.tmux_client, "session_exists", lambda session: True)
    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "delete_terminal",
        Mock(side_effect=lambda terminal_id, **kwargs: db_module.delete_terminal(terminal_id)),
    )
    create_terminal = Mock()

    def create_replacement(agent):
        create_terminal(agent)
        db_module.create_terminal(
            "terminal-2",
            "cao-implementation-partner",
            "developer-5678",
            "codex",
            agent_id="implementation_partner",
            workspace_context_id=_default_workspace_context_id(),
        )
        return _created_terminal_result("terminal-2")

    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "create_terminal_for_agent",
        Mock(side_effect=create_replacement),
    )

    result = handle.notify(
        "Deliver after provider runtime refresh.",
        source_kind="linear_event",
        source_id="event-provider-runtime-refresh",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.RESTARTED
    assert capability.discovered_terminal_ids == ["terminal-1", "terminal-2"]
    assert capability.serialized_payloads == [
        _provider_runtime_payload("session-a"),
        _provider_runtime_payload("session-a"),
    ]
    assert create_terminal.call_args.args[0].current_workspace_context_id == handle.workspace_context_id
    assert result.delivery.delivered is True
    send_input.assert_called_once_with(
        "terminal-2",
        "Deliver after provider runtime refresh.",
    )
    state = json.loads(handle._runtime_state_path().read_text())
    assert state["terminal_id"] == "terminal-2"
    assert "provider_runtime" not in state
    assert capability.saved_states[-1].payload == _provider_runtime_payload("session-a")


def test_stale_refresh_with_no_current_session_restarts_without_resume_payload(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    capability = RecordingRuntimeStateCapability(None, None)
    monkeypatch.setattr(
        runtime_agent.provider_manager,
        "runtime_state_capability",
        lambda provider: capability,
    )
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    monkeypatch.setattr(runtime_agent.tmux_client, "session_exists", lambda session: True)
    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "delete_terminal",
        Mock(side_effect=lambda terminal_id, **kwargs: db_module.delete_terminal(terminal_id)),
    )
    create_terminal = Mock()

    def create_replacement(agent):
        create_terminal(agent)
        db_module.create_terminal(
            "terminal-2",
            "cao-implementation-partner",
            "developer-5678",
            "codex",
            agent_id="implementation_partner",
            workspace_context_id=_default_workspace_context_id(),
        )
        return _created_terminal_result("terminal-2")

    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "create_terminal_for_agent",
        Mock(side_effect=create_replacement),
    )

    result = handle.notify(
        "Deliver without provider resume.",
        source_kind="linear_event",
        source_id="event-no-current-session",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.RESTARTED
    assert create_terminal.call_args.args[0].current_workspace_context_id == handle.workspace_context_id
    assert capability.deserialized_payloads == []
    assert result.delivery.delivered is True
    send_input.assert_called_once_with("terminal-2", "Deliver without provider resume.")
    state = json.loads(handle._runtime_state_path().read_text())
    assert "provider_runtime" not in state
    assert capability.cleared_provider_data_dirs


def test_stale_refresh_surfaces_provider_discovery_failure_without_restarting(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    capability = RecordingRuntimeStateCapability(RuntimeError("probe failed"))
    monkeypatch.setattr(
        runtime_agent.provider_manager,
        "runtime_state_capability",
        lambda provider: capability,
    )
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    delete_terminal = Mock()
    create_terminal = Mock()
    monkeypatch.setattr(runtime_agent.terminal_service, "delete_terminal", delete_terminal)
    monkeypatch.setattr(runtime_agent.terminal_service, "create_terminal_for_agent", create_terminal)

    result = handle.notify(
        "Do not deliver after provider failure.",
        source_kind="linear_event",
        source_id="event-provider-failure",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.FAILED
    assert result.error == "probe failed"
    delete_terminal.assert_not_called()
    create_terminal.assert_not_called()
    send_input.assert_not_called()


def test_fresh_runtime_updates_agent_provider_runtime_cache(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _mark_terminal_fresh(handle)
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    capability = RecordingRuntimeStateCapability(_provider_runtime_payload("session-b"))
    monkeypatch.setattr(
        runtime_agent.provider_manager,
        "runtime_state_capability",
        lambda provider: capability,
    )
    send_input = terminal_send_patcher(runtime_agent.terminal_service)

    result = handle.notify(
        "Deliver after provider state changed.",
        source_kind="linear_event",
        source_id="event-provider-cache-update",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.REUSED
    send_input.assert_called_once_with("terminal-1", "Deliver after provider state changed.")
    state = json.loads(handle._runtime_state_path().read_text())
    assert state["terminal_id"] == "terminal-1"
    assert "provider_runtime" not in state
    assert capability.saved_states[-1].payload == _provider_runtime_payload("session-b")


def test_supported_provider_no_current_session_clears_stale_provider_runtime_cache(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    handle._write_applied_runtime_state("terminal-1", handle._desired_runtime_fingerprint())
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    capability = RecordingRuntimeStateCapability(None)
    monkeypatch.setattr(
        runtime_agent.provider_manager,
        "runtime_state_capability",
        lambda provider: capability,
    )
    send_input = terminal_send_patcher(runtime_agent.terminal_service)

    result = handle.notify(
        "Deliver after provider reports no current session.",
        source_kind="linear_event",
        source_id="event-clear-stale-provider-cache",
    )

    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.REUSED
    send_input.assert_called_once_with(
        "terminal-1",
        "Deliver after provider reports no current session.",
    )
    state = json.loads(handle._runtime_state_path().read_text())
    assert "provider_runtime" not in state
    assert capability.cleared_provider_data_dirs


def test_stale_idle_runtime_restarts_before_delivery_and_rehomes_old_pending(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    create_inbox_delivery("provider_conversation", "terminal-1", "Old terminal pending")
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    monkeypatch.setattr(runtime_agent.tmux_client, "session_exists", lambda session: True)
    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "delete_terminal",
        Mock(side_effect=lambda terminal_id, **kwargs: db_module.delete_terminal(terminal_id)),
    )

    def create_replacement(agent):
        db_module.create_terminal(
            "terminal-2",
            "cao-implementation-partner",
            "developer-5678",
            "codex",
            agent_id="implementation_partner",
            workspace_context_id=_default_workspace_context_id(),
        )
        return _created_terminal_result("terminal-2")

    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "create_terminal_for_agent",
        Mock(side_effect=create_replacement),
    )

    result = handle.try_deliver_pending()

    assert result.terminal_id == "terminal-2"
    assert result.delivered is True
    assert handle._last_freshness_result is not None
    assert handle._last_freshness_result.action == AgentRuntimeFreshnessAction.RESTARTED
    assert _pending_deliveries("terminal-1") == []
    assert _pending_deliveries(handle.inbox_receiver_id) == []
    assert _all_delivery_statuses("terminal-2") == [MessageStatus.DELIVERED]
    send_input.assert_called_once_with("terminal-2", "Old terminal pending")


def test_stale_busy_runtime_defers_and_rehomes_terminal_pending_without_delete(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    create_inbox_delivery("provider_conversation", "terminal-1", "Do not strand me")
    _provider(terminal_provider_patcher, TerminalStatus.PROCESSING)
    capability = RecordingRuntimeStateCapability(RuntimeError("must not probe busy terminal"))
    monkeypatch.setattr(
        runtime_agent.provider_manager,
        "runtime_state_capability",
        lambda provider: capability,
    )
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    delete_terminal = Mock()
    monkeypatch.setattr(runtime_agent.terminal_service, "delete_terminal", delete_terminal)

    result = handle.try_deliver_pending()

    assert result.status == AgentRuntimeStatus.BUSY
    assert result.delivered is False
    assert handle._last_freshness_result is not None
    assert handle._last_freshness_result.action == AgentRuntimeFreshnessAction.DEFERRED
    assert handle._last_freshness_result.fresh is False
    assert capability.discovered_terminal_ids == []
    delete_terminal.assert_not_called()
    send_input.assert_not_called()
    assert _pending_deliveries("terminal-1") == []
    assert _pending_deliveries(handle.inbox_receiver_id)[0].message.body == "Do not strand me"


def test_refresh_failure_keeps_notifications_on_agent_receiver(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    create_inbox_delivery("provider_conversation", "terminal-1", "Keep this durable")
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    monkeypatch.setattr(runtime_agent.tmux_client, "session_exists", lambda session: True)
    monkeypatch.setattr(runtime_agent.terminal_service, "delete_terminal", Mock(return_value=True))
    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "create_terminal_for_agent",
        Mock(side_effect=RuntimeError("restart failed")),
    )

    result = handle.try_deliver_pending()

    assert result.attempted is False
    assert result.error == "restart failed"
    send_input.assert_not_called()
    assert _pending_deliveries("terminal-1") == []
    assert _pending_deliveries(handle.inbox_receiver_id)[0].message.body == "Keep this durable"


def test_stale_idle_runtime_does_not_restart_when_old_terminal_stop_fails(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    create_inbox_delivery("provider_conversation", "terminal-1", "Keep on agent while stop fails")
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    create_terminal = Mock()
    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "delete_terminal",
        Mock(side_effect=RuntimeError("failed to stop old terminal")),
    )
    monkeypatch.setattr(runtime_agent.terminal_service, "create_terminal_for_agent", create_terminal)

    result = handle.try_deliver_pending()

    assert result.attempted is False
    assert result.error == "failed to stop old terminal"
    create_terminal.assert_not_called()
    send_input.assert_not_called()
    assert _pending_deliveries("terminal-1") == []
    assert (
        _pending_deliveries(handle.inbox_receiver_id)[0].message.body
        == "Keep on agent while stop fails"
    )


def test_notify_queues_without_terminal_input_while_agent_is_busy(
    test_session,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, TerminalStatus.PROCESSING)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)

    result = handle.notify(
        "A follow-up arrived while you were working.",
        source_kind="linear_event",
        source_id="event-busy",
    )

    assert result.status == AgentRuntimeStatus.BUSY
    assert result.delivery.attempted is False
    send_input.assert_not_called()
    assert _pending_deliveries(handle.inbox_receiver_id)[0].notification.status == (
        MessageStatus.PENDING
    )


def test_accept_notification_preserves_existing_inbox_pointer_while_agent_is_busy(
    test_session,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, TerminalStatus.PROCESSING)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    delivery = create_inbox_delivery(
        "provider_conversation",
        "terminal-1",
        "[CAO inbox notification]\nID: 1",
        source_kind="provider_conversation_thread",
        source_id="1",
    )

    result = handle.accept_notification(AgentRuntimeNotification(delivery=delivery, created=True))

    assert result.status == AgentRuntimeStatus.BUSY
    assert result.delivery.attempted is False
    assert result.notification.delivery.notification.id == delivery.notification.id
    send_input.assert_not_called()
    assert _pending_deliveries(handle.inbox_receiver_id)[0].notification.status == (
        MessageStatus.PENDING
    )


def test_busy_notification_uses_terminal_inbox_for_later_owner_delivery(
    test_session,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    provider = terminal_provider_patcher(
        runtime_agent.provider_manager,
        TerminalStatus.PROCESSING,
    )
    send_input = terminal_send_patcher(inbox_service.terminal_service)

    handle.notify(
        "Deliver this after the agent becomes idle.",
        source_kind="linear_event",
        source_id="event-later",
    )
    provider.status = TerminalStatus.IDLE
    _mark_terminal_fresh(handle)

    assert handle.try_deliver_pending().delivered is True
    send_input.assert_called_once_with("terminal-1", "Deliver this after the agent becomes idle.")
    assert _all_delivery_statuses("terminal-1") == [MessageStatus.DELIVERED]


@pytest.mark.parametrize(
    ("provider_status", "runtime_status"),
    [
        (TerminalStatus.ERROR, AgentRuntimeStatus.ERROR),
        (None, AgentRuntimeStatus.UNREACHABLE),
    ],
)
def test_notify_keeps_notifications_pending_when_agent_is_error_or_unreachable(
    test_session,
    handle,
    provider_status,
    runtime_status,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, provider_status)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)

    result = handle.notify(
        "This should remain durable.",
        source_kind="linear_event",
        source_id=f"event-{runtime_status.value}",
    )

    assert result.status == runtime_status
    assert result.delivery.attempted is False
    send_input.assert_not_called()
    assert _pending_deliveries(handle.inbox_receiver_id)[0].notification.status == (
        MessageStatus.PENDING
    )


def test_notify_delivers_pending_notification_when_agent_is_idle(
    test_session,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
    _mark_terminal_fresh(handle)
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)

    result = handle.notify(
        "A Linear mention is ready.",
        source_kind="linear_event",
        source_id="event-ready",
    )

    assert result.status == AgentRuntimeStatus.IDLE
    assert result.delivery.attempted is True
    assert result.delivery.delivered is True
    send_input.assert_called_once_with("terminal-1", "A Linear mention is ready.")
    assert _all_delivery_statuses("terminal-1") == [MessageStatus.DELIVERED]


def test_duplicate_notification_source_reuses_existing_inbox_message(
    test_session,
    handle,
    terminal_provider_patcher,
):
    _create_terminal()
    _provider(terminal_provider_patcher, TerminalStatus.PROCESSING)

    first = handle.notify(
        "Only one notification should be queued.",
        source_kind="linear_event",
        source_id="event-duplicate",
    )
    second = handle.notify(
        "Duplicate webhook body should not create another row.",
        source_kind="linear_event",
        source_id="event-duplicate",
    )

    assert first.notification.created is True
    assert second.notification.created is False
    assert (
        second.notification.delivery.notification.id == first.notification.delivery.notification.id
    )
    deliveries = _pending_deliveries(handle.inbox_receiver_id)
    assert [delivery.message.body for delivery in deliveries] == [
        "Only one notification should be queued."
    ]


def test_duplicate_notification_source_does_not_republish_unchanged_runtime_events(
    test_session,
    handle,
    terminal_provider_patcher,
    recorded_runtime_events,
):
    _create_terminal()
    _provider(terminal_provider_patcher, TerminalStatus.PROCESSING)

    first = handle.notify(
        "Only one runtime notification event should be emitted.",
        source_kind="linear_event",
        source_id="event-runtime-duplicate",
    )
    event_count_after_first = len(recorded_runtime_events)
    second = handle.notify(
        "Duplicate webhook should not emit unchanged runtime events.",
        source_kind="linear_event",
        source_id="event-runtime-duplicate",
    )

    assert first.notification.created is True
    assert second.notification.created is False
    assert event_count_after_first == 3
    assert len(recorded_runtime_events) == event_count_after_first
    assert [type(event) for event in recorded_runtime_events] == [
        AgentRuntimeNotificationAcceptedEvent,
        AgentRuntimeLifecycleEvent,
        AgentRuntimeNotificationDeliveryEvent,
    ]
    delivery = recorded_runtime_events[-1]
    assert isinstance(delivery, AgentRuntimeNotificationDeliveryEvent)
    assert delivery.outcome == "deferred"
    assert delivery.runtime_status == AgentRuntimeStatus.BUSY.value

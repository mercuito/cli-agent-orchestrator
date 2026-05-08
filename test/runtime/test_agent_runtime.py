"""Tests for the CAO-owned provider-facing agent runtime handle."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import create_inbox_delivery
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.runtime import agent as runtime_agent
from cli_agent_orchestrator.runtime.agent import (
    AgentRuntimeHandle,
    AgentRuntimeNotification,
    AgentRuntimeStatus,
)
from cli_agent_orchestrator.services import inbox_service


@pytest.fixture
def test_session(runtime_inbox_db_session):
    return runtime_inbox_db_session


@pytest.fixture
def identity(implementation_partner_identity_factory):
    return implementation_partner_identity_factory()


@pytest.fixture
def handle(identity) -> AgentRuntimeHandle:
    return AgentRuntimeHandle(identity)


def _create_terminal(session_name: str = "cao-implementation-partner") -> str:
    return db_module.create_terminal(
        "terminal-1",
        session_name,
        "developer-1234",
        "codex",
        "developer",
    )["id"]


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


def test_status_reports_not_started_without_terminal_metadata(test_session, handle):
    assert handle.status() == AgentRuntimeStatus.NOT_STARTED


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


def test_ensure_started_creates_terminal_from_agent_identity_when_not_started(
    test_session,
    monkeypatch,
    identity,
    handle,
):
    created = Mock(
        id="terminal-1",
        session_name="cao-implementation-partner",
        name="developer-1234",
        provider=Mock(value="codex"),
        agent_profile="developer",
    )
    create_terminal = Mock(return_value=created)
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.tmux_client.session_exists",
        lambda session: False,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.terminal_service.create_terminal",
        create_terminal,
    )

    terminal = handle.ensure_started()

    assert terminal.id == "terminal-1"
    create_terminal.assert_called_once_with(
        provider=identity.cli_provider,
        agent_profile=identity.agent_profile,
        session_name="cao-implementation-partner",
        new_session=True,
        working_directory=identity.workdir,
    )


def test_notify_accepts_durable_inbox_state_when_startup_fails(
    test_session,
    monkeypatch,
    handle,
):
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.tmux_client.session_exists",
        lambda session: False,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.terminal_service.create_terminal",
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


def test_offline_notification_moves_to_terminal_inbox_when_runtime_later_starts(
    test_session,
    monkeypatch,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    monkeypatch.setattr(
        "cli_agent_orchestrator.runtime.agent.terminal_service.create_terminal",
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
    _provider(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(inbox_service.terminal_service)

    result = handle.try_deliver_pending()

    assert result.delivered is True
    assert _pending_deliveries(handle.inbox_receiver_id) == []
    assert _all_delivery_statuses("terminal-1") == [MessageStatus.DELIVERED]
    send_input.assert_called_once_with("terminal-1", "Persist me while the agent is offline.")


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
    assert _pending_deliveries("terminal-1")[0].notification.status == MessageStatus.PENDING


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
        "presence",
        "terminal-1",
        "[CAO inbox notification]\nID: 1",
        source_kind="presence_thread",
        source_id="1",
    )

    result = handle.accept_notification(AgentRuntimeNotification(delivery=delivery, created=True))

    assert result.status == AgentRuntimeStatus.BUSY
    assert result.delivery.attempted is False
    assert result.notification.delivery.notification.id == delivery.notification.id
    send_input.assert_not_called()
    assert _pending_deliveries("terminal-1")[0].notification.status == MessageStatus.PENDING


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

    assert inbox_service.check_and_send_pending_messages("terminal-1") is True
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
    assert _pending_deliveries("terminal-1")[0].notification.status == MessageStatus.PENDING


def test_notify_delivers_pending_notification_when_agent_is_idle(
    test_session,
    handle,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    _create_terminal()
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
    deliveries = _pending_deliveries("terminal-1")
    assert [delivery.message.body for delivery in deliveries] == [
        "Only one notification should be queued."
    ]

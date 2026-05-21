"""Tests for the inbox service."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.inbox import (
    get_notification,
    send as send,
)
from cli_agent_orchestrator.inbox import readiness as inbox_service
from cli_agent_orchestrator.inbox.readiness import (
    LogFileHandler,
    check_and_send_pending_messages,
    format_message_batch,
)
from cli_agent_orchestrator.models.inbox import InboxNotification, MessageStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus


def _delivery(
    notification_id: int,
    message: str,
    *,
    sender_id: str = "sender",
    receiver_id: str = "test-agent",
) -> InboxNotification:
    return InboxNotification(
        id=notification_id,
        sender_agent_id=sender_id,
        receiver_agent_id=receiver_id,
        body=message,
        status=MessageStatus.PENDING,
        created_at=datetime(2026, 1, 1, 9, notification_id, 0),
    )


def _create_test_notification(sender_id: str, receiver_id: str, body: str) -> InboxNotification:
    return send(receiver_id, body, sender_agent_id=sender_id)


def _get_test_delivery(notification_id: int) -> InboxNotification | None:
    return get_notification(notification_id)


@pytest.fixture
def live_inbox_db(runtime_inbox_db_session):
    return runtime_inbox_db_session


@pytest.fixture(autouse=True)
def agent_addressed_terminal_compat(monkeypatch):
    """Keep legacy readiness unit tests focused on delivery behavior.

    The tracer test covers real agent-id resolution through terminal metadata.
    These older tests exercise batching, status checks, and failure handling.
    """
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness._live_terminal_id_for_agent",
        lambda receiver_agent_id: f"terminal-for-{receiver_agent_id}",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.get_terminal_metadata",
        lambda terminal_id: {"agent_id": f"agent-for-{terminal_id}"},
    )


def _provider_with_status(terminal_provider_patcher, status: TerminalStatus):
    return terminal_provider_patcher(inbox_service.provider_manager, status)


class TestCheckAndSendPendingMessages:
    """Tests for check_and_send_pending_messages function."""

    @patch("cli_agent_orchestrator.inbox.readiness.get_oldest_pending_inbox_notification")
    def test_no_pending_messages(self, mock_get_oldest):
        """Test when no pending messages exist."""
        mock_get_oldest.return_value = None

        result = check_and_send_pending_messages("test-agent")

        assert result is False

    @patch("cli_agent_orchestrator.inbox.readiness.provider_manager")
    @patch(
        "cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications_for_sender"
    )
    @patch("cli_agent_orchestrator.inbox.readiness.get_oldest_pending_inbox_notification")
    def test_provider_not_found(self, mock_get_oldest, mock_get_batch, mock_provider_manager):
        """Test when provider not found."""
        mock_message = _delivery(1, "test message")
        mock_get_oldest.return_value = mock_message
        mock_get_batch.return_value = [mock_message]
        mock_provider_manager.get_provider.return_value = None

        with pytest.raises(ValueError, match="Provider not found"):
            check_and_send_pending_messages("test-agent")

    @patch("cli_agent_orchestrator.inbox.readiness.provider_manager")
    @patch(
        "cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications_for_sender"
    )
    @patch("cli_agent_orchestrator.inbox.readiness.get_oldest_pending_inbox_notification")
    def test_terminal_not_ready(self, mock_get_oldest, mock_get_batch, mock_provider_manager):
        """Test when terminal not ready."""
        mock_message = _delivery(1, "test message")
        mock_get_oldest.return_value = mock_message
        mock_get_batch.return_value = [mock_message]
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.PROCESSING
        mock_provider_manager.get_provider.return_value = mock_provider

        result = check_and_send_pending_messages("test-agent")

        assert result is False

    @patch("cli_agent_orchestrator.inbox.readiness.update_inbox_notification_statuses")
    @patch("cli_agent_orchestrator.inbox.readiness.terminal_service")
    @patch("cli_agent_orchestrator.inbox.readiness.provider_manager")
    @patch(
        "cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications_for_sender"
    )
    @patch("cli_agent_orchestrator.inbox.readiness.get_oldest_pending_inbox_notification")
    def test_message_sent_successfully(
        self,
        mock_get_oldest,
        mock_get_batch,
        mock_provider_manager,
        mock_terminal_service,
        mock_update_statuses,
    ):
        """Test successful message delivery."""
        mock_message = _delivery(1, "test message")
        mock_get_oldest.return_value = mock_message
        mock_get_batch.return_value = [mock_message]
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.IDLE
        mock_provider_manager.get_provider.return_value = mock_provider

        result = check_and_send_pending_messages("test-agent")

        assert result is True
        mock_terminal_service.send_input.assert_called_once()
        assert mock_terminal_service.send_input.call_args.args[0] == "terminal-for-test-agent"
        assert mock_terminal_service.send_input.call_args.args[1].startswith("test message")
        mock_update_statuses.assert_called_once_with([1], MessageStatus.DELIVERED)

    @patch("cli_agent_orchestrator.inbox.readiness.update_inbox_notification_statuses")
    @patch("cli_agent_orchestrator.inbox.readiness.terminal_service")
    @patch("cli_agent_orchestrator.inbox.readiness.provider_manager")
    @patch(
        "cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications_for_sender"
    )
    @patch("cli_agent_orchestrator.inbox.readiness.get_oldest_pending_inbox_notification")
    def test_message_send_failure(
        self,
        mock_get_oldest,
        mock_get_batch,
        mock_provider_manager,
        mock_terminal_service,
        mock_update_statuses,
    ):
        """Test message delivery failure."""
        mock_message = _delivery(1, "test message")
        mock_get_oldest.return_value = mock_message
        mock_get_batch.return_value = [mock_message]
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.IDLE
        mock_provider_manager.get_provider.return_value = mock_provider
        mock_terminal_service.send_input.side_effect = Exception("Send failed")

        with pytest.raises(Exception, match="Send failed"):
            check_and_send_pending_messages("test-agent")

        mock_update_statuses.assert_called_once_with(
            [1], MessageStatus.FAILED, error_detail="Send failed"
        )

    @patch("cli_agent_orchestrator.inbox.readiness.update_inbox_notification_statuses")
    @patch("cli_agent_orchestrator.inbox.readiness.terminal_service")
    @patch("cli_agent_orchestrator.inbox.readiness.provider_manager")
    @patch(
        "cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications_for_sender"
    )
    @patch("cli_agent_orchestrator.inbox.readiness.get_oldest_pending_inbox_notification")
    def test_same_sender_batch_sent_as_one_payload(
        self,
        mock_get_oldest,
        mock_get_batch,
        mock_provider_manager,
        mock_terminal_service,
        mock_update_statuses,
    ):
        """Same-sender pending messages are delivered together in selected order."""
        messages = [_delivery(1, "first"), _delivery(2, "correction")]
        mock_get_oldest.return_value = messages[0]
        mock_get_batch.return_value = messages
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.IDLE
        mock_provider_manager.get_provider.return_value = mock_provider

        result = check_and_send_pending_messages("test-agent")

        assert result is True
        payload = mock_terminal_service.send_input.call_args.args[1]
        assert "Queued 2 messages from sender" in payload
        assert payload.index("[1] first") < payload.index("[2] correction")
        mock_provider.get_status.assert_called_once()
        mock_update_statuses.assert_called_once_with([1, 2], MessageStatus.DELIVERED)

    @patch("cli_agent_orchestrator.inbox.readiness.update_inbox_notification_statuses")
    @patch("cli_agent_orchestrator.inbox.readiness.terminal_service")
    @patch("cli_agent_orchestrator.inbox.readiness.provider_manager")
    @patch(
        "cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications_for_sender"
    )
    @patch("cli_agent_orchestrator.inbox.readiness.get_oldest_pending_inbox_notification")
    def test_batch_send_failure_marks_selected_messages_failed(
        self,
        mock_get_oldest,
        mock_get_batch,
        mock_provider_manager,
        mock_terminal_service,
        mock_update_statuses,
    ):
        """Only the selected batch is marked failed when terminal send raises."""
        messages = [_delivery(1, "first"), _delivery(2, "correction")]
        mock_get_oldest.return_value = messages[0]
        mock_get_batch.return_value = messages
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.COMPLETED
        mock_provider_manager.get_provider.return_value = mock_provider
        mock_terminal_service.send_input.side_effect = RuntimeError("tmux send failed")

        with pytest.raises(RuntimeError, match="tmux send failed"):
            check_and_send_pending_messages("test-agent")

        mock_update_statuses.assert_called_once_with(
            [1, 2], MessageStatus.FAILED, error_detail="tmux send failed"
        )

    def test_format_message_batch_truncates_and_bounds_output(self):
        """Grouped formatter preserves order while bounding long terminal dumps."""
        messages = [_delivery(1, "a" * 80), _delivery(2, "second")]

        payload = format_message_batch(messages, max_body_chars=30, max_total_chars=120)

        assert payload.startswith("Queued 2 messages from sender:")
        assert "[1]" in payload
        assert "[message truncated]" in payload
        assert len(payload) <= 120


class TestLogFileHandler:
    """Tests for LogFileHandler class."""

    @patch("cli_agent_orchestrator.inbox.readiness.check_and_send_pending_messages")
    @patch("cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications")
    def test_on_modified_triggers_delivery(self, mock_get_messages, mock_check_send):
        """Any log-file modification for a terminal with pending messages
        should delegate to check_and_send_pending_messages."""
        from watchdog.events import FileModifiedEvent

        mock_get_messages.return_value = [MagicMock()]

        handler = LogFileHandler()
        event = FileModifiedEvent("/path/to/test-terminal.log")

        handler.on_modified(event)

        mock_check_send.assert_called_once_with("agent-for-test-terminal")

    @patch("cli_agent_orchestrator.inbox.readiness.check_and_send_pending_messages")
    @patch("cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications")
    def test_handle_log_change_no_pending_messages(self, mock_get_messages, mock_check_send):
        """No DB row for this terminal means nothing to deliver — skip the
        expensive status check entirely."""
        mock_get_messages.return_value = []

        handler = LogFileHandler()
        handler._handle_log_change("test-terminal")

        mock_get_messages.assert_called_once_with("agent-for-test-terminal", limit=1)
        mock_check_send.assert_not_called()

    def test_on_modified_non_log_file(self):
        """on_modified ignores files without a .log suffix."""
        from watchdog.events import FileModifiedEvent

        handler = LogFileHandler()
        event = MagicMock(spec=FileModifiedEvent)
        event.src_path = "/path/to/test-terminal.txt"

        handler.on_modified(event)  # should not raise

    def test_on_modified_not_file_modified_event(self):
        """on_modified ignores non-modification events (create, delete, etc)."""
        handler = LogFileHandler()
        event = MagicMock()
        event.src_path = "/path/to/test-terminal.log"

        handler.on_modified(event)  # should not raise

    @patch("cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications")
    def test_handle_log_change_exception(self, mock_get_messages):
        """_handle_log_change must swallow exceptions so a single DB hiccup
        doesn't kill the watchdog thread."""
        mock_get_messages.side_effect = Exception("Database error")

        handler = LogFileHandler()
        handler._handle_log_change("test-terminal")  # must not raise


class TestAutoDeliveryRegression:
    """Regression: supervisor's pipe-pane log updates while supervisor is
    IDLE → watchdog must deliver the pending message.

    Previously a fast-path pre-filter scanned the raw pipe-pane log for each
    provider's ``get_idle_pattern_for_log()`` marker before proceeding to
    the accurate status check. For Codex v0.111+ the marker is drawn via
    cursor-positioning escapes and never appears as contiguous bytes in the
    raw log, so the fast-path always rejected and no message was ever
    delivered automatically. Deleting the fast-path fixes this.
    """

    @patch("cli_agent_orchestrator.inbox.readiness.update_inbox_notification_statuses")
    @patch("cli_agent_orchestrator.inbox.readiness.terminal_service")
    @patch("cli_agent_orchestrator.inbox.readiness.provider_manager")
    @patch(
        "cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications_for_sender"
    )
    @patch("cli_agent_orchestrator.inbox.readiness.get_oldest_pending_inbox_notification")
    @patch("cli_agent_orchestrator.inbox.readiness.list_pending_inbox_notifications")
    def test_watchdog_delivers_even_when_log_has_no_idle_marker(
        self,
        mock_get_pending,
        mock_get_oldest,
        mock_get_batch,
        mock_provider_manager,
        mock_term_svc,
        mock_update,
    ):
        """Simulates the exact failure mode we hit with Codex in production.

        The receiver's pipe-pane log file has grown (cursor-addressed TUI
        redraws) but contains NO contiguous idle marker. A full
        ``provider.get_status()`` reports IDLE (it reads the rendered
        ``capture-pane`` output, where the marker IS visible).
        """
        from watchdog.events import FileModifiedEvent

        message = _delivery(42, "callback from worker")
        mock_get_pending.return_value = [message]
        mock_get_oldest.return_value = message
        mock_get_batch.return_value = [message]

        provider = MagicMock()
        provider.get_status.return_value = TerminalStatus.IDLE
        # Sanity: even if a caller wanted to check get_idle_pattern_for_log
        # against the raw log, it would not match — the marker isn't there.
        provider.get_idle_pattern_for_log.return_value = r"\? for shortcuts"
        mock_provider_manager.get_provider.return_value = provider

        handler = LogFileHandler()
        handler.on_modified(FileModifiedEvent("/path/to/cao-logs/89ce8e03.log"))

        mock_term_svc.send_input.assert_called_once()
        assert mock_term_svc.send_input.call_args.args[0] == "terminal-for-agent-for-89ce8e03"
        assert mock_term_svc.send_input.call_args.args[1].startswith("callback from worker")
        mock_update.assert_called_once_with([42], MessageStatus.DELIVERED)


def test_busy_terminal_keeps_semantic_notification_pending(
    live_inbox_db,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    delivery = _create_test_notification("worker-a", "agent-1", "Wait until idle.")
    _provider_with_status(terminal_provider_patcher, TerminalStatus.PROCESSING)
    send_input = terminal_send_patcher(inbox_service.terminal_service)

    result = check_and_send_pending_messages("agent-1")

    assert result is False
    send_input.assert_not_called()
    persisted = _get_test_delivery(delivery.id)
    assert persisted.status == MessageStatus.PENDING
    assert persisted.body == "Wait until idle."


@pytest.mark.parametrize("status", [TerminalStatus.IDLE, TerminalStatus.COMPLETED])
def test_idle_or_completed_terminal_delivers_semantic_notification(
    live_inbox_db,
    status,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    delivery = _create_test_notification("worker-a", "agent-1", "Ready now.")
    _provider_with_status(terminal_provider_patcher, status)
    send_input = terminal_send_patcher(inbox_service.terminal_service)

    result = check_and_send_pending_messages("agent-1")

    assert result is True
    send_input.assert_called_once()
    assert send_input.call_args.args[0] == "terminal-for-agent-1"
    assert send_input.call_args.args[1].startswith("Ready now.")
    persisted = _get_test_delivery(delivery.id)
    assert persisted.status == MessageStatus.DELIVERED
    assert persisted.delivered_at is not None


def test_idle_terminal_delivers_non_message_backed_notification_body(
    live_inbox_db,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    notification = send(
        "agent-1",
        "CAO-123 has new comments.",
        sender_agent_id="runtime",
    )
    _provider_with_status(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(inbox_service.terminal_service)

    result = check_and_send_pending_messages("agent-1")

    assert result is True
    send_input.assert_called_once()
    assert send_input.call_args.args[0] == "terminal-for-agent-1"
    assert send_input.call_args.args[1].startswith("CAO-123 has new comments.")
    persisted = _get_test_delivery(notification.id)
    assert persisted.body == "CAO-123 has new comments."
    assert persisted.status == MessageStatus.DELIVERED


def test_plain_notification_preview_includes_notification_id_footer(
    live_inbox_db,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    # Given
    notification = send(
        "agent-1",
        "Plain message body.",
        sender_agent_id="worker-a",
    )
    _provider_with_status(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(inbox_service.terminal_service)

    # When
    result = check_and_send_pending_messages("agent-1")

    # Then
    assert result is True
    send_input.assert_called_once_with(
        "terminal-for-agent-1",
        f"Plain message body.\n\nnotification_id={notification.id}",
    )


def test_delivery_failure_marks_notification_failed_without_mutating_durable_message(
    live_inbox_db,
    monkeypatch,
    terminal_provider_patcher,
):
    delivery = _create_test_notification(
        "runtime",
        "agent-1",
        "Durable provider body.",
    )
    _provider_with_status(terminal_provider_patcher, TerminalStatus.IDLE)
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.terminal_service.send_input",
        MagicMock(side_effect=RuntimeError("tmux send failed")),
    )

    with pytest.raises(RuntimeError, match="tmux send failed"):
        check_and_send_pending_messages("agent-1")

    persisted = _get_test_delivery(delivery.id)
    assert persisted.status == MessageStatus.FAILED
    assert persisted.failed_at is not None
    assert persisted.error_detail == "tmux send failed"
    assert persisted.body == "Durable provider body."


def test_same_sender_notifications_batch_without_merging_different_senders(
    live_inbox_db,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    first = _create_test_notification("worker-a", "agent-1", "first")
    other = _create_test_notification("worker-b", "agent-1", "other sender")
    third = _create_test_notification("worker-a", "agent-1", "third")
    _provider_with_status(terminal_provider_patcher, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(inbox_service.terminal_service)

    result = check_and_send_pending_messages("agent-1")

    assert result is True
    payload = send_input.call_args.args[1]
    assert "[1] first" in payload
    assert "[2] third" in payload
    assert "other sender" not in payload
    assert _get_test_delivery(first.id).status == (
        MessageStatus.DELIVERED
    )
    assert _get_test_delivery(third.id).status == (
        MessageStatus.DELIVERED
    )
    assert _get_test_delivery(other.id).status == MessageStatus.PENDING

"""Tests for the inbox service."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.models.inbox import InboxMessage, MessageStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.services.inbox_service import (
    LogFileHandler,
    check_and_send_pending_messages,
    format_message_batch,
)


def _message(
    message_id: int,
    message: str,
    *,
    sender_id: str = "sender",
    receiver_id: str = "test-terminal",
    source_kind: str | None = "terminal",
    source_id: str | None = "sender",
) -> InboxMessage:
    return InboxMessage(
        id=message_id,
        sender_id=sender_id,
        receiver_id=receiver_id,
        message=message,
        source_kind=source_kind,
        source_id=source_id,
        status=MessageStatus.PENDING,
        created_at=datetime(2026, 1, 1, 9, message_id, 0),
    )


class TestCheckAndSendPendingMessages:
    """Tests for check_and_send_pending_messages function."""

    @patch("cli_agent_orchestrator.services.inbox_service.get_oldest_pending_message")
    def test_no_pending_messages(self, mock_get_oldest):
        """Test when no pending messages exist."""
        mock_get_oldest.return_value = None

        result = check_and_send_pending_messages("test-terminal")

        assert result is False

    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages_for_effective_source")
    @patch("cli_agent_orchestrator.services.inbox_service.get_oldest_pending_message")
    def test_provider_not_found(self, mock_get_oldest, mock_get_batch, mock_provider_manager):
        """Test when provider not found."""
        mock_message = _message(1, "test message")
        mock_get_oldest.return_value = mock_message
        mock_get_batch.return_value = [mock_message]
        mock_provider_manager.get_provider.return_value = None

        with pytest.raises(ValueError, match="Provider not found"):
            check_and_send_pending_messages("test-terminal")

    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages_for_effective_source")
    @patch("cli_agent_orchestrator.services.inbox_service.get_oldest_pending_message")
    def test_terminal_not_ready(self, mock_get_oldest, mock_get_batch, mock_provider_manager):
        """Test when terminal not ready."""
        mock_message = _message(1, "test message")
        mock_get_oldest.return_value = mock_message
        mock_get_batch.return_value = [mock_message]
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.PROCESSING
        mock_provider_manager.get_provider.return_value = mock_provider

        result = check_and_send_pending_messages("test-terminal")

        assert result is False

    @patch("cli_agent_orchestrator.services.inbox_service.update_message_statuses")
    @patch("cli_agent_orchestrator.services.inbox_service.terminal_service")
    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages_for_effective_source")
    @patch("cli_agent_orchestrator.services.inbox_service.get_oldest_pending_message")
    def test_message_sent_successfully(
        self,
        mock_get_oldest,
        mock_get_batch,
        mock_provider_manager,
        mock_terminal_service,
        mock_update_statuses,
    ):
        """Test successful message delivery."""
        mock_message = _message(1, "test message")
        mock_get_oldest.return_value = mock_message
        mock_get_batch.return_value = [mock_message]
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.IDLE
        mock_provider_manager.get_provider.return_value = mock_provider

        result = check_and_send_pending_messages("test-terminal")

        assert result is True
        mock_terminal_service.send_input.assert_called_once_with("test-terminal", "test message")
        mock_update_statuses.assert_called_once_with([1], MessageStatus.DELIVERED)

    @patch("cli_agent_orchestrator.services.inbox_service.update_message_statuses")
    @patch("cli_agent_orchestrator.services.inbox_service.terminal_service")
    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages_for_effective_source")
    @patch("cli_agent_orchestrator.services.inbox_service.get_oldest_pending_message")
    def test_message_send_failure(
        self,
        mock_get_oldest,
        mock_get_batch,
        mock_provider_manager,
        mock_terminal_service,
        mock_update_statuses,
    ):
        """Test message delivery failure."""
        mock_message = _message(1, "test message")
        mock_get_oldest.return_value = mock_message
        mock_get_batch.return_value = [mock_message]
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.IDLE
        mock_provider_manager.get_provider.return_value = mock_provider
        mock_terminal_service.send_input.side_effect = Exception("Send failed")

        with pytest.raises(Exception, match="Send failed"):
            check_and_send_pending_messages("test-terminal")

        mock_update_statuses.assert_called_once_with([1], MessageStatus.FAILED)

    @patch("cli_agent_orchestrator.services.inbox_service.update_message_statuses")
    @patch("cli_agent_orchestrator.services.inbox_service.terminal_service")
    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages_for_effective_source")
    @patch("cli_agent_orchestrator.services.inbox_service.get_oldest_pending_message")
    def test_same_source_batch_sent_as_one_payload(
        self,
        mock_get_oldest,
        mock_get_batch,
        mock_provider_manager,
        mock_terminal_service,
        mock_update_statuses,
    ):
        """Same-source pending messages are delivered together in selected order."""
        messages = [_message(1, "first"), _message(2, "correction")]
        mock_get_oldest.return_value = messages[0]
        mock_get_batch.return_value = messages
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.IDLE
        mock_provider_manager.get_provider.return_value = mock_provider

        result = check_and_send_pending_messages("test-terminal")

        assert result is True
        payload = mock_terminal_service.send_input.call_args.args[1]
        assert "Queued 2 messages from terminal:sender" in payload
        assert payload.index("[1] first") < payload.index("[2] correction")
        mock_provider.get_status.assert_called_once()
        mock_update_statuses.assert_called_once_with([1, 2], MessageStatus.DELIVERED)

    @patch("cli_agent_orchestrator.services.inbox_service.update_message_statuses")
    @patch("cli_agent_orchestrator.services.inbox_service.terminal_service")
    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages_for_effective_source")
    @patch("cli_agent_orchestrator.services.inbox_service.get_oldest_pending_message")
    def test_batch_send_failure_marks_selected_messages_failed(
        self,
        mock_get_oldest,
        mock_get_batch,
        mock_provider_manager,
        mock_terminal_service,
        mock_update_statuses,
    ):
        """Only the selected batch is marked failed when terminal send raises."""
        messages = [_message(1, "first"), _message(2, "correction")]
        mock_get_oldest.return_value = messages[0]
        mock_get_batch.return_value = messages
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.COMPLETED
        mock_provider_manager.get_provider.return_value = mock_provider
        mock_terminal_service.send_input.side_effect = RuntimeError("tmux send failed")

        with pytest.raises(RuntimeError, match="tmux send failed"):
            check_and_send_pending_messages("test-terminal")

        mock_update_statuses.assert_called_once_with([1, 2], MessageStatus.FAILED)

    def test_format_message_batch_truncates_and_bounds_output(self):
        """Grouped formatter preserves order while bounding long terminal dumps."""
        messages = [_message(1, "a" * 80), _message(2, "second")]

        payload = format_message_batch(messages, max_body_chars=30, max_total_chars=120)

        assert payload.startswith("Queued 2 messages from terminal:sender:")
        assert "[1]" in payload
        assert "[message truncated]" in payload
        assert len(payload) <= 120


class TestLogFileHandler:
    """Tests for LogFileHandler class."""

    @patch("cli_agent_orchestrator.services.inbox_service.check_and_send_pending_messages")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
    def test_on_modified_triggers_delivery(self, mock_get_messages, mock_check_send):
        """Any log-file modification for a terminal with pending messages
        should delegate to check_and_send_pending_messages."""
        from watchdog.events import FileModifiedEvent

        mock_get_messages.return_value = [MagicMock()]

        handler = LogFileHandler()
        event = FileModifiedEvent("/path/to/test-terminal.log")

        handler.on_modified(event)

        mock_check_send.assert_called_once_with("test-terminal")

    @patch("cli_agent_orchestrator.services.inbox_service.check_and_send_pending_messages")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
    def test_handle_log_change_no_pending_messages(self, mock_get_messages, mock_check_send):
        """No DB row for this terminal means nothing to deliver — skip the
        expensive status check entirely."""
        mock_get_messages.return_value = []

        handler = LogFileHandler()
        handler._handle_log_change("test-terminal")

        mock_get_messages.assert_called_once_with("test-terminal", limit=1)
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

    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
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

    @patch("cli_agent_orchestrator.services.inbox_service.update_message_statuses")
    @patch("cli_agent_orchestrator.services.inbox_service.terminal_service")
    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages_for_effective_source")
    @patch("cli_agent_orchestrator.services.inbox_service.get_oldest_pending_message")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
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

        message = _message(42, "callback from worker")
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

        mock_term_svc.send_input.assert_called_once_with("89ce8e03", "callback from worker")
        mock_update.assert_called_once_with([42], MessageStatus.DELIVERED)

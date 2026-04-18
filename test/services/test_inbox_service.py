"""Tests for the inbox service."""

from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.services.inbox_service import (
    LogFileHandler,
    check_and_send_pending_messages,
)


class TestCheckAndSendPendingMessages:
    """Tests for check_and_send_pending_messages function."""

    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
    def test_no_pending_messages(self, mock_get_messages):
        """Test when no pending messages exist."""
        mock_get_messages.return_value = []

        result = check_and_send_pending_messages("test-terminal")

        assert result is False

    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
    def test_provider_not_found(self, mock_get_messages, mock_provider_manager):
        """Test when provider not found."""
        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.message = "test message"
        mock_get_messages.return_value = [mock_message]
        mock_provider_manager.get_provider.return_value = None

        with pytest.raises(ValueError, match="Provider not found"):
            check_and_send_pending_messages("test-terminal")

    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
    def test_terminal_not_ready(self, mock_get_messages, mock_provider_manager):
        """Test when terminal not ready."""
        mock_message = MagicMock()
        mock_get_messages.return_value = [mock_message]
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.PROCESSING
        mock_provider_manager.get_provider.return_value = mock_provider

        result = check_and_send_pending_messages("test-terminal")

        assert result is False

    @patch("cli_agent_orchestrator.services.inbox_service.update_message_status")
    @patch("cli_agent_orchestrator.services.inbox_service.terminal_service")
    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
    def test_message_sent_successfully(
        self, mock_get_messages, mock_provider_manager, mock_terminal_service, mock_update_status
    ):
        """Test successful message delivery."""
        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.message = "test message"
        mock_get_messages.return_value = [mock_message]
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.IDLE
        mock_provider_manager.get_provider.return_value = mock_provider

        result = check_and_send_pending_messages("test-terminal")

        assert result is True
        mock_terminal_service.send_input.assert_called_once_with("test-terminal", "test message")
        mock_update_status.assert_called_once_with(1, MessageStatus.DELIVERED)

    @patch("cli_agent_orchestrator.services.inbox_service.update_message_status")
    @patch("cli_agent_orchestrator.services.inbox_service.terminal_service")
    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
    def test_message_send_failure(
        self, mock_get_messages, mock_provider_manager, mock_terminal_service, mock_update_status
    ):
        """Test message delivery failure."""
        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.message = "test message"
        mock_get_messages.return_value = [mock_message]
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.IDLE
        mock_provider_manager.get_provider.return_value = mock_provider
        mock_terminal_service.send_input.side_effect = Exception("Send failed")

        with pytest.raises(Exception, match="Send failed"):
            check_and_send_pending_messages("test-terminal")

        mock_update_status.assert_called_once_with(1, MessageStatus.FAILED)


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

    @patch("cli_agent_orchestrator.services.inbox_service.update_message_status")
    @patch("cli_agent_orchestrator.services.inbox_service.terminal_service")
    @patch("cli_agent_orchestrator.services.inbox_service.provider_manager")
    @patch("cli_agent_orchestrator.services.inbox_service.get_pending_messages")
    def test_watchdog_delivers_even_when_log_has_no_idle_marker(
        self, mock_get_messages, mock_provider_manager, mock_term_svc, mock_update
    ):
        """Simulates the exact failure mode we hit with Codex in production.

        The receiver's pipe-pane log file has grown (cursor-addressed TUI
        redraws) but contains NO contiguous idle marker. A full
        ``provider.get_status()`` reports IDLE (it reads the rendered
        ``capture-pane`` output, where the marker IS visible).
        """
        from watchdog.events import FileModifiedEvent

        message = MagicMock()
        message.id = 42
        message.message = "callback from worker"
        mock_get_messages.return_value = [message]

        provider = MagicMock()
        provider.get_status.return_value = TerminalStatus.IDLE
        # Sanity: even if a caller wanted to check get_idle_pattern_for_log
        # against the raw log, it would not match — the marker isn't there.
        provider.get_idle_pattern_for_log.return_value = r"\? for shortcuts"
        mock_provider_manager.get_provider.return_value = provider

        handler = LogFileHandler()
        handler.on_modified(FileModifiedEvent("/path/to/cao-logs/89ce8e03.log"))

        mock_term_svc.send_input.assert_called_once_with("89ce8e03", "callback from worker")
        mock_update.assert_called_once_with(42, MessageStatus.DELIVERED)

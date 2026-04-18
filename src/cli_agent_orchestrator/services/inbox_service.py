"""Inbox service with watchdog for automatic message delivery.

This module provides the inbox functionality for agent-to-agent communication,
using file system monitoring to detect when agents become idle and can receive
messages.

Architecture:
- Messages are queued in the database (inbox table) via send_message MCP tool
- LogFileHandler monitors terminal log files for changes using watchdog
- When a log file is modified and there are pending messages for that
  terminal, the accurate ``provider.get_status()`` is consulted; if the
  terminal is IDLE or COMPLETED, pending messages are delivered via
  ``terminal_service.send_input()`` (types into the tmux pane)

Message Flow:
1. Agent A calls ``send_message(terminal_id, message)`` — queued in DB as PENDING
2. Agent B's pipe-pane log file is appended to (TUI redraws, output, etc.)
3. ``LogFileHandler.on_modified()`` fires → checks the DB for pending messages
4. If pending + terminal is idle/completed → deliver, mark DELIVERED
5. On send failure, mark FAILED

Design note — no pre-filter on the log contents:
   An earlier version attempted to skip the expensive status check by
   fast-matching each provider's ``get_idle_pattern_for_log()`` against the
   tail of the raw pipe-pane log. That assumption broke in practice: Codex
   v0.111+ (and other TUI-redraw-heavy providers) draw their idle markers
   via cursor-positioning escape codes, so the marker never appears as
   contiguous bytes in the raw stream. The fast-path silently rejected
   every delivery. Benchmarks showed the accurate check at ~24 ms per call;
   at realistic loads (<10 active terminals, 5 s polling) total overhead is
   under ~5% CPU worst case. Removing the pre-filter trades a small CPU
   margin for correctness across all provider versions.
"""

import logging
from pathlib import Path

from watchdog.events import FileModifiedEvent, FileSystemEventHandler

from cli_agent_orchestrator.clients.database import (
    get_pending_messages,
    update_message_status,
)
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.manager import provider_manager
from cli_agent_orchestrator.services import terminal_service

logger = logging.getLogger(__name__)


def check_and_send_pending_messages(terminal_id: str) -> bool:
    """Check for pending messages and send if terminal is ready.

    Args:
        terminal_id: Terminal ID to check messages for

    Returns:
        bool: True if a message was sent, False otherwise

    Raises:
        ValueError: If provider not found for terminal
    """
    messages = get_pending_messages(terminal_id, limit=1)
    if not messages:
        return False

    message = messages[0]

    provider = provider_manager.get_provider(terminal_id)
    if provider is None:
        raise ValueError(f"Provider not found for terminal {terminal_id}")

    status = provider.get_status()
    if status not in (TerminalStatus.IDLE, TerminalStatus.COMPLETED):
        logger.debug(f"Terminal {terminal_id} not ready (status={status})")
        return False

    try:
        terminal_service.send_input(terminal_id, message.message)
        update_message_status(message.id, MessageStatus.DELIVERED)
        logger.info(f"Delivered message {message.id} to terminal {terminal_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send message {message.id} to {terminal_id}: {e}")
        update_message_status(message.id, MessageStatus.FAILED)
        raise


class LogFileHandler(FileSystemEventHandler):
    """Handler for terminal log file changes."""

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and event.src_path.endswith(".log"):
            log_path = Path(event.src_path)
            terminal_id = log_path.stem
            logger.debug(f"Log file modified: {terminal_id}.log")
            self._handle_log_change(terminal_id)

    def _handle_log_change(self, terminal_id: str):
        """Handle log file change and attempt message delivery.

        Short-circuits on the cheap DB check so we don't pay for
        ``provider.get_status()`` (tmux subprocess call) when there is
        nothing to deliver. For any pending message, delegate to
        ``check_and_send_pending_messages`` which is the single source of
        truth for the idle-detection and delivery semantics.
        """
        try:
            if not get_pending_messages(terminal_id, limit=1):
                logger.debug(f"No pending messages for {terminal_id}, skipping")
                return
            check_and_send_pending_messages(terminal_id)
        except Exception as e:
            logger.error(f"Error handling log change for {terminal_id}: {e}")

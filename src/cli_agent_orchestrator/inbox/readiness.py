"""Inbox readiness and terminal delivery.

This module keeps terminal readiness as an implementation detail of the
agent-addressed inbox. Notifications are stored against durable agent ids;
delivery resolves the receiver's live terminal only when a send attempt runs.

Message Flow:
1. Agent A calls ``send_message(receiver_agent_id, body)`` — queued as a pending notification
2. Agent B's pipe-pane log file is appended to (TUI redraws, output, etc.)
3. ``LogFileHandler.on_modified()`` resolves the terminal to its agent
4. If pending + live terminal is idle/completed → deliver, mark DELIVERED
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
from typing import List

from watchdog.events import FileModifiedEvent, FileSystemEventHandler

from cli_agent_orchestrator.clients.database import (
    get_terminal_metadata,
    list_terminals_by_agent,
)
from cli_agent_orchestrator.events import (
    AgentReady,
    CaoEventDispatcher,
    InvalidCaoEventError,
    default_cao_event_dispatcher,
)
from cli_agent_orchestrator.inbox.store import (
    get_oldest_pending_inbox_notification,
    list_pending_inbox_notifications,
    list_pending_inbox_notifications_for_sender,
    update_inbox_notification_statuses,
)
from cli_agent_orchestrator.models.inbox import InboxNotification, MessageStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.manager import provider_manager
from cli_agent_orchestrator.services import terminal_service

logger = logging.getLogger(__name__)

DEFAULT_MAX_BATCH_BODY_CHARS = 2000
DEFAULT_MAX_BATCH_TOTAL_CHARS = 12000
AGENT_READY_INBOX_DELIVERY_SUBSCRIPTION_ID = "inbox.agent-ready-delivery"


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    suffix = "\n[message truncated]"
    return text[: max(0, max_chars - len(suffix))].rstrip() + suffix


def _format_delivery_body(
    notification: InboxNotification,
    *,
    max_chars: int,
) -> str:
    footer = f"\n\nnotification_id={notification.id}"
    body = _truncate_text(notification.body, max(0, max_chars - len(footer)))
    return f"{body}{footer}"


def format_message_batch(
    notifications: List[InboxNotification],
    *,
    max_body_chars: int = DEFAULT_MAX_BATCH_BODY_CHARS,
    max_total_chars: int = DEFAULT_MAX_BATCH_TOTAL_CHARS,
) -> str:
    """Format a selected inbox batch for terminal delivery with bounded output."""
    if not notifications:
        return ""
    if len(notifications) == 1:
        return _format_delivery_body(notifications[0], max_chars=max_total_chars)

    header = f"Queued {len(notifications)} messages from {notifications[0].sender_agent_id}:"
    lines = [header, ""]

    for idx, notification in enumerate(notifications, start=1):
        formatted_message = f"[{idx}] {_format_delivery_body(notification, max_chars=max_body_chars)}"
        candidate = "\n".join([*lines, formatted_message])
        if len(candidate) > max_total_chars:
            lines.append("[batch output truncated]")
            break
        lines.append(formatted_message)

    result = "\n".join(lines)
    if len(result) > max_total_chars:
        result = result[:max_total_chars].rstrip()
    return result


def check_and_send_pending_messages(receiver_agent_id: str) -> bool:
    """Check for pending messages and send if the receiver is ready.

    Args:
        receiver_agent_id: Durable receiver id to check messages for.

    Returns:
        bool: True if a message was sent, False otherwise

    Raises:
        ValueError: If provider not found for the receiver's terminal
    """
    oldest_notification = get_oldest_pending_inbox_notification(receiver_agent_id)
    if oldest_notification is None:
        return False

    terminal_id = _live_terminal_id_for_agent(receiver_agent_id)
    if terminal_id is None:
        logger.debug("No live terminal for agent %s", receiver_agent_id)
        return False

    notifications = list_pending_inbox_notifications_for_sender(
        receiver_agent_id, oldest_notification
    )
    if not notifications:
        logger.warning(
            "Oldest pending notification %s selected no deliverable batch for agent %s",
            oldest_notification.id,
            receiver_agent_id,
        )
        return False
    notification_ids = [notification.id for notification in notifications]

    provider = provider_manager.get_provider(terminal_id)
    if provider is None:
        raise ValueError(f"Provider not found for terminal {terminal_id}")

    status = provider.get_status()
    if status not in (TerminalStatus.IDLE, TerminalStatus.COMPLETED):
        logger.debug(f"Terminal {terminal_id} not ready (status={status})")
        return False

    try:
        terminal_service.send_input(terminal_id, format_message_batch(notifications))
        update_inbox_notification_statuses(notification_ids, MessageStatus.DELIVERED)
        logger.info(
            "Delivered inbox notification batch %s to terminal %s",
            notification_ids,
            terminal_id,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send notification batch {notification_ids} to {terminal_id}: {e}")
        update_inbox_notification_statuses(
            notification_ids, MessageStatus.FAILED, error_detail=str(e)
        )
        raise


def subscribe_to_agent_ready(dispatcher: CaoEventDispatcher | None = None) -> CaoEventDispatcher:
    """Subscribe inbox delivery to AgentReady events on a dispatcher."""

    event_dispatcher = dispatcher or default_cao_event_dispatcher()
    event_dispatcher.register_events((AgentReady,))
    try:
        event_dispatcher.subscribe(
            event_type=AgentReady,
            handler=_handle_agent_ready,
            subscription_id=AGENT_READY_INBOX_DELIVERY_SUBSCRIPTION_ID,
        )
    except InvalidCaoEventError as exc:
        if "Duplicate CAO event subscription_id" not in str(exc):
            raise
    return event_dispatcher


def _handle_agent_ready(event: AgentReady) -> bool:
    delivered = False
    for receiver_id in _pending_receiver_ids_for_ready_agent(event.agent_id):
        delivered = check_and_send_pending_messages(receiver_id) or delivered
    return delivered


def _pending_receiver_ids_for_ready_agent(agent_id: str) -> list[str]:
    if list_pending_inbox_notifications(agent_id, limit=1):
        return [agent_id]
    return []


def _live_terminal_id_for_agent(agent_id: str) -> str | None:
    terminals = list_terminals_by_agent(agent_id)
    if terminals:
        terminal_id = terminals[0].get("id")
        return str(terminal_id) if terminal_id else None
    return None


def _agent_receiver_ids_for_terminal(metadata: dict) -> list[str]:
    agent_id = metadata.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        return []
    return [agent_id]


class LogFileHandler(FileSystemEventHandler):
    """Handler for terminal log file changes."""

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and event.src_path.endswith(".log"):
            log_path = Path(event.src_path)
            terminal_id = log_path.stem
            logger.debug(f"Log file modified: {terminal_id}.log")
            self._handle_log_change(terminal_id)

    def _handle_log_change(self, terminal_id: str):
        """Handle log file change and attempt message delivery for its agent.

        Short-circuits on the cheap DB check so we don't pay for
        ``provider.get_status()`` (tmux subprocess call) when there is
        nothing to deliver. For any pending message, delegate to
        ``check_and_send_pending_messages`` which is the single source of
        truth for the idle-detection and delivery semantics.
        """
        try:
            metadata = get_terminal_metadata(terminal_id)
            if metadata is None:
                logger.debug("No terminal metadata for %s, skipping inbox delivery", terminal_id)
                return
            receiver_ids = _agent_receiver_ids_for_terminal(metadata)
            if not receiver_ids:
                logger.debug("Terminal %s has no agent id, skipping inbox delivery", terminal_id)
                return
            for receiver_id in receiver_ids:
                if not list_pending_inbox_notifications(receiver_id, limit=1):
                    continue
                check_and_send_pending_messages(receiver_id)
                return
            logger.debug("No pending messages for terminal %s receivers, skipping", terminal_id)
        except Exception as e:
            logger.error(f"Error handling log change for {terminal_id}: {e}")


subscribe_to_agent_ready()

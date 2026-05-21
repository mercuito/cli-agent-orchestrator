"""Process-local inbox reply source registry."""

from __future__ import annotations

from typing import Any, Callable

from cli_agent_orchestrator.inbox.models import Notification

ReplyHandler = Callable[[Notification, str, str], Any]

_reply_handlers: dict[str, ReplyHandler] = {}


class NotReplyable(ValueError):
    """Raised when an inbox notification source has no reply handler."""


def register_reply_handler(source_kind: str, handler: ReplyHandler) -> None:
    """Register the reply handler for one inbox source kind."""
    source_kind = _required_text(source_kind, "source_kind")
    _reply_handlers[source_kind] = handler


def can_reply(source_kind: str) -> bool:
    """Return whether a reply handler is registered for ``source_kind``."""
    return source_kind in _reply_handlers


def dispatch_reply(notification: Notification, body: str, caller_agent_id: str) -> Any:
    """Dispatch a reply through the handler registered for the notification source."""
    handler = _reply_handlers.get(notification.source_kind)
    if handler is None:
        raise NotReplyable(
            f"inbox notification {notification.id} source_kind "
            f"{notification.source_kind!r} is not replyable"
        )
    return handler(notification, body, caller_agent_id)


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()

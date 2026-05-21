"""Agent-addressed inbox public API."""

from __future__ import annotations

import logging

from cli_agent_orchestrator.inbox.models import (
    Notification,
    PlainSource,
    ProviderSource,
    ReadResult,
    Reply,
)
from cli_agent_orchestrator.inbox.source_registry import (
    NotReplyable,
)
from cli_agent_orchestrator.inbox.source_registry import can_reply as _source_can_reply
from cli_agent_orchestrator.inbox.source_registry import (
    dispatch_reply,
    register_reply_handler,
)

logger = logging.getLogger(__name__)


class InboxReadError(ValueError):
    """Base error for inbox read failures."""


class InboxReadNotFoundError(InboxReadError):
    """Raised when the requested inbox notification is missing."""


class InboxReplyError(ValueError):
    """Base error for inbox reply failures."""


def send(
    receiver_agent_id: str,
    body: str,
    *,
    source: PlainSource | ProviderSource,
) -> Notification:
    """Persist a notification and attempt immediate delivery to the live agent terminal."""
    from cli_agent_orchestrator.inbox import readiness, store

    receiver_agent_id = _required_text(receiver_agent_id, "receiver_agent_id")
    body = _required_text(body, "body")
    source_kind, source_id, metadata = _source_record(source)
    legacy_notification = store.create_inbox_notification_event(
        receiver_agent_id,
        body,
        source_kind=source_kind,
        source_id=source_id,
        metadata=metadata,
    )
    try:
        readiness.check_and_send_pending_messages(receiver_agent_id)
    except Exception as exc:
        logger.warning("Immediate inbox delivery attempt failed for %s: %s", receiver_agent_id, exc)
    return _notification_from_legacy(legacy_notification)


def read(notification_id: int, caller_agent_id: str) -> ReadResult:
    """Read one source-agnostic inbox notification for its owning agent."""
    from cli_agent_orchestrator.inbox import store

    caller_agent_id = _required_text(caller_agent_id, "caller_agent_id")
    delivery = store.get_inbox_delivery(notification_id)
    if delivery is None:
        raise InboxReadNotFoundError(f"inbox notification {notification_id} not found")

    notification = _notification_from_legacy(delivery.notification)
    if not _agent_owns_receiver(notification.receiver_agent_id, caller_agent_id):
        raise InboxReadError("caller agent is not authorized for this inbox notification")

    return ReadResult(
        notification=notification,
        body=notification.body,
        metadata=notification.metadata or {},
        can_reply=_source_can_reply(notification.source_kind),
    )


def reply(notification_id: int, body: str, caller_agent_id: str):
    """Reply to one inbox notification through its owning source route."""
    from cli_agent_orchestrator.inbox import store

    caller_agent_id = _required_text(caller_agent_id, "caller_agent_id")
    try:
        body = _required_text(body, "body")
    except ValueError as exc:
        raise InboxReplyError(str(exc)) from exc
    delivery = store.get_inbox_delivery(notification_id)
    if delivery is None:
        raise InboxReadNotFoundError(f"inbox notification {notification_id} not found")

    notification = _notification_from_legacy(delivery.notification)
    if not _agent_owns_receiver(notification.receiver_agent_id, caller_agent_id):
        raise InboxReadError("caller agent is not authorized for this inbox notification")

    return dispatch_reply(notification, body, caller_agent_id)


def _source_record(source: PlainSource | ProviderSource) -> tuple[str, str, dict | None]:
    if isinstance(source, PlainSource):
        return "plain", _required_text(source.sender_agent_id, "sender_agent_id"), None
    return (
        _required_text(source.source_kind, "source_kind"),
        _required_text(source.source_id, "source_id"),
        source.metadata,
    )


def _notification_from_legacy(notification) -> Notification:
    return Notification(
        id=notification.id,
        receiver_agent_id=notification.receiver_id,
        body=notification.body,
        source_kind=notification.source_kind,
        source_id=notification.source_id,
        metadata=notification.metadata,
        status=notification.status,
        created_at=notification.created_at,
        delivered_at=notification.delivered_at,
        failed_at=notification.failed_at,
        error_detail=notification.error_detail,
    )


def _agent_owns_receiver(receiver_agent_id: str, caller_agent_id: str) -> bool:
    agent_receiver_prefix = f"agent:{caller_agent_id}"
    if (
        receiver_agent_id == caller_agent_id
        or receiver_agent_id == agent_receiver_prefix
        or receiver_agent_id.startswith(f"{agent_receiver_prefix}:")
    ):
        return True

    from cli_agent_orchestrator.clients import database as db_module

    metadata = db_module.get_terminal_metadata(receiver_agent_id)
    return metadata is not None and metadata.get("agent_id") == caller_agent_id


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _reply_to_plain_source(notification: Notification, body: str, caller_agent_id: str):
    return send(
        receiver_agent_id=notification.source_id,
        body=body,
        source=PlainSource(sender_agent_id=caller_agent_id),
    )


register_reply_handler("plain", _reply_to_plain_source)


__all__ = [
    "InboxReadError",
    "InboxReadNotFoundError",
    "InboxReplyError",
    "NotReplyable",
    "Notification",
    "PlainSource",
    "ProviderSource",
    "ReadResult",
    "Reply",
    "read",
    "reply",
    "send",
]

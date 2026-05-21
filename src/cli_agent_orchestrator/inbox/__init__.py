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

logger = logging.getLogger(__name__)


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


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


__all__ = [
    "Notification",
    "PlainSource",
    "ProviderSource",
    "ReadResult",
    "Reply",
    "send",
]

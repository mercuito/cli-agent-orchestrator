"""Agent-to-agent inbox public API."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Sequence

from cli_agent_orchestrator.inbox.models import Notification, ReadResult
from cli_agent_orchestrator.models.inbox import InboxNotification
from cli_agent_orchestrator.models.inbox import MessageStatus

try:
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover - imported only for typing
    Session = object  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)


class InboxReadError(ValueError):
    """Base error for inbox read failures."""


class InboxReadNotFoundError(InboxReadError):
    """Raised when the requested inbox notification is missing."""


def send(
    receiver_agent_id: str,
    body: str,
    *,
    sender_agent_id: str,
    db: Optional["Session"] = None,
    attempt_delivery: bool = True,
) -> InboxNotification:
    """Persist a notification and attempt immediate delivery to the live agent terminal."""
    from cli_agent_orchestrator.inbox.store import create_inbox_notification
    from cli_agent_orchestrator.inbox import readiness

    notification = create_inbox_notification(
        receiver_agent_id=receiver_agent_id,
        body=body,
        sender_agent_id=sender_agent_id,
        db=db,
    )
    if attempt_delivery and db is None:
        try:
            readiness.check_and_send_pending_messages(receiver_agent_id)
        except Exception as exc:
            logger.warning(
                "Immediate inbox delivery attempt failed for %s: %s",
                receiver_agent_id,
                exc,
            )
    return notification


def read(notification_id: int, caller_agent_id: str) -> ReadResult:
    """Read one inbox notification for its owning agent."""
    caller_agent_id = _required_text(caller_agent_id, "caller_agent_id")
    notification = get_notification(notification_id)
    if notification is None:
        raise InboxReadNotFoundError(f"inbox notification {notification_id} not found")

    if not _agent_owns_receiver(notification.receiver_agent_id, caller_agent_id):
        raise InboxReadError("caller agent is not authorized for this inbox notification")

    return ReadResult(notification=_public_notification(notification), body=notification.body)


def get_notification(notification_id: int, *, db: Optional["Session"] = None) -> Optional[InboxNotification]:
    """Read one inbox notification by id."""
    from cli_agent_orchestrator.inbox.store import get_inbox_notification

    return get_inbox_notification(notification_id, db=db)


def list_notifications(
    receiver_agent_id: str,
    *,
    limit: int = 10,
    status: Optional[MessageStatus] = None,
) -> list[InboxNotification]:
    """List notifications for one receiver agent."""
    from cli_agent_orchestrator.inbox.store import list_inbox_notifications

    return list_inbox_notifications(receiver_agent_id, limit=limit, status=status)


def list_pending_notifications(
    receiver_agent_id: str,
    *,
    limit: int = 10,
) -> list[InboxNotification]:
    """List pending notifications for one receiver agent."""
    return list_notifications(receiver_agent_id, limit=limit, status=MessageStatus.PENDING)


def oldest_pending_notification(receiver_agent_id: str) -> Optional[InboxNotification]:
    """Read the oldest pending notification for one receiver agent."""
    notifications = list_pending_notifications(receiver_agent_id, limit=1)
    return notifications[0] if notifications else None


def list_pending_notifications_for_sender(
    receiver_agent_id: str,
    source_notification: InboxNotification,
) -> list[InboxNotification]:
    """List pending notifications from the same sender as ``source_notification``."""
    from cli_agent_orchestrator.inbox.store import list_pending_inbox_notifications_for_sender

    return list_pending_inbox_notifications_for_sender(receiver_agent_id, source_notification)


def update_notification_statuses(
    notification_ids: Sequence[int],
    status: MessageStatus,
    *,
    error_detail: Optional[str] = None,
) -> int:
    """Update delivery state for inbox notifications."""
    from cli_agent_orchestrator.inbox.store import update_inbox_notification_statuses

    return update_inbox_notification_statuses(
        notification_ids,
        status,
        error_detail=error_detail,
    )


def update_notification_status(
    notification_id: int,
    status: MessageStatus,
    *,
    error_detail: Optional[str] = None,
) -> bool:
    """Update delivery state for one inbox notification."""
    from cli_agent_orchestrator.inbox.store import update_inbox_notification_status

    return update_inbox_notification_status(
        notification_id,
        status,
        error_detail=error_detail,
    )


def list_notifications_involving_agent(
    agent_id: str,
    *,
    db: "Session",
    peers: Optional[Sequence[str]] = None,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
) -> list[InboxNotification]:
    """List inbox notifications involving one agent within an optional window."""
    from sqlalchemy import or_

    from cli_agent_orchestrator.inbox.store import (
        InboxNotificationModel,
        inbox_notification_from_model,
    )

    query = db.query(InboxNotificationModel).filter(
        or_(
            InboxNotificationModel.sender_agent_id == agent_id,
            InboxNotificationModel.receiver_agent_id == agent_id,
        ),
    )
    if peers:
        query = query.filter(
            or_(
                InboxNotificationModel.sender_agent_id.in_(list(peers)),
                InboxNotificationModel.receiver_agent_id.in_(list(peers)),
            )
        )
    if started_at is not None:
        query = query.filter(InboxNotificationModel.created_at >= started_at)
    if ended_at is not None:
        query = query.filter(InboxNotificationModel.created_at <= ended_at)
    rows = query.order_by(
        InboxNotificationModel.created_at.asc(),
        InboxNotificationModel.id.asc(),
    ).all()
    return [inbox_notification_from_model(row) for row in rows]


def pending_notification_ids_for_receivers(receiver_agent_ids: Iterable[str]) -> set[int]:
    """Return pending notification ids for the given receiver agents."""
    from cli_agent_orchestrator.clients import database as db_module
    from cli_agent_orchestrator.inbox.store import InboxNotificationModel

    normalized_receiver_ids = tuple(dict.fromkeys(receiver_agent_ids))
    if not normalized_receiver_ids:
        return set()
    with db_module.SessionLocal() as session:
        rows = (
            session.query(InboxNotificationModel.id)
            .filter(
                InboxNotificationModel.receiver_agent_id.in_(normalized_receiver_ids),
                InboxNotificationModel.status == MessageStatus.PENDING.value,
            )
            .all()
        )
    return {int(row[0]) for row in rows}


def any_notification_delivered(notification_ids: Iterable[int]) -> bool:
    """Return whether any of the provided notifications has been delivered."""
    from cli_agent_orchestrator.clients import database as db_module
    from cli_agent_orchestrator.inbox.store import InboxNotificationModel

    normalized_ids = list(dict.fromkeys(notification_ids))
    if not normalized_ids:
        return False
    with db_module.SessionLocal() as session:
        return (
            session.query(InboxNotificationModel.id)
            .filter(
                InboxNotificationModel.id.in_(normalized_ids),
                InboxNotificationModel.status == MessageStatus.DELIVERED.value,
            )
            .first()
            is not None
        )


def delete_notification(notification_id: int, *, db: "Session") -> int:
    """Delete one inbox notification inside the caller's transaction."""
    from cli_agent_orchestrator.inbox.store import InboxNotificationModel

    return (
        db.query(InboxNotificationModel)
        .filter(InboxNotificationModel.id == notification_id)
        .delete()
    )


def delete_completed_notifications_before(cutoff_date: datetime, *, session_factory=None) -> int:
    """Delete delivered or failed inbox notifications older than ``cutoff_date``."""
    from cli_agent_orchestrator.clients import database as db_module
    from cli_agent_orchestrator.inbox.store import InboxNotificationModel

    make_session = session_factory or db_module.SessionLocal
    with make_session() as db:
        deleted_notifications = (
            db.query(InboxNotificationModel)
            .filter(
                InboxNotificationModel.created_at < cutoff_date,
                InboxNotificationModel.status.in_(
                    [MessageStatus.DELIVERED.value, MessageStatus.FAILED.value]
                ),
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        return int(deleted_notifications)


def ensure_notification_table(engine) -> None:
    """Create the inbox notification table when missing."""
    from cli_agent_orchestrator.inbox.store import InboxNotificationModel

    InboxNotificationModel.__table__.create(bind=engine, checkfirst=True)


def schedule_log_delivery_watcher(observer, log_dir: str | Path) -> None:
    """Schedule terminal-log inbox delivery handling on a watchdog observer."""
    from cli_agent_orchestrator.inbox.readiness import LogFileHandler

    observer.schedule(LogFileHandler(), str(log_dir), recursive=False)


def _public_notification(notification) -> Notification:
    return Notification(
        id=notification.id,
        sender_agent_id=notification.sender_agent_id,
        receiver_agent_id=notification.receiver_agent_id,
        body=notification.body,
        status=notification.status,
        created_at=notification.created_at,
        delivered_at=notification.delivered_at,
        failed_at=notification.failed_at,
        error_detail=notification.error_detail,
    )


def _agent_owns_receiver(receiver_agent_id: str, caller_agent_id: str) -> bool:
    return receiver_agent_id == caller_agent_id


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


__all__ = [
    "InboxReadError",
    "InboxReadNotFoundError",
    "InboxNotification",
    "MessageStatus",
    "Notification",
    "ReadResult",
    "any_notification_delivered",
    "delete_completed_notifications_before",
    "delete_notification",
    "ensure_notification_table",
    "get_notification",
    "list_notifications",
    "list_notifications_involving_agent",
    "list_pending_notifications",
    "list_pending_notifications_for_sender",
    "oldest_pending_notification",
    "pending_notification_ids_for_receivers",
    "read",
    "schedule_log_delivery_watcher",
    "send",
    "update_notification_status",
    "update_notification_statuses",
]

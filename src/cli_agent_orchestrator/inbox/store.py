"""Inbox notification persistence."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence, cast

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

from cli_agent_orchestrator.clients.database_core import Base
from cli_agent_orchestrator.models.inbox import InboxNotification, MessageStatus


class InboxNotificationModel(Base):
    """SQLAlchemy model for agent-to-agent inbox notifications."""

    __tablename__ = "inbox_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_agent_id = Column(String, nullable=False)
    receiver_agent_id = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    delivered_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    error_detail = Column(Text, nullable=True)


def _session_local():
    from cli_agent_orchestrator.clients import database as db_module

    return db_module.SessionLocal


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def inbox_notification_from_model(row: InboxNotificationModel) -> InboxNotification:
    """Convert an inbox notification row to its domain model."""
    return InboxNotification(
        id=cast(int, row.id),
        sender_agent_id=cast(str, row.sender_agent_id),
        receiver_agent_id=cast(str, row.receiver_agent_id),
        body=cast(str, row.body),
        status=MessageStatus(cast(str, row.status)),
        created_at=cast(datetime, row.created_at),
        delivered_at=cast(Optional[datetime], row.delivered_at),
        failed_at=cast(Optional[datetime], row.failed_at),
        error_detail=cast(Optional[str], row.error_detail),
    )


def create_inbox_notification(
    receiver_agent_id: str,
    body: str,
    *,
    sender_agent_id: str,
    status: MessageStatus = MessageStatus.PENDING,
    db: Optional[Session] = None,
) -> InboxNotification:
    """Create one agent-to-agent inbox notification."""
    receiver_agent_id = _required_text(receiver_agent_id, "receiver_agent_id")
    sender_agent_id = _required_text(sender_agent_id, "sender_agent_id")
    body = _required_text(body, "body")

    def _add_notification(session: Session) -> InboxNotification:
        notification_row = InboxNotificationModel(
            sender_agent_id=sender_agent_id,
            receiver_agent_id=receiver_agent_id,
            body=body,
            status=status.value,
        )
        session.add(notification_row)
        session.flush()
        session.refresh(notification_row)
        return inbox_notification_from_model(notification_row)

    if db is not None:
        return _add_notification(db)

    with _session_local()() as session:
        notification = _add_notification(session)
        session.commit()
        return notification


def get_inbox_notification(
    notification_id: int, *, db: Optional[Session] = None
) -> Optional[InboxNotification]:
    """Read one inbox notification by id."""

    def _get(session: Session) -> Optional[InboxNotification]:
        notification_row = session.get(InboxNotificationModel, notification_id)
        return None if notification_row is None else inbox_notification_from_model(notification_row)

    if db is not None:
        return _get(db)
    with _session_local()() as session:
        return _get(session)


def list_inbox_notifications(
    receiver_agent_id: str,
    limit: int = 10,
    status: Optional[MessageStatus] = None,
) -> List[InboxNotification]:
    """List inbox notifications for one receiver."""
    receiver_agent_id = _required_text(receiver_agent_id, "receiver_agent_id")
    with _session_local()() as db:
        query = db.query(InboxNotificationModel).filter(
            InboxNotificationModel.receiver_agent_id == receiver_agent_id
        )
        if status is not None:
            query = query.filter(InboxNotificationModel.status == status.value)
        notification_rows = (
            query.order_by(InboxNotificationModel.created_at.asc(), InboxNotificationModel.id.asc())
            .limit(limit)
            .all()
        )
        return [inbox_notification_from_model(row) for row in notification_rows]


def list_pending_inbox_notifications(
    receiver_agent_id: str, limit: int = 10
) -> List[InboxNotification]:
    """List pending notifications for a receiver."""
    return list_inbox_notifications(receiver_agent_id, limit=limit, status=MessageStatus.PENDING)


def get_oldest_pending_inbox_notification(receiver_agent_id: str) -> Optional[InboxNotification]:
    """Get the oldest pending notification for a receiver."""
    notifications = list_pending_inbox_notifications(receiver_agent_id, limit=1)
    return notifications[0] if notifications else None


def list_pending_inbox_notifications_for_sender(
    receiver_agent_id: str, source_notification: InboxNotification
) -> List[InboxNotification]:
    """List pending notifications from the same sender as ``source_notification``."""
    sender_agent_id = source_notification.sender_agent_id
    with _session_local()() as db:
        notification_rows = (
            db.query(InboxNotificationModel)
            .filter(
                InboxNotificationModel.receiver_agent_id == receiver_agent_id,
                InboxNotificationModel.status == MessageStatus.PENDING.value,
                InboxNotificationModel.sender_agent_id == sender_agent_id,
            )
            .order_by(InboxNotificationModel.created_at.asc(), InboxNotificationModel.id.asc())
            .all()
        )
        return [inbox_notification_from_model(row) for row in notification_rows]


def _apply_notification_status(
    notification: InboxNotificationModel, status: MessageStatus, error_detail: Optional[str]
) -> None:
    setattr(notification, "status", status.value)
    if status == MessageStatus.DELIVERED:
        setattr(notification, "delivered_at", datetime.now())
        setattr(notification, "failed_at", None)
        setattr(notification, "error_detail", None)
    elif status == MessageStatus.FAILED:
        setattr(notification, "failed_at", datetime.now())
        setattr(notification, "error_detail", error_detail)
    else:
        setattr(notification, "delivered_at", None)
        setattr(notification, "failed_at", None)
        setattr(notification, "error_detail", None)


def update_inbox_notification_statuses(
    notification_ids: Sequence[int],
    status: MessageStatus,
    *,
    error_detail: Optional[str] = None,
) -> int:
    """Update delivery state for inbox notifications."""
    if not notification_ids:
        return 0

    with _session_local()() as db:
        rows = (
            db.query(InboxNotificationModel)
            .filter(InboxNotificationModel.id.in_(list(notification_ids)))
            .all()
        )
        for row in rows:
            _apply_notification_status(row, status, error_detail)
        db.commit()
        return len(rows)


def update_inbox_notification_status(
    notification_id: int,
    status: MessageStatus,
    *,
    error_detail: Optional[str] = None,
) -> bool:
    """Update delivery state for one inbox notification."""
    return (
        update_inbox_notification_statuses(
            [notification_id],
            status,
            error_detail=error_detail,
        )
        == 1
    )

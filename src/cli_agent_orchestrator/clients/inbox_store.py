"""Inbox message and delivery-notification persistence."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Session

from cli_agent_orchestrator.clients.database_core import Base
from cli_agent_orchestrator.models.inbox import (
    InboxDelivery,
    InboxMessageRecord,
    InboxNotification,
    InboxNotificationTarget,
    MessageStatus,
)

MAX_NOTIFICATION_METADATA_JSON_CHARS = 4000
INBOX_NOTIFICATION_TARGET_KIND_MESSAGE = "inbox_message"
INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY = "primary"


class InboxMessageModel(Base):
    """SQLAlchemy model for durable semantic inbox messages."""

    __tablename__ = "inbox_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    source_kind = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    origin_json = Column(Text, nullable=True)
    route_kind = Column(String, nullable=True)
    route_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class InboxNotificationModel(Base):
    """SQLAlchemy model for per-recipient inbox attention notifications."""

    __tablename__ = "inbox_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receiver_id = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    source_kind = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    metadata_json = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    delivered_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    error_detail = Column(Text, nullable=True)


class InboxNotificationTargetModel(Base):
    """SQLAlchemy model linking notifications to first-class CAO targets."""

    __tablename__ = "inbox_notification_targets"
    __table_args__ = (
        UniqueConstraint(
            "notification_id",
            "target_kind",
            "target_id",
            "role",
            name="uq_inbox_notification_target_link",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    notification_id = Column(
        Integer,
        ForeignKey("inbox_notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_kind = Column(String, nullable=False)
    target_id = Column(String, nullable=False)
    role = Column(String, nullable=False)


def _session_local():
    from cli_agent_orchestrator.clients import database as db_module

    return db_module.SessionLocal


def _validate_complete_identity(
    kind: Optional[str], identity_id: Optional[str], label: str
) -> None:
    if (kind is None) != (identity_id is None):
        raise ValueError(f"{label}_kind and {label}_id must be provided together")


def _resolve_source_identity(
    sender_id: str, source_kind: Optional[str], source_id: Optional[str]
) -> Tuple[str, str]:
    _validate_complete_identity(source_kind, source_id, "source")
    if source_kind is None and source_id is None:
        return "terminal", sender_id
    assert source_kind is not None and source_id is not None
    return source_kind, source_id


def _serialize_origin(origin: Optional[Dict[str, Any]]) -> Optional[str]:
    if origin is None:
        return None
    return json.dumps(origin, sort_keys=True)


def _serialize_notification_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    if metadata is None:
        return None
    encoded = json.dumps(metadata, sort_keys=True)
    if len(encoded) > MAX_NOTIFICATION_METADATA_JSON_CHARS:
        raise ValueError(
            "notification metadata exceeds "
            f"{MAX_NOTIFICATION_METADATA_JSON_CHARS} JSON characters"
        )
    return encoded


def _deserialize_origin(origin_json: Optional[str]) -> Optional[Dict[str, Any]]:
    if origin_json is None:
        return None
    value = json.loads(origin_json)
    return value if isinstance(value, dict) else None


def inbox_message_record_from_model(row: InboxMessageModel) -> InboxMessageRecord:
    """Convert a durable inbox message row to its domain model."""
    return InboxMessageRecord(
        id=row.id,
        sender_id=row.sender_id,
        body=row.body,
        source_kind=row.source_kind,
        source_id=row.source_id,
        origin=_deserialize_origin(row.origin_json),
        route_kind=row.route_kind,
        route_id=row.route_id,
        created_at=row.created_at,
    )


def inbox_notification_from_model(row: InboxNotificationModel) -> InboxNotification:
    """Convert an inbox notification row to its domain model."""
    return InboxNotification(
        id=row.id,
        receiver_id=row.receiver_id,
        body=row.body,
        source_kind=row.source_kind,
        source_id=row.source_id,
        metadata=_deserialize_origin(row.metadata_json),
        status=MessageStatus(row.status),
        created_at=row.created_at,
        delivered_at=row.delivered_at,
        failed_at=row.failed_at,
        error_detail=row.error_detail,
    )


def inbox_notification_target_from_model(
    row: InboxNotificationTargetModel,
) -> InboxNotificationTarget:
    """Convert an inbox notification target row to its domain model."""
    return InboxNotificationTarget(
        id=row.id,
        notification_id=row.notification_id,
        target_kind=row.target_kind,
        target_id=row.target_id,
        role=row.role,
    )


def inbox_delivery_from_models(
    message_row: Optional[InboxMessageModel],
    notification_row: InboxNotificationModel,
    target_rows: Optional[Sequence[InboxNotificationTargetModel]] = None,
) -> InboxDelivery:
    """Convert joined semantic inbox rows to their domain model."""
    return InboxDelivery(
        message=inbox_message_record_from_model(message_row) if message_row is not None else None,
        notification=inbox_notification_from_model(notification_row),
        targets=[
            inbox_notification_target_from_model(target_row) for target_row in (target_rows or [])
        ],
    )


def _add_primary_inbox_message_target(
    session: Session, *, notification_id: int, message_id: int
) -> InboxNotificationTargetModel:
    target_row = InboxNotificationTargetModel(
        notification_id=notification_id,
        target_kind=INBOX_NOTIFICATION_TARGET_KIND_MESSAGE,
        target_id=str(message_id),
        role=INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY,
    )
    session.add(target_row)
    session.flush()
    return target_row


def _primary_inbox_message_target(
    target_rows: Sequence[InboxNotificationTargetModel],
) -> Optional[InboxNotificationTargetModel]:
    for target_row in target_rows:
        if (
            target_row.target_kind == INBOX_NOTIFICATION_TARGET_KIND_MESSAGE
            and target_row.role == INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY
        ):
            return target_row
    return None


def _message_for_target(
    session: Session, target_row: Optional[InboxNotificationTargetModel]
) -> Optional[InboxMessageModel]:
    if target_row is None:
        return None
    try:
        message_id = int(target_row.target_id)
    except ValueError:
        return None
    return session.get(InboxMessageModel, message_id)


def _target_rows_for_notification(
    session: Session, notification_id: int
) -> List[InboxNotificationTargetModel]:
    return (
        session.query(InboxNotificationTargetModel)
        .filter(InboxNotificationTargetModel.notification_id == notification_id)
        .order_by(InboxNotificationTargetModel.id.asc())
        .all()
    )


def _delivery_from_notification_row(
    session: Session, notification_row: InboxNotificationModel
) -> InboxDelivery:
    target_rows = _target_rows_for_notification(session, notification_row.id)
    return inbox_delivery_from_models(
        _message_for_target(session, _primary_inbox_message_target(target_rows)),
        notification_row,
        target_rows,
    )


def create_inbox_delivery(
    sender_id: str,
    receiver_id: str,
    message: str,
    *,
    source_kind: Optional[str] = None,
    source_id: Optional[str] = None,
    origin: Optional[Dict[str, Any]] = None,
    route_kind: Optional[str] = None,
    route_id: Optional[str] = None,
    notification_body: Optional[str] = None,
    notification_metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> InboxDelivery:
    """Create one durable inbox message and one attention notification."""
    effective_source_kind, effective_source_id = _resolve_source_identity(
        sender_id, source_kind, source_id
    )
    _validate_complete_identity(route_kind, route_id, "route")

    def _add_delivery(session: Session) -> InboxDelivery:
        message_row = InboxMessageModel(
            sender_id=sender_id,
            body=message,
            source_kind=effective_source_kind,
            source_id=effective_source_id,
            origin_json=_serialize_origin(origin),
            route_kind=route_kind,
            route_id=route_id,
        )
        session.add(message_row)
        session.flush()
        notification_row = InboxNotificationModel(
            receiver_id=receiver_id,
            body=notification_body if notification_body is not None else message,
            source_kind=effective_source_kind,
            source_id=effective_source_id,
            metadata_json=_serialize_notification_metadata(notification_metadata),
            status=MessageStatus.PENDING.value,
        )
        session.add(notification_row)
        session.flush()
        target_row = _add_primary_inbox_message_target(
            session, notification_id=notification_row.id, message_id=message_row.id
        )
        session.refresh(message_row)
        session.refresh(notification_row)
        session.refresh(target_row)
        return inbox_delivery_from_models(message_row, notification_row, [target_row])

    if db is not None:
        return _add_delivery(db)

    with _session_local()() as session:
        delivery = _add_delivery(session)
        session.commit()
        return delivery


def create_inbox_message_record(
    sender_id: str,
    message: str,
    *,
    source_kind: Optional[str] = None,
    source_id: Optional[str] = None,
    origin: Optional[Dict[str, Any]] = None,
    route_kind: Optional[str] = None,
    route_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> InboxMessageRecord:
    """Create a durable inbox message without creating delivery state."""
    effective_source_kind, effective_source_id = _resolve_source_identity(
        sender_id, source_kind, source_id
    )
    _validate_complete_identity(route_kind, route_id, "route")

    def _add_message(session: Session) -> InboxMessageRecord:
        message_row = InboxMessageModel(
            sender_id=sender_id,
            body=message,
            source_kind=effective_source_kind,
            source_id=effective_source_id,
            origin_json=_serialize_origin(origin),
            route_kind=route_kind,
            route_id=route_id,
        )
        session.add(message_row)
        session.flush()
        session.refresh(message_row)
        return inbox_message_record_from_model(message_row)

    if db is not None:
        return _add_message(db)

    with _session_local()() as session:
        record = _add_message(session)
        session.commit()
        return record


def create_inbox_notification(
    message_id: int,
    receiver_id: str,
    *,
    body: Optional[str] = None,
    source_kind: Optional[str] = None,
    source_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    status: MessageStatus = MessageStatus.PENDING,
    db: Optional[Session] = None,
) -> InboxNotification:
    """Create an attention notification for an existing durable inbox message."""
    _validate_complete_identity(source_kind, source_id, "source")

    def _add_notification(session: Session) -> InboxNotification:
        message_row = session.get(InboxMessageModel, message_id)
        if message_row is None:
            raise ValueError(f"Inbox message not found: {message_id}")
        notification_row = InboxNotificationModel(
            receiver_id=receiver_id,
            body=body if body is not None else message_row.body,
            source_kind=source_kind if source_kind is not None else message_row.source_kind,
            source_id=source_id if source_id is not None else message_row.source_id,
            metadata_json=_serialize_notification_metadata(metadata),
            status=status.value,
        )
        session.add(notification_row)
        session.flush()
        _add_primary_inbox_message_target(
            session, notification_id=notification_row.id, message_id=message_id
        )
        session.refresh(notification_row)
        return inbox_notification_from_model(notification_row)

    if db is not None:
        return _add_notification(db)

    with _session_local()() as session:
        notification = _add_notification(session)
        session.commit()
        return notification


def create_inbox_notification_event(
    receiver_id: str,
    body: str,
    *,
    source_kind: str,
    source_id: str,
    metadata: Optional[Dict[str, Any]] = None,
    status: MessageStatus = MessageStatus.PENDING,
    db: Optional[Session] = None,
) -> InboxNotification:
    """Create an attention notification that is not backed by a CAO message."""
    if not body:
        raise ValueError("notification body is required")
    if not receiver_id:
        raise ValueError("receiver_id is required")
    _validate_complete_identity(source_kind, source_id, "source")

    def _add_notification(session: Session) -> InboxNotification:
        notification_row = InboxNotificationModel(
            receiver_id=receiver_id,
            body=body,
            source_kind=source_kind,
            source_id=source_id,
            metadata_json=_serialize_notification_metadata(metadata),
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


def _get_delivery_by_notification_id(
    session: Session, notification_id: int
) -> Optional[InboxDelivery]:
    notification_row = session.get(InboxNotificationModel, notification_id)
    if notification_row is None:
        return None
    return _delivery_from_notification_row(session, notification_row)


def get_inbox_delivery(
    notification_id: int, *, db: Optional[Session] = None
) -> Optional[InboxDelivery]:
    """Read one notification-backed inbox message by notification id."""
    if db is not None:
        return _get_delivery_by_notification_id(db, notification_id)
    with _session_local()() as session:
        return _get_delivery_by_notification_id(session, notification_id)


def list_inbox_deliveries(
    receiver_id: str, limit: int = 10, status: Optional[MessageStatus] = None
) -> List[InboxDelivery]:
    """List notification-backed inbox messages for one receiver."""
    with _session_local()() as db:
        query = db.query(InboxNotificationModel).filter(
            InboxNotificationModel.receiver_id == receiver_id
        )
        if status is not None:
            query = query.filter(InboxNotificationModel.status == status.value)
        notification_rows = (
            query.order_by(InboxNotificationModel.created_at.asc(), InboxNotificationModel.id.asc())
            .limit(limit)
            .all()
        )
        return [
            _delivery_from_notification_row(db, notification_row)
            for notification_row in notification_rows
        ]


def list_pending_inbox_notifications(receiver_id: str, limit: int = 10) -> List[InboxDelivery]:
    """List pending notification-backed messages for a receiver."""
    return list_inbox_deliveries(receiver_id, limit=limit, status=MessageStatus.PENDING)


def get_oldest_pending_inbox_delivery(receiver_id: str) -> Optional[InboxDelivery]:
    """Get the oldest pending semantic delivery notification for a receiver."""
    deliveries = list_pending_inbox_notifications(receiver_id, limit=1)
    return deliveries[0] if deliveries else None


def list_pending_inbox_deliveries_for_effective_source(
    receiver_id: str, source_delivery: InboxDelivery
) -> List[InboxDelivery]:
    """List pending notifications for the same attention source as ``source_delivery``."""
    source_notification = source_delivery.notification
    with _session_local()() as db:
        notification_rows = (
            db.query(InboxNotificationModel)
            .filter(
                InboxNotificationModel.receiver_id == receiver_id,
                InboxNotificationModel.status == MessageStatus.PENDING.value,
                InboxNotificationModel.source_kind == source_notification.source_kind,
                InboxNotificationModel.source_id == source_notification.source_id,
            )
            .order_by(InboxNotificationModel.created_at.asc(), InboxNotificationModel.id.asc())
            .all()
        )
        return [
            _delivery_from_notification_row(db, notification_row)
            for notification_row in notification_rows
        ]


def move_pending_inbox_notifications(
    current_receiver_id: str,
    new_receiver_id: str,
) -> int:
    """Move pending semantic delivery notifications to a new receiver id."""
    with _session_local()() as db:
        updated = (
            db.query(InboxNotificationModel)
            .filter(
                InboxNotificationModel.receiver_id == current_receiver_id,
                InboxNotificationModel.status == MessageStatus.PENDING.value,
            )
            .update(
                {InboxNotificationModel.receiver_id: new_receiver_id},
                synchronize_session=False,
            )
        )
        db.commit()
        return int(updated or 0)


def update_inbox_notification_receiver(notification_id: int, receiver_id: str) -> bool:
    """Update one semantic notification recipient."""
    with _session_local()() as db:
        row = db.get(InboxNotificationModel, notification_id)
        if row is None:
            return False
        row.receiver_id = receiver_id
        db.commit()
        return True


def _apply_notification_status(
    notification: InboxNotificationModel, status: MessageStatus, error_detail: Optional[str]
) -> None:
    notification.status = status.value
    if status == MessageStatus.DELIVERED:
        notification.delivered_at = datetime.now()
        notification.failed_at = None
        notification.error_detail = None
    elif status == MessageStatus.FAILED:
        notification.failed_at = datetime.now()
        notification.error_detail = error_detail
    else:
        notification.delivered_at = None
        notification.failed_at = None
        notification.error_detail = None


def update_inbox_notification_statuses(
    notification_ids: Sequence[int],
    status: MessageStatus,
    *,
    error_detail: Optional[str] = None,
) -> int:
    """Update delivery state for semantic inbox notifications."""
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
    """Update one semantic inbox notification by notification id."""
    return (
        update_inbox_notification_statuses([notification_id], status, error_detail=error_detail) > 0
    )

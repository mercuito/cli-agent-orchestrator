"""Bridge durable provider-neutral presence messages into terminal inbox notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, cast

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxDelivery
from cli_agent_orchestrator.presence.models import PersistedPresenceEvent

PRESENCE_INBOX_SOURCE_KIND = "presence_thread"
PRESENCE_INBOX_ROUTE_KIND = "presence_thread"
PRESENCE_INBOX_SENDER_ID = "presence"
DEFAULT_PREVIEW_CHARS = 240
DEFAULT_NOTIFICATION_CHARS = 700
MAX_NOTIFICATION_METADATA_JSON_CHARS = 4000


@dataclass(frozen=True)
class PresenceInboxNotification:
    """Result of bridging one persisted presence message into the inbox."""

    delivery: InboxDelivery
    created: bool


def create_notification_for_persisted_event(
    persisted_event: PersistedPresenceEvent,
    *,
    receiver_id: str,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    notification_chars: int = DEFAULT_NOTIFICATION_CHARS,
) -> PresenceInboxNotification:
    """Create a terminal inbox notification for a persisted presence event.

    The persisted event must include a durable message record. Receiver selection
    stays explicit and caller-owned; this bridge does not route by agent identity.
    """

    if persisted_event.message is None:
        raise ValueError("persisted presence event has no message to notify")
    return create_notification_for_message(
        presence_message_id=persisted_event.message.id,
        receiver_id=receiver_id,
        preview_chars=preview_chars,
        notification_chars=notification_chars,
    )


def create_notification_for_message(
    *,
    presence_message_id: int,
    receiver_id: str,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    notification_chars: int = DEFAULT_NOTIFICATION_CHARS,
) -> PresenceInboxNotification:
    """Create or return the inbox notification for a persisted presence message."""

    if not receiver_id:
        raise ValueError("receiver_id is required")
    if presence_message_id <= 0:
        raise ValueError("presence_message_id must be positive")

    with db_module.SessionLocal() as session:
        existing = _get_existing_notification(session, receiver_id, presence_message_id)
        if existing is not None:
            return PresenceInboxNotification(delivery=existing, created=False)

        message_row = (
            session.query(db_module.PresenceMessageModel)
            .filter(db_module.PresenceMessageModel.id == presence_message_id)
            .first()
        )
        if message_row is None:
            raise ValueError(f"presence message {presence_message_id} not found")

        thread_row = (
            session.query(db_module.PresenceThreadModel)
            .filter(db_module.PresenceThreadModel.id == message_row.thread_id)
            .first()
        )
        if thread_row is None:
            raise ValueError(
                f"presence thread {message_row.thread_id} for message {presence_message_id} not found"
            )

        work_item_row = None
        if thread_row.work_item_id is not None:
            work_item_row = (
                session.query(db_module.PresenceWorkItemModel)
                .filter(db_module.PresenceWorkItemModel.id == thread_row.work_item_id)
                .first()
            )

        delivery = db_module.create_inbox_delivery(
            PRESENCE_INBOX_SENDER_ID,
            receiver_id,
            _presence_message_body(message_row, thread_row),
            db=session,
            source_kind=PRESENCE_INBOX_SOURCE_KIND,
            source_id=str(thread_row.id),
            origin=_presence_message_origin(message_row),
            route_kind=PRESENCE_INBOX_ROUTE_KIND,
            route_id=str(thread_row.id),
            notification_body=format_presence_notification(
                inbox_notification_id=0,
                message_row=message_row,
                thread_row=thread_row,
                work_item_row=work_item_row,
                preview_chars=preview_chars,
                notification_chars=notification_chars,
            ),
        )
        notification_row = session.get(db_module.InboxNotificationModel, delivery.notification.id)
        if notification_row is None:
            raise RuntimeError(f"inbox notification {delivery.notification.id} not found")
        mutable_notification_row = cast(Any, notification_row)
        mutable_notification_row.body = format_presence_notification(
            inbox_notification_id=cast(int, delivery.notification.id),
            message_row=message_row,
            thread_row=thread_row,
            work_item_row=work_item_row,
            preview_chars=preview_chars,
            notification_chars=notification_chars,
        )
        session.flush()

        inserted = session.execute(
            sqlite_insert(db_module.PresenceInboxNotificationModel)
            .values(
                receiver_id=receiver_id,
                presence_message_id=presence_message_id,
                inbox_notification_id=delivery.notification.id,
                created_at=datetime.now(),
            )
            .on_conflict_do_nothing(index_elements=["receiver_id", "presence_message_id"])
        )
        if inserted.rowcount == 1:
            refreshed = db_module.get_inbox_delivery(delivery.notification.id, db=session)
            if refreshed is None:
                raise RuntimeError(
                    f"inbox notification {delivery.notification.id} for presence message "
                    f"{presence_message_id} not found"
                )
            session.commit()
            return PresenceInboxNotification(delivery=refreshed, created=True)

        if delivery.message is None:
            raise RuntimeError("message-backed presence notification lost its durable message")
        notification_row = session.get(db_module.InboxNotificationModel, delivery.notification.id)
        if notification_row is not None:
            session.delete(notification_row)
        durable_message_row = session.get(db_module.InboxMessageModel, delivery.message.id)
        if durable_message_row is not None:
            session.delete(durable_message_row)
        session.flush()
        existing = _get_existing_notification(session, receiver_id, presence_message_id)
        if existing is None:
            raise RuntimeError("presence inbox notification insert conflicted without existing row")
        session.commit()
        return PresenceInboxNotification(delivery=existing, created=False)


def format_presence_notification(
    *,
    inbox_notification_id: int,
    message_row: db_module.PresenceMessageModel,
    thread_row: db_module.PresenceThreadModel,
    work_item_row: Optional[db_module.PresenceWorkItemModel] = None,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    notification_chars: int = DEFAULT_NOTIFICATION_CHARS,
) -> str:
    """Build the compact agent-visible notification sent through the inbox."""

    lines = [
        "[CAO inbox notification]",
        f"ID: {inbox_notification_id}",
        f"Preview: {_preview(cast(Optional[str], message_row.body), preview_chars)}",
        f"Source: {_format_source(message_row, thread_row)}",
        _format_author(message_row),
        _format_work_item(work_item_row),
    ]
    if _metadata_indicates_media(
        cast(Optional[str], message_row.metadata_json)
    ) or _metadata_indicates_media(cast(Optional[str], message_row.raw_snapshot_json)):
        lines.append("Attachment/media metadata present.")
    guidance = "\n".join(
        [
            "",
            f"Read: read_inbox_message(notification_id={inbox_notification_id}).",
            "Reply: " f"reply_to_inbox_message(notification_id={inbox_notification_id}, body=...).",
        ]
    )
    body = "\n".join(line for line in lines if line)
    reserved = len(guidance) + 1
    if len(body) + reserved > notification_chars:
        body = _truncate(body, max(0, notification_chars - reserved))
    return f"{body}\n{guidance}" if body else guidance.lstrip()


def _get_existing_notification(
    session: Session, receiver_id: str, presence_message_id: int
) -> Optional[InboxDelivery]:
    row = (
        session.query(db_module.PresenceInboxNotificationModel)
        .filter(
            db_module.PresenceInboxNotificationModel.receiver_id == receiver_id,
            db_module.PresenceInboxNotificationModel.presence_message_id == presence_message_id,
        )
        .first()
    )
    if row is None:
        return None

    delivery = db_module.get_inbox_delivery(cast(int, row.inbox_notification_id), db=session)
    if delivery is not None:
        return delivery
    raise RuntimeError(
        "inbox notification "
        f"{row.inbox_notification_id} for presence message {presence_message_id} not found"
    )


def _presence_message_body(
    message_row: db_module.PresenceMessageModel,
    thread_row: db_module.PresenceThreadModel,
) -> str:
    body = _compact(cast(Optional[str], message_row.body))
    if body:
        return body
    return _compact(cast(Optional[str], thread_row.prompt_context)) or "(no text body)"


def _presence_message_origin(
    message_row: db_module.PresenceMessageModel,
) -> Optional[dict[str, Any]]:
    metadata = _load_json_object(cast(Optional[str], message_row.metadata_json))
    return dict(metadata) if metadata is not None else None


def _format_work_item(row: Optional[db_module.PresenceWorkItemModel]) -> Optional[str]:
    if row is None:
        return None

    parts = [_compact(cast(Optional[str], value)) for value in (row.identifier, row.title) if value]
    if not parts:
        return None
    return f"Issue: {_truncate(' - '.join(parts), 180)}"


def _format_source(
    message_row: db_module.PresenceMessageModel,
    thread_row: db_module.PresenceThreadModel,
) -> str:
    provider = _compact(cast(Optional[str], message_row.provider))
    if provider == "linear" and thread_row.kind == "conversation":
        return "Linear AgentSession"
    return provider or "provider presence"


def _format_author(row: db_module.PresenceMessageModel) -> Optional[str]:
    metadata = _load_json_object(cast(Optional[str], row.metadata_json))
    if not metadata:
        return None
    author = _find_author_metadata(metadata)
    if not author:
        return None
    return f"From: {_truncate(author, 120)}"


def _preview(body: Optional[str], max_chars: int) -> str:
    text = _compact(body)
    if not text:
        return "(no text body)"
    return _truncate(text, max_chars)


def _compact(value: Optional[str]) -> str:
    if value is None:
        return ""
    return " ".join(value.split())


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    suffix = "..."
    return value[: max(0, max_chars - len(suffix))].rstrip() + suffix


def _load_json_object(metadata_json: Optional[str]) -> Optional[dict[str, Any]]:
    if not metadata_json or len(metadata_json) > MAX_NOTIFICATION_METADATA_JSON_CHARS:
        return None
    try:
        metadata = json.loads(metadata_json)
    except Exception:
        return None
    return metadata if isinstance(metadata, dict) else None


def _metadata_indicates_media(metadata_json: Optional[str]) -> bool:
    metadata = _load_json_object(metadata_json)
    if metadata is None:
        return False
    return _contains_media_marker(metadata)


def _contains_media_marker(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(
                marker in normalized_key
                for marker in ("attachment", "media", "file", "image", "video", "audio")
            ) and bool(item):
                return True
            if _contains_media_marker(item):
                return True
    if isinstance(value, list):
        return any(_contains_media_marker(item) for item in value)
    return False


def _find_author_metadata(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        for key in ("actor", "author", "user", "creator"):
            item = value.get(key)
            if isinstance(item, dict):
                name = item.get("name") or item.get("displayName") or item.get("email")
                if name:
                    return _compact(str(name))
            elif isinstance(item, str) and item.strip():
                return _compact(item)
        data = value.get("data")
        if isinstance(data, dict):
            found = _find_author_metadata(data)
            if found:
                return found
        for item in value.values():
            found = _find_author_metadata(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_author_metadata(item)
            if found:
                return found
    return None

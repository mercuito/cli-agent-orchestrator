"""Bridge durable provider-neutral presence messages into terminal inbox notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, cast

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxMessage, MessageStatus
from cli_agent_orchestrator.presence.models import PersistedPresenceEvent

PRESENCE_INBOX_SOURCE_KIND = "presence_thread"
PRESENCE_INBOX_SENDER_ID = "presence"
DEFAULT_PREVIEW_CHARS = 240
DEFAULT_NOTIFICATION_CHARS = 700


@dataclass(frozen=True)
class PresenceInboxNotification:
    """Result of bridging one persisted presence message into the inbox."""

    inbox_message: InboxMessage
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
            return PresenceInboxNotification(inbox_message=existing, created=False)

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

        inbox_row = db_module.InboxModel(
            sender_id=PRESENCE_INBOX_SENDER_ID,
            receiver_id=receiver_id,
            message="[CAO inbox notification pending]",
            source_kind=PRESENCE_INBOX_SOURCE_KIND,
            source_id=str(thread_row.id),
            status=MessageStatus.PENDING.value,
            created_at=datetime.now(),
        )
        session.add(inbox_row)
        session.flush()
        mutable_inbox_row = cast(Any, inbox_row)
        mutable_inbox_row.message = format_presence_notification(
            inbox_message_id=cast(int, inbox_row.id),
            message_row=message_row,
            thread_row=thread_row,
            work_item_row=work_item_row,
            preview_chars=preview_chars,
            notification_chars=notification_chars,
        )
        session.flush()
        session.refresh(inbox_row)

        inserted = session.execute(
            sqlite_insert(db_module.PresenceInboxNotificationModel)
            .values(
                receiver_id=receiver_id,
                presence_message_id=presence_message_id,
                inbox_message_id=inbox_row.id,
                created_at=datetime.now(),
            )
            .on_conflict_do_nothing(index_elements=["receiver_id", "presence_message_id"])
        )
        if inserted.rowcount == 1:
            inbox_message = db_module.inbox_message_from_model(inbox_row)
            session.commit()
            return PresenceInboxNotification(inbox_message=inbox_message, created=True)

        session.delete(inbox_row)
        session.flush()
        existing = _get_existing_notification(session, receiver_id, presence_message_id)
        if existing is None:
            raise RuntimeError("presence inbox notification insert conflicted without existing row")
        session.commit()
        return PresenceInboxNotification(inbox_message=existing, created=False)


def format_presence_notification(
    *,
    inbox_message_id: int,
    message_row: db_module.PresenceMessageModel,
    thread_row: db_module.PresenceThreadModel,
    work_item_row: Optional[db_module.PresenceWorkItemModel] = None,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    notification_chars: int = DEFAULT_NOTIFICATION_CHARS,
) -> str:
    """Build a small human-readable notification body from persisted presence rows."""

    lines = [
        "[CAO inbox notification]",
        f"ID: {inbox_message_id}",
        f"Preview: {_preview(cast(Optional[str], message_row.body), preview_chars)}",
        f"Source: {_format_source(message_row, thread_row)}",
        _format_author(message_row),
        _format_work_item(work_item_row),
    ]
    if _metadata_indicates_media(
        cast(Optional[str], message_row.metadata_json)
    ) or _metadata_indicates_media(
        cast(Optional[str], message_row.raw_snapshot_json)
    ):
        lines.append("Attachment/media metadata present.")
    guidance = "\n".join(
        [
            "",
            f"Read: read_inbox_message(inbox_message_id={inbox_message_id}).",
            f"Reply: reply_to_inbox_message(inbox_message_id={inbox_message_id}, body=...).",
        ]
    )
    body = "\n".join(line for line in lines if line)
    reserved = len(guidance) + 1
    if len(body) + reserved > notification_chars:
        body = _truncate(body, max(0, notification_chars - reserved))
    return f"{body}\n{guidance}" if body else guidance.lstrip()


def _get_existing_notification(
    session: Session, receiver_id: str, presence_message_id: int
) -> Optional[InboxMessage]:
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

    inbox_row = (
        session.query(db_module.InboxModel)
        .filter(db_module.InboxModel.id == row.inbox_message_id)
        .first()
    )
    if inbox_row is None:
        raise RuntimeError(
            f"inbox message {row.inbox_message_id} for presence message {presence_message_id} not found"
        )
    return db_module.inbox_message_from_model(inbox_row)


def _format_work_item(row: Optional[db_module.PresenceWorkItemModel]) -> Optional[str]:
    if row is None:
        return None

    parts = [
        _compact(cast(Optional[str], value))
        for value in (row.identifier, row.title)
        if value
    ]
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
    metadata = _load_json_object(cast(Optional[str], row.metadata_json)) or _load_json_object(
        cast(Optional[str], row.raw_snapshot_json)
    )
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


def _metadata_indicates_media(metadata_json: Optional[str]) -> bool:
    metadata = _load_json_object(metadata_json)
    if metadata is None:
        return False
    return _contains_media_marker(metadata)


def _load_json_object(metadata_json: Optional[str]) -> Optional[dict[str, Any]]:
    if not metadata_json:
        return None
    try:
        metadata = json.loads(metadata_json)
    except Exception:
        return None
    return metadata if isinstance(metadata, dict) else None


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

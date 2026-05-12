"""Bridge provider-owned conversation messages into terminal inbox notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, cast

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxDelivery
from cli_agent_orchestrator.provider_conversations.inbox_read_presentation import (
    INBOX_READ_PRESENTATION_METADATA_KEY,
)
from cli_agent_orchestrator.provider_conversations.models import PersistedProviderEventRecords

PROVIDER_CONVERSATION_INBOX_SOURCE_KIND = "provider_conversation_thread"
PROVIDER_CONVERSATION_INBOX_ROUTE_KIND = "provider_conversation_thread"
PROVIDER_CONVERSATION_INBOX_SENDER_ID = "provider_conversation"
DEFAULT_PREVIEW_CHARS = 240
DEFAULT_NOTIFICATION_CHARS = 700
MAX_NOTIFICATION_METADATA_JSON_CHARS = 4000


@dataclass(frozen=True)
class ProviderConversationInboxNotification:
    """Result of bridging one persisted provider message into the inbox."""

    delivery: InboxDelivery
    created: bool


def create_notification_for_persisted_event(
    persisted_event: PersistedProviderEventRecords,
    *,
    receiver_id: str,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    notification_chars: int = DEFAULT_NOTIFICATION_CHARS,
) -> ProviderConversationInboxNotification:
    """Create a terminal inbox notification for a persisted provider event.

    The persisted event must include a durable message record. Receiver selection
    stays explicit and caller-owned; this bridge does not route by agent identity.
    """

    if persisted_event.message is None:
        raise ValueError("persisted provider event has no message to notify")
    return create_notification_for_message(
        provider_message_id=persisted_event.message.id,
        receiver_id=receiver_id,
        preview_chars=preview_chars,
        notification_chars=notification_chars,
    )


def create_notification_for_message(
    *,
    provider_message_id: int,
    receiver_id: str,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    notification_chars: int = DEFAULT_NOTIFICATION_CHARS,
) -> ProviderConversationInboxNotification:
    """Create or return the inbox notification for a persisted provider conversation message."""

    if not receiver_id:
        raise ValueError("receiver_id is required")
    if provider_message_id <= 0:
        raise ValueError("provider_message_id must be positive")

    with db_module.SessionLocal() as session:
        existing = _get_existing_notification(session, receiver_id, provider_message_id)
        if existing is not None:
            return ProviderConversationInboxNotification(delivery=existing, created=False)

        message_row = (
            session.query(db_module.ProviderConversationMessageModel)
            .filter(db_module.ProviderConversationMessageModel.id == provider_message_id)
            .first()
        )
        if message_row is None:
            raise ValueError(f"provider conversation message {provider_message_id} not found")

        thread_row = (
            session.query(db_module.ProviderConversationThreadModel)
            .filter(db_module.ProviderConversationThreadModel.id == message_row.thread_id)
            .first()
        )
        if thread_row is None:
            raise ValueError(
                f"provider conversation thread {message_row.thread_id} for message {provider_message_id} not found"
            )

        work_item_row = None
        if thread_row.work_item_id is not None:
            work_item_row = (
                session.query(db_module.ProviderWorkItemModel)
                .filter(db_module.ProviderWorkItemModel.id == thread_row.work_item_id)
                .first()
            )

        delivery = db_module.create_inbox_delivery(
            PROVIDER_CONVERSATION_INBOX_SENDER_ID,
            receiver_id,
            _provider_message_body(message_row, thread_row),
            db=session,
            source_kind=PROVIDER_CONVERSATION_INBOX_SOURCE_KIND,
            source_id=str(thread_row.id),
            origin=_provider_message_origin(message_row),
            route_kind=PROVIDER_CONVERSATION_INBOX_ROUTE_KIND,
            route_id=str(thread_row.id),
            notification_body=format_provider_conversation_notification(
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
        mutable_notification_row.body = format_provider_conversation_notification(
            inbox_notification_id=cast(int, delivery.notification.id),
            message_row=message_row,
            thread_row=thread_row,
            work_item_row=work_item_row,
            preview_chars=preview_chars,
            notification_chars=notification_chars,
        )
        session.flush()

        inserted = session.execute(
            sqlite_insert(db_module.ProviderConversationInboxNotificationModel)
            .values(
                receiver_id=receiver_id,
                provider_message_id=provider_message_id,
                inbox_notification_id=delivery.notification.id,
                created_at=datetime.now(),
            )
            .on_conflict_do_nothing(
                index_elements=[
                    db_module.ProviderConversationInboxNotificationModel.receiver_id,
                    db_module.ProviderConversationInboxNotificationModel.provider_message_id,
                ]
            )
        )
        if inserted.rowcount == 1:
            refreshed = db_module.get_inbox_delivery(delivery.notification.id, db=session)
            if refreshed is None:
                raise RuntimeError(
                    f"inbox notification {delivery.notification.id} for provider conversation message "
                    f"{provider_message_id} not found"
                )
            session.commit()
            return ProviderConversationInboxNotification(delivery=refreshed, created=True)

        if delivery.message is None:
            raise RuntimeError("message-backed provider conversation notification lost its durable message")
        notification_row = session.get(db_module.InboxNotificationModel, delivery.notification.id)
        if notification_row is not None:
            session.delete(notification_row)
        durable_message_row = session.get(db_module.InboxMessageModel, delivery.message.id)
        if durable_message_row is not None:
            session.delete(durable_message_row)
        session.flush()
        existing = _get_existing_notification(session, receiver_id, provider_message_id)
        if existing is None:
            raise RuntimeError("provider conversation inbox notification insert conflicted without existing row")
        session.commit()
        return ProviderConversationInboxNotification(delivery=existing, created=False)


def format_provider_conversation_notification(
    *,
    inbox_notification_id: int,
    message_row: db_module.ProviderConversationMessageModel,
    thread_row: db_module.ProviderConversationThreadModel,
    work_item_row: Optional[db_module.ProviderWorkItemModel] = None,
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
    session: Session, receiver_id: str, provider_message_id: int
) -> Optional[InboxDelivery]:
    row = (
        session.query(db_module.ProviderConversationInboxNotificationModel)
        .filter(
            db_module.ProviderConversationInboxNotificationModel.receiver_id == receiver_id,
            db_module.ProviderConversationInboxNotificationModel.provider_message_id == provider_message_id,
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
        f"{row.inbox_notification_id} for provider conversation message {provider_message_id} not found"
    )


def _provider_message_body(
    message_row: db_module.ProviderConversationMessageModel,
    thread_row: db_module.ProviderConversationThreadModel,
) -> str:
    body = _compact(cast(Optional[str], message_row.body))
    if body:
        return body
    return "(no text body)"


def _provider_message_origin(
    message_row: db_module.ProviderConversationMessageModel,
) -> Optional[dict[str, Any]]:
    metadata = _load_json_object(cast(Optional[str], message_row.metadata_json))
    return dict(metadata) if metadata is not None else None


def _format_work_item(row: Optional[db_module.ProviderWorkItemModel]) -> Optional[str]:
    if row is None:
        return None

    parts = [_compact(cast(Optional[str], value)) for value in (row.identifier, row.title) if value]
    if not parts:
        return None
    return f"Issue: {_truncate(' - '.join(parts), 180)}"


def _format_source(
    message_row: db_module.ProviderConversationMessageModel,
    thread_row: db_module.ProviderConversationThreadModel,
) -> str:
    provider = _compact(cast(Optional[str], message_row.provider))
    if provider == "linear" and thread_row.kind == "conversation":
        return "Linear AgentSession"
    return provider or "provider conversation"


def _format_author(row: db_module.ProviderConversationMessageModel) -> Optional[str]:
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
        presentation = value.get(INBOX_READ_PRESENTATION_METADATA_KEY)
        if isinstance(presentation, dict):
            source_label = presentation.get("source_label")
            if isinstance(source_label, str) and source_label.strip():
                return _compact(source_label)
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

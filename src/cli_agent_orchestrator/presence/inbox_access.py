"""CAO inbox read surface for provider-backed presence notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxMessage
from cli_agent_orchestrator.presence.inbox_bridge import PRESENCE_INBOX_SOURCE_KIND


class InboxReadError(ValueError):
    """Base error for CAO inbox read failures."""


class InboxReadNotFoundError(InboxReadError):
    """Raised when the requested inbox message or backing presence data is missing."""


class InboxReadUnsupportedSourceError(InboxReadError):
    """Raised when an inbox message is not backed by readable provider context."""


@dataclass(frozen=True)
class InboxReadResult:
    """Full provider-backed context for one CAO inbox notification."""

    inbox_message: InboxMessage
    thread: Dict[str, Any]
    message: Optional[Dict[str, Any]]
    work_item: Optional[Dict[str, Any]]
    thread_messages: List[Dict[str, Any]]
    replyable: bool
    reply_error: Optional[str] = None


def read_inbox_message(inbox_message_id: int) -> InboxReadResult:
    """Read full durable provider context for a replyable inbox notification."""

    with db_module.SessionLocal() as session:
        inbox_row = (
            session.query(db_module.InboxModel)
            .filter(db_module.InboxModel.id == inbox_message_id)
            .first()
        )
        if inbox_row is None:
            raise InboxReadNotFoundError(f"inbox message {inbox_message_id} not found")
        inbox_message = db_module.inbox_message_from_model(inbox_row)

        if inbox_row.source_kind != PRESENCE_INBOX_SOURCE_KIND:
            raise InboxReadUnsupportedSourceError(
                f"inbox message {inbox_message_id} source_kind "
                f"{inbox_row.source_kind!r} is not readable as provider context"
            )
        if inbox_row.source_id is None:
            raise InboxReadNotFoundError(
                f"inbox message {inbox_message_id} does not include a presence thread source id"
            )
        try:
            thread_id = int(inbox_row.source_id)
        except ValueError as exc:
            raise InboxReadNotFoundError(
                f"inbox message {inbox_message_id} has invalid presence thread source id "
                f"{inbox_row.source_id!r}"
            ) from exc

        thread_row = (
            session.query(db_module.PresenceThreadModel)
            .filter(db_module.PresenceThreadModel.id == thread_id)
            .first()
        )
        if thread_row is None:
            raise InboxReadNotFoundError(
                f"presence thread {thread_id} for inbox message {inbox_message_id} not found"
            )

        marker = (
            session.query(db_module.PresenceInboxNotificationModel)
            .filter(db_module.PresenceInboxNotificationModel.inbox_message_id == inbox_message_id)
            .first()
        )
        message_row = None
        if marker is not None:
            message_row = (
                session.query(db_module.PresenceMessageModel)
                .filter(db_module.PresenceMessageModel.id == marker.presence_message_id)
                .first()
            )
            if message_row is None:
                raise InboxReadNotFoundError(
                    f"presence message {marker.presence_message_id} for inbox message "
                    f"{inbox_message_id} not found"
                )

        work_item = None
        if thread_row.work_item_id is not None:
            work_item_row = (
                session.query(db_module.PresenceWorkItemModel)
                .filter(db_module.PresenceWorkItemModel.id == thread_row.work_item_id)
                .first()
            )
            if work_item_row is not None:
                work_item = _work_item_to_dict(work_item_row)

        thread_messages = (
            session.query(db_module.PresenceMessageModel)
            .filter(db_module.PresenceMessageModel.thread_id == thread_row.id)
            .order_by(
                db_module.PresenceMessageModel.created_at.asc(),
                db_module.PresenceMessageModel.id.asc(),
            )
            .all()
        )

        reply_error = None
        replyable = True
        if not thread_row.provider or not thread_row.external_id:
            replyable = False
            reply_error = "backing provider thread ref is missing"

        return InboxReadResult(
            inbox_message=inbox_message,
            thread=_thread_to_dict(thread_row),
            message=_message_to_dict(message_row) if message_row is not None else None,
            work_item=work_item,
            thread_messages=[_message_to_dict(row) for row in thread_messages],
            replyable=replyable,
            reply_error=reply_error,
        )


def read_result_to_dict(result: InboxReadResult) -> Dict[str, Any]:
    """Convert a read result into a stable MCP-friendly shape."""

    return {
        "success": True,
        "inbox_message": {
            "id": result.inbox_message.id,
            "sender_id": result.inbox_message.sender_id,
            "receiver_id": result.inbox_message.receiver_id,
            "message": result.inbox_message.message,
            "source_kind": result.inbox_message.source_kind,
            "source_id": result.inbox_message.source_id,
            "status": result.inbox_message.status.value,
            "created_at": result.inbox_message.created_at.isoformat(),
        },
        "provider_context": {
            "thread": result.thread,
            "message": result.message,
            "work_item": result.work_item,
            "thread_messages": result.thread_messages,
        },
        "reply": {
            "replyable": result.replyable,
            "error": result.reply_error,
            "tool": "reply_to_inbox_message" if result.replyable else None,
            "inbox_message_id": result.inbox_message.id if result.replyable else None,
        },
    }


def _thread_to_dict(row: db_module.PresenceThreadModel) -> Dict[str, Any]:
    return {
        "id": row.id,
        "provider": row.provider,
        "external_id": row.external_id,
        "external_url": row.external_url,
        "work_item_id": row.work_item_id,
        "kind": row.kind,
        "state": row.state,
        "prompt_context": row.prompt_context,
        "raw_snapshot": _loads_json(row.raw_snapshot_json),
        "metadata": _loads_json(row.metadata_json),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _message_to_dict(row: db_module.PresenceMessageModel) -> Dict[str, Any]:
    return {
        "id": row.id,
        "thread_id": row.thread_id,
        "provider": row.provider,
        "external_id": row.external_id,
        "direction": row.direction,
        "kind": row.kind,
        "body": row.body,
        "state": row.state,
        "raw_snapshot": _loads_json(row.raw_snapshot_json),
        "metadata": _loads_json(row.metadata_json),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _work_item_to_dict(row: db_module.PresenceWorkItemModel) -> Dict[str, Any]:
    return {
        "id": row.id,
        "provider": row.provider,
        "external_id": row.external_id,
        "external_url": row.external_url,
        "identifier": row.identifier,
        "title": row.title,
        "state": row.state,
        "raw_snapshot": _loads_json(row.raw_snapshot_json),
        "metadata": _loads_json(row.metadata_json),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _loads_json(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else None

"""Route terminal inbox replies back to provider-neutral presence threads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from cli_agent_orchestrator.clients.database import get_inbox_message
from cli_agent_orchestrator.models.inbox import InboxMessage
from cli_agent_orchestrator.presence.inbox_bridge import PRESENCE_INBOX_SOURCE_KIND
from cli_agent_orchestrator.presence.manager import (
    PresenceProviderManager,
    presence_provider_manager,
)
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationMessageRecord,
    ConversationThreadRecord,
    ExternalRef,
)
from cli_agent_orchestrator.presence.persistence import (
    get_thread_by_id,
    upsert_message,
)


class PresenceReplyError(ValueError):
    """Base error for inbox-to-presence reply routing failures."""


class PresenceReplyNotFoundError(PresenceReplyError):
    """Raised when an inbox message or presence thread cannot be resolved."""


class PresenceReplyUnsupportedSourceError(PresenceReplyError):
    """Raised when an inbox message is not backed by a presence thread."""


class PresenceReplyDeliveryError(PresenceReplyError):
    """Raised after a provider reply failure has been recorded durably."""

    def __init__(self, message: str, *, failed_message: ConversationMessageRecord) -> None:
        super().__init__(message)
        self.failed_message = failed_message


@dataclass(frozen=True)
class PresenceReplyResult:
    """Durable result of replying to a provider-backed presence thread."""

    inbox_message: InboxMessage
    thread: ConversationThreadRecord
    provider_reply: ConversationMessage
    outbound_message: ConversationMessageRecord


def reply_to_inbox_message(
    inbox_message_id: int,
    body: str,
    *,
    provider_manager: PresenceProviderManager = presence_provider_manager,
    metadata: Optional[Mapping[str, Any]] = None,
) -> PresenceReplyResult:
    """Reply to a presence-thread inbox notification through the provider registry."""

    if not body:
        raise PresenceReplyError("reply body is required")

    inbox_message = get_inbox_message(inbox_message_id)
    if inbox_message is None:
        raise PresenceReplyNotFoundError(f"inbox message {inbox_message_id} not found")

    if inbox_message.source_kind != PRESENCE_INBOX_SOURCE_KIND:
        raise PresenceReplyUnsupportedSourceError(
            f"inbox message {inbox_message_id} source_kind "
            f"{inbox_message.source_kind!r} is not supported for presence replies"
        )

    thread_id = _parse_thread_source_id(inbox_message)
    thread = get_thread_by_id(thread_id)
    if thread is None:
        raise PresenceReplyNotFoundError(
            f"presence thread {thread_id} for inbox message {inbox_message_id} not found"
        )

    thread_ref = ExternalRef(
        provider=thread.provider,
        id=thread.external_id,
        url=thread.external_url,
    )

    try:
        provider_reply = provider_manager.reply_to_thread(
            thread_ref,
            body,
            metadata=_reply_metadata(inbox_message_id, metadata),
        )
    except Exception as exc:
        failed_message = _record_failed_reply(
            thread=thread,
            body=body,
            inbox_message_id=inbox_message_id,
            error=exc,
            metadata=metadata,
        )
        raise PresenceReplyDeliveryError(
            f"provider reply failed for inbox message {inbox_message_id}: {exc}",
            failed_message=failed_message,
        ) from exc

    outbound_message = _record_successful_reply(
        thread=thread,
        body=body,
        inbox_message_id=inbox_message_id,
        provider_reply=provider_reply,
        metadata=metadata,
    )
    return PresenceReplyResult(
        inbox_message=inbox_message,
        thread=thread,
        provider_reply=provider_reply,
        outbound_message=outbound_message,
    )


def _parse_thread_source_id(inbox_message: InboxMessage) -> int:
    if inbox_message.source_id is None:
        raise PresenceReplyNotFoundError(
            f"inbox message {inbox_message.id} does not include a presence thread source id"
        )

    try:
        return int(inbox_message.source_id)
    except ValueError as exc:
        raise PresenceReplyNotFoundError(
            f"inbox message {inbox_message.id} has invalid presence thread source id "
            f"{inbox_message.source_id!r}"
        ) from exc


def _reply_metadata(
    inbox_message_id: int,
    metadata: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    return {
        "inbox_message_id": inbox_message_id,
        **(dict(metadata) if metadata is not None else {}),
    }


def _record_successful_reply(
    *,
    thread: ConversationThreadRecord,
    body: str,
    inbox_message_id: int,
    provider_reply: ConversationMessage,
    metadata: Optional[Mapping[str, Any]],
) -> ConversationMessageRecord:
    reply_ref = provider_reply.ref
    record_metadata: Dict[str, Any] = {
        "inbox_message_id": inbox_message_id,
        "reply_status": "delivered",
    }
    if reply_ref is not None:
        record_metadata["provider_reply_ref"] = {
            "provider": reply_ref.provider,
            "id": reply_ref.id,
            "url": reply_ref.url,
        }
    if metadata is not None:
        record_metadata["metadata"] = dict(metadata)

    return upsert_message(
        thread_id=thread.id,
        provider=thread.provider,
        external_id=reply_ref.id if reply_ref is not None else None,
        direction="outbound",
        kind=provider_reply.kind,
        body=provider_reply.body if provider_reply.body is not None else body,
        state=provider_reply.state,
        metadata=record_metadata,
    )


def _record_failed_reply(
    *,
    thread: ConversationThreadRecord,
    body: str,
    inbox_message_id: int,
    error: Exception,
    metadata: Optional[Mapping[str, Any]],
) -> ConversationMessageRecord:
    record_metadata: Dict[str, Any] = {
        "inbox_message_id": inbox_message_id,
        "reply_status": "failed",
        "error_type": type(error).__name__,
        "error": str(error),
    }
    if metadata is not None:
        record_metadata["metadata"] = dict(metadata)

    return upsert_message(
        thread_id=thread.id,
        provider=thread.provider,
        direction="outbound",
        kind="response",
        body=body,
        state="failed",
        metadata=record_metadata,
    )

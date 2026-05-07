"""Route terminal inbox replies back to provider-neutral presence threads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxDelivery
from cli_agent_orchestrator.presence.inbox_bridge import PRESENCE_INBOX_ROUTE_KIND
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


MAX_PROVIDER_ERROR_CHARS = 240

_STACK_TRACE_RE = re.compile(r"Traceback \(most recent call last\):|\n\s*File \"")
_BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SENSITIVE_QUOTED_VALUE_RE = re.compile(
    r"(?i)\b(access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization|"
    r"api[_-]?key|password|secret|token)\b([\"']?\s*[:=]\s*)([\"']).*?\3"
)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)\b(access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization|"
    r"api[_-]?key|password|secret|token)\b([\"']?\s*[:=]\s*)[^,\s'\"}]+"
)


@dataclass(frozen=True)
class PresenceReplyResult:
    """Durable result of replying to a provider-backed presence thread."""

    delivery: InboxDelivery
    thread: ConversationThreadRecord
    provider_reply: ConversationMessage
    outbound_message: ConversationMessageRecord


def reply_to_inbox_message(
    notification_id: int,
    body: str,
    *,
    provider_manager: PresenceProviderManager = presence_provider_manager,
    metadata: Optional[Mapping[str, Any]] = None,
) -> PresenceReplyResult:
    """Reply to a presence-thread inbox notification through the provider registry."""

    if not body:
        raise PresenceReplyError("reply body is required")

    delivery = _read_delivery(notification_id)
    if delivery is None:
        raise PresenceReplyNotFoundError(f"inbox notification {notification_id} not found")
    message = delivery.message

    if message.route_kind != PRESENCE_INBOX_ROUTE_KIND:
        raise PresenceReplyUnsupportedSourceError(
            f"inbox notification {notification_id} route_kind "
            f"{message.route_kind!r} is not supported for presence replies"
        )

    thread_id = _parse_thread_route_id(delivery)
    thread = get_thread_by_id(thread_id)
    if thread is None:
        raise PresenceReplyNotFoundError(
            f"presence thread {thread_id} for inbox notification {notification_id} not found"
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
            metadata=_reply_metadata(delivery.notification.id, thread=thread, metadata=metadata),
        )
    except Exception as exc:
        safe_error = _safe_provider_error(exc)
        failed_message = _record_failed_reply(
            thread=thread,
            body=body,
            inbox_notification_id=delivery.notification.id,
            error=exc,
            safe_error=safe_error,
            metadata=metadata,
        )
        raise PresenceReplyDeliveryError(
            f"provider reply failed for inbox notification {notification_id}: {safe_error}",
            failed_message=failed_message,
        ) from exc

    outbound_message = _record_successful_reply(
        thread=thread,
        body=body,
        inbox_notification_id=delivery.notification.id,
        provider_reply=provider_reply,
        metadata=metadata,
    )
    return PresenceReplyResult(
        delivery=delivery,
        thread=thread,
        provider_reply=provider_reply,
        outbound_message=outbound_message,
    )


def _read_delivery(notification_id: int) -> Optional[InboxDelivery]:
    return db_module.get_inbox_delivery(notification_id)


def _parse_thread_route_id(delivery: InboxDelivery) -> int:
    message = delivery.message
    if message.route_id is None:
        raise PresenceReplyNotFoundError(
            f"inbox notification {delivery.notification.id} does not include a presence thread route id"
        )

    try:
        return int(message.route_id)
    except ValueError as exc:
        raise PresenceReplyNotFoundError(
            f"inbox notification {delivery.notification.id} has invalid presence thread route id "
            f"{message.route_id!r}"
        ) from exc


def _reply_metadata(
    inbox_notification_id: int,
    *,
    thread: ConversationThreadRecord,
    metadata: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "inbox_notification_id": inbox_notification_id,
    }
    if thread.metadata is not None:
        result["thread_metadata"] = thread.metadata
    if thread.raw_snapshot is not None:
        result["thread_raw_snapshot"] = thread.raw_snapshot
    if metadata is not None:
        result.update(dict(metadata))
    return result


def _record_successful_reply(
    *,
    thread: ConversationThreadRecord,
    body: str,
    inbox_notification_id: int,
    provider_reply: ConversationMessage,
    metadata: Optional[Mapping[str, Any]],
) -> ConversationMessageRecord:
    reply_ref = provider_reply.ref
    record_metadata: Dict[str, Any] = {
        "inbox_notification_id": inbox_notification_id,
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
    inbox_notification_id: int,
    error: Exception,
    safe_error: str,
    metadata: Optional[Mapping[str, Any]],
) -> ConversationMessageRecord:
    record_metadata: Dict[str, Any] = {
        "inbox_notification_id": inbox_notification_id,
        "reply_status": "failed",
        "error_type": type(error).__name__,
        "error": safe_error,
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


def _safe_provider_error(error: Exception) -> str:
    """Return a concise provider-error summary safe for agent-facing failures."""

    raw_message = str(error) or type(error).__name__
    message = _STACK_TRACE_RE.split(raw_message, maxsplit=1)[0].strip()
    if not message:
        message = type(error).__name__
    message = _BEARER_TOKEN_RE.sub("Bearer [redacted]", message)
    message = _SENSITIVE_QUOTED_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[redacted]{match.group(3)}",
        message,
    )
    message = _SENSITIVE_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[redacted]",
        message,
    )
    message = " ".join(message.split())
    if len(message) <= MAX_PROVIDER_ERROR_CHARS:
        return message
    suffix = "..."
    return message[: MAX_PROVIDER_ERROR_CHARS - len(suffix)].rstrip() + suffix

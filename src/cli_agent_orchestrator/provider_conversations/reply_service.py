"""Route terminal inbox replies back to provider-backed conversation threads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxDelivery, InboxNotificationTarget
from cli_agent_orchestrator.provider_conversations.inbox_bridge import (
    PROVIDER_CONVERSATION_INBOX_ROUTE_KIND,
)
from cli_agent_orchestrator.provider_conversations.models import (
    ConversationMessage,
    ConversationMessageRecord,
    ConversationThreadRecord,
    ExternalRef,
)
from cli_agent_orchestrator.provider_conversations.persistence import (
    get_thread_by_id,
    upsert_message,
)


class ProviderConversationReplyError(ValueError):
    """Base error for provider-conversation reply routing failures."""


class ProviderConversationReplyNotFoundError(ProviderConversationReplyError):
    """Raised when an inbox message or provider conversation thread cannot be resolved."""


class ProviderConversationReplyUnsupportedSourceError(ProviderConversationReplyError):
    """Raised when an inbox message is not backed by a provider conversation thread."""


class ProviderConversationReplyDeliveryError(ProviderConversationReplyError):
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
class ProviderConversationReplyResult:
    """Durable result of replying to a provider-backed provider conversation thread."""

    delivery: InboxDelivery
    thread: ConversationThreadRecord
    provider_reply: ConversationMessage
    outbound_message: ConversationMessageRecord


def reply_to_inbox_message(
    notification_id: int,
    body: str,
    *,
    metadata: Optional[Mapping[str, Any]] = None,
) -> ProviderConversationReplyResult:
    """Reply to a provider-thread inbox notification."""

    if not body:
        raise ProviderConversationReplyError("reply body is required")

    delivery = _read_delivery(notification_id)
    if delivery is None:
        raise ProviderConversationReplyNotFoundError(
            f"inbox notification {notification_id} not found"
        )
    message_target = _primary_inbox_message_target(delivery)
    if message_target is None:
        raise ProviderConversationReplyUnsupportedSourceError(
            f"inbox notification {notification_id} has no CAO message target"
        )
    message = delivery.message
    if message is None:
        raise ProviderConversationReplyNotFoundError(
            f"inbox message target {message_target.target_id} for inbox notification "
            f"{notification_id} not found"
        )

    if message.route_kind != PROVIDER_CONVERSATION_INBOX_ROUTE_KIND:
        raise ProviderConversationReplyUnsupportedSourceError(
            f"inbox notification {notification_id} route_kind "
            f"{message.route_kind!r} is not supported for provider conversation replies"
        )

    thread_id = _parse_thread_route_id(delivery)
    thread = get_thread_by_id(thread_id)
    if thread is None:
        raise ProviderConversationReplyNotFoundError(
            f"provider conversation thread {thread_id} for inbox notification {notification_id} not found"
        )

    try:
        provider_reply = _send_provider_thread_reply(
            thread,
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
        raise ProviderConversationReplyDeliveryError(
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
    return ProviderConversationReplyResult(
        delivery=delivery,
        thread=thread,
        provider_reply=provider_reply,
        outbound_message=outbound_message,
    )


def _send_provider_thread_reply(
    thread: ConversationThreadRecord,
    body: str,
    *,
    metadata: Mapping[str, Any],
) -> ConversationMessage:
    if thread.provider == "linear":
        return _send_linear_thread_reply(thread, body, metadata=metadata)
    raise ProviderConversationReplyUnsupportedSourceError(
        f"provider {thread.provider!r} is not supported for inbox replies"
    )


def _send_linear_thread_reply(
    thread: ConversationThreadRecord,
    body: str,
    *,
    metadata: Mapping[str, Any],
) -> ConversationMessage:
    from cli_agent_orchestrator.linear import app_client

    content = {"type": "response", "body": body}
    activity = app_client.create_agent_activity(
        thread.external_id,
        content,
        app_key=_linear_app_key_from_reply_metadata(metadata),
    )
    activity_id = _string_value(activity.get("id")) if isinstance(activity, Mapping) else None
    return ConversationMessage(
        kind="response",
        body=body,
        ref=ExternalRef(provider="linear", id=activity_id) if activity_id else None,
        direction="outbound",
        state="delivered",
    )


def _linear_app_key_from_reply_metadata(metadata: Mapping[str, Any]) -> Optional[str]:
    for key in ("_cao_linear_app_key", "app_key", "linear_app_key"):
        value = metadata.get(key)
        if value:
            return str(value)
    for key in ("thread_metadata", "thread_raw_snapshot", "raw_snapshot"):
        found = _linear_app_key_from_nested(metadata.get(key))
        if found:
            return found
    return None


def _linear_app_key_from_nested(value: Any) -> Optional[str]:
    if isinstance(value, Mapping):
        direct = (
            value.get("_cao_linear_app_key")
            or value.get("linear_app_key")
            or value.get("app_key")
            or value.get("appKey")
        )
        if direct:
            return str(direct)
        data = value.get("data")
        if isinstance(data, Mapping):
            found = _linear_app_key_from_nested(data)
            if found:
                return found
        for item in value.values():
            found = _linear_app_key_from_nested(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _linear_app_key_from_nested(item)
            if found:
                return found
    return None


def _string_value(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)


def _read_delivery(notification_id: int) -> Optional[InboxDelivery]:
    return db_module.get_inbox_delivery(notification_id)


def _primary_inbox_message_target(delivery: InboxDelivery) -> Optional[InboxNotificationTarget]:
    for target in delivery.targets:
        if (
            target.target_kind == db_module.INBOX_NOTIFICATION_TARGET_KIND_INBOX_MESSAGE
            and target.role == db_module.INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY
        ):
            return target
    return None


def _parse_thread_route_id(delivery: InboxDelivery) -> int:
    message = delivery.message
    if message is None:
        raise ProviderConversationReplyUnsupportedSourceError(
            f"inbox notification {delivery.notification.id} is not backed by a CAO message"
        )
    if message.route_id is None:
        raise ProviderConversationReplyNotFoundError(
            f"inbox notification {delivery.notification.id} does not include a provider conversation thread route id"
        )

    try:
        return int(message.route_id)
    except ValueError as exc:
        raise ProviderConversationReplyNotFoundError(
            f"inbox notification {delivery.notification.id} has invalid provider conversation thread route id "
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

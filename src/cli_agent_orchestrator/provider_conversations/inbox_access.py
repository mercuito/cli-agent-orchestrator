"""CAO inbox read surface for terminal and provider-backed notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, cast

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxDelivery, InboxNotificationTarget
from cli_agent_orchestrator.provider_conversations.inbox_bridge import (
    PROVIDER_CONVERSATION_INBOX_ROUTE_KIND,
)
from cli_agent_orchestrator.provider_conversations.inbox_authorization import (
    require_provider_inbox_authorization,
    require_inbox_notification_receiver,
)
from cli_agent_orchestrator.provider_conversations.inbox_read_presentation import (
    INBOX_READ_PRESENTATION_METADATA_KEY,
)


class InboxReadError(ValueError):
    """Base error for CAO inbox read failures."""


class InboxReadNotFoundError(InboxReadError):
    """Raised when the requested inbox notification or backing provider data is missing."""


class InboxReadUnsupportedNotificationError(InboxReadError):
    """Raised when a valid inbox notification has no CAO-readable backing message."""


@dataclass(frozen=True)
class InboxReadResult:
    """Message-first read result for one CAO inbox notification."""

    delivery: InboxDelivery
    from_label: str
    body: str
    replyable: bool
    workspace: Optional[Dict[str, Any]] = None
    reply_error: Optional[str] = None
    thread: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


MAX_WORKSPACE_JSON_CHARS = 1000
MAX_METADATA_JSON_CHARS = 4000
MAX_CONTEXT_JSON_CHARS = 4000
MAX_CONTEXT_VALUE_CHARS = 3500


def read_inbox_message(
    notification_id: int,
    *,
    caller_terminal_id: Optional[str] = None,
) -> InboxReadResult:
    """Read one CAO inbox notification through the slim shared inbox surface."""

    with db_module.SessionLocal() as session:
        delivery = _read_delivery(session, notification_id)
        if delivery is None:
            raise InboxReadNotFoundError(f"inbox notification {notification_id} not found")
        message_target = _primary_inbox_message_target(delivery)
        if message_target is None:
            raise InboxReadUnsupportedNotificationError(
                f"inbox notification {notification_id} has no CAO message target"
            )
        message = delivery.message
        if message is None:
            raise InboxReadNotFoundError(
                f"inbox message target {message_target.target_id} for inbox notification "
                f"{notification_id} not found"
            )

        require_inbox_notification_receiver(
            delivery,
            caller_terminal_id=caller_terminal_id,
            error=InboxReadError,
        )

        if message.route_kind != PROVIDER_CONVERSATION_INBOX_ROUTE_KIND:
            return InboxReadResult(
                delivery=delivery,
                from_label=_plain_source_label(session, delivery),
                body=message.body,
                replyable=False,
                reply_error="no provider reply route",
                workspace=None,
            )

        if message.route_id is None:
            raise InboxReadNotFoundError(
                f"inbox notification {notification_id} does not include a provider conversation thread route id"
            )
        try:
            thread_id = int(message.route_id)
        except ValueError as exc:
            raise InboxReadNotFoundError(
                f"inbox notification {notification_id} has invalid provider conversation thread route id "
                f"{message.route_id!r}"
            ) from exc

        thread_row = (
            session.query(db_module.ProviderConversationThreadModel)
            .filter(db_module.ProviderConversationThreadModel.id == thread_id)
            .first()
        )
        if thread_row is None:
            raise InboxReadNotFoundError(
                f"provider conversation thread {thread_id} for inbox notification {notification_id} not found"
            )

        message_row = _selected_provider_message_row(
            session,
            inbox_notification_id=delivery.notification.id,
        )
        message_metadata = _message_metadata(message_row)
        origin = message.origin if isinstance(message.origin, Mapping) else None
        require_provider_inbox_authorization(
            delivery,
            caller_terminal_id=caller_terminal_id,
            provider=thread_row.provider,
            thread_metadata=_thread_metadata(thread_row),
            thread_raw_snapshot=_thread_raw_snapshot(thread_row),
            message_metadata=message_metadata,
            message_raw_snapshot=_message_raw_snapshot(message_row),
            error=InboxReadError,
        )

        reply_error = None
        replyable = True
        if not thread_row.provider or not thread_row.external_id:
            replyable = False
            reply_error = "backing provider thread ref is missing"

        return InboxReadResult(
            delivery=delivery,
            from_label=_provider_conversation_source_label(
                origin, message_metadata, message_row, thread_row
            ),
            body=_provider_conversation_body(message_row, thread_row),
            replyable=replyable,
            reply_error=reply_error,
            workspace=_provider_conversation_workspace(origin)
            or _provider_conversation_workspace(message_metadata),
            thread={"provider": cast(Optional[str], thread_row.provider)},
            context=_provider_conversation_context(origin)
            or _provider_conversation_context(message_metadata),
        )


def read_result_to_dict(result: InboxReadResult) -> Dict[str, Any]:
    """Convert a read result into the slim default MCP shape."""
    breadcrumb = _workspace_breadcrumb(result.workspace)

    payload: Dict[str, Any] = {
        "success": True,
        "notification_id": result.delivery.notification.id,
        "message_id": result.delivery.message.id if result.delivery.message is not None else None,
        "from": result.from_label,
        "body": result.body,
        "replyable": result.replyable,
    }
    if breadcrumb is not None:
        payload["breadcrumb"] = breadcrumb
    if result.reply_error:
        payload["reply_error"] = result.reply_error
    return payload


def _read_delivery(session: Any, notification_id: int) -> Optional[InboxDelivery]:
    return db_module.get_inbox_delivery(notification_id, db=session)


def _primary_inbox_message_target(delivery: InboxDelivery) -> Optional[InboxNotificationTarget]:
    for target in delivery.targets:
        if (
            target.target_kind == db_module.INBOX_NOTIFICATION_TARGET_KIND_INBOX_MESSAGE
            and target.role == db_module.INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY
        ):
            return target
    return None


def _selected_provider_message_row(
    session: Any,
    *,
    inbox_notification_id: int,
) -> Optional[db_module.ProviderConversationMessageModel]:
    marker = (
        session.query(db_module.ProviderConversationInboxNotificationModel)
        .filter(
            db_module.ProviderConversationInboxNotificationModel.inbox_notification_id
            == inbox_notification_id
        )
        .first()
    )
    if marker is not None:
        message_row = (
            session.query(db_module.ProviderConversationMessageModel)
            .filter(db_module.ProviderConversationMessageModel.id == marker.provider_message_id)
            .first()
        )
        if message_row is None:
            raise InboxReadNotFoundError(
                f"provider conversation message {marker.provider_message_id} for inbox notification "
                f"{inbox_notification_id} not found"
            )
        return cast(Optional[db_module.ProviderConversationMessageModel], message_row)

    raise InboxReadNotFoundError(
        f"provider conversation notification marker for inbox notification {inbox_notification_id} not found"
    )


def _message_metadata(
    message_row: Optional[db_module.ProviderConversationMessageModel],
) -> Optional[Dict[str, Any]]:
    if message_row is None:
        return None
    return _load_bounded_json_object(cast(Optional[str], message_row.metadata_json))


def _message_raw_snapshot(
    message_row: Optional[db_module.ProviderConversationMessageModel],
) -> Optional[Dict[str, Any]]:
    if message_row is None:
        return None
    return _load_bounded_json_object(cast(Optional[str], message_row.raw_snapshot_json))


def _thread_metadata(
    thread_row: db_module.ProviderConversationThreadModel,
) -> Optional[Dict[str, Any]]:
    return _load_bounded_json_object(cast(Optional[str], thread_row.metadata_json))


def _thread_raw_snapshot(
    thread_row: db_module.ProviderConversationThreadModel,
) -> Optional[Dict[str, Any]]:
    return _load_bounded_json_object(cast(Optional[str], thread_row.raw_snapshot_json))


def _provider_conversation_workspace(
    metadata: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    presentation = _presentation(metadata)
    if presentation is None:
        return None
    workspace = presentation.get("workspace")
    return _bounded_workspace(workspace) if isinstance(workspace, Mapping) else None


def _bounded_workspace(value: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    breadcrumb = value.get("breadcrumb")
    if not value.get("name") or not isinstance(breadcrumb, Mapping):
        return None

    workspace = {
        "name": _bounded_label(str(value["name"]), max_chars=80),
        "breadcrumb": dict(breadcrumb),
    }
    try:
        encoded = json.dumps(workspace, sort_keys=True)
    except (TypeError, ValueError):
        return None
    if len(encoded) > MAX_WORKSPACE_JSON_CHARS:
        return None
    return cast(Dict[str, Any], json.loads(encoded))


def _workspace_breadcrumb(workspace: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not workspace:
        return None
    breadcrumb = workspace.get("breadcrumb")
    if not isinstance(breadcrumb, Mapping):
        return None
    result: Dict[str, Any] = {}
    workspace_name = workspace.get("name")
    if isinstance(workspace_name, str) and workspace_name.strip():
        result["workspace"] = workspace_name
    result.update(dict(breadcrumb))
    return result or None


def _load_bounded_json_object(metadata_json: Optional[str]) -> Optional[Dict[str, Any]]:
    if not metadata_json or len(metadata_json) > MAX_METADATA_JSON_CHARS:
        return None
    try:
        metadata = json.loads(metadata_json)
    except Exception:
        return None
    return metadata if isinstance(metadata, dict) else None


def _plain_source_label(session: Any, delivery: InboxDelivery) -> str:
    message = delivery.message
    if message is None:
        if delivery.notification.source_kind:
            return _display_from_token(str(delivery.notification.source_kind))
        return "Inbox sender"
    terminal = (
        session.query(db_module.TerminalModel)
        .filter(db_module.TerminalModel.id == message.sender_id)
        .first()
    )
    if terminal is not None and terminal.agent_id:
        return _display_from_token(cast(str, terminal.agent_id))

    sender_id = str(cast(str, message.sender_id) or "")
    if sender_id.startswith("agent:"):
        return _display_from_token(sender_id.split(":", 1)[1])

    if message.source_kind and message.source_kind != "terminal":
        return _display_from_token(str(message.source_kind))
    if message.source_kind == "terminal":
        return "Terminal sender"
    return "Inbox sender"


def _provider_conversation_source_label(
    origin: Optional[Mapping[str, Any]],
    metadata: Optional[Mapping[str, Any]],
    message_row: Optional[db_module.ProviderConversationMessageModel],
    thread_row: db_module.ProviderConversationThreadModel,
) -> str:
    presentation = _presentation(origin) or _presentation(metadata)
    if presentation is not None:
        label = presentation.get("source_label")
        if label:
            return _bounded_label(str(label))

    if message_row is not None:
        return _provider_label(cast(Optional[str], message_row.provider))
    return _provider_label(cast(Optional[str], thread_row.provider))


def _provider_conversation_body(
    message_row: Optional[db_module.ProviderConversationMessageModel],
    thread_row: db_module.ProviderConversationThreadModel,
) -> str:
    if message_row is not None and message_row.body:
        return str(cast(Optional[str], message_row.body))
    return "(no text body)"


def _provider_conversation_context(
    metadata: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    presentation = _presentation(metadata)
    if presentation is None:
        return None
    context = presentation.get("context")
    return _bounded_context(context) if isinstance(context, Mapping) else None


def _bounded_context(value: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    context: Dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        if isinstance(item, str):
            context[key] = _truncate_text(item, max_chars=MAX_CONTEXT_VALUE_CHARS)
        elif item is None or isinstance(item, (int, float, bool)):
            context[key] = item
        else:
            return None
    try:
        encoded = json.dumps(context, sort_keys=True)
    except (TypeError, ValueError):
        return None
    if len(encoded) > MAX_CONTEXT_JSON_CHARS:
        return None
    return context


def _provider_label(provider: Optional[str]) -> str:
    if provider:
        return _display_from_token(provider)
    return "Provider conversation"


def _display_from_token(value: str) -> str:
    label = value.replace("_", " ").replace("-", " ").replace(":", " ").strip()
    return _bounded_label(label.title() if label else "Inbox sender")


def _presentation(metadata: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    if metadata is None:
        return None
    presentation = metadata.get(INBOX_READ_PRESENTATION_METADATA_KEY)
    return presentation if isinstance(presentation, Mapping) else None


def _bounded_label(value: str, max_chars: int = 120) -> str:
    label = " ".join(value.split())
    if len(label) <= max_chars:
        return label
    suffix = "..."
    return label[: max(0, max_chars - len(suffix))].rstrip() + suffix


def _truncate_text(value: str, *, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    suffix = "..."
    return value[: max(0, max_chars - len(suffix))].rstrip() + suffix

"""Linear-owned inbox read context helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, cast

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.inbox import InboxReadError, InboxReadNotFoundError
from cli_agent_orchestrator.linear.inbox_authorization import (
    provider_inbox_authorization_decision,
    require_provider_inbox_authorization,
)
from cli_agent_orchestrator.linear.inbox_read_presentation import (
    INBOX_READ_PRESENTATION_METADATA_KEY,
)


@dataclass(frozen=True)
class MessageContext:
    """Linear-specific context attached to an MCP inbox read response."""

    from_label: str
    body: str
    can_reply: bool
    breadcrumb: Optional[Dict[str, Any]] = None
    reply_error: Optional[str] = None


MAX_WORKSPACE_JSON_CHARS = 1000
MAX_METADATA_JSON_CHARS = 4000


def get_message_context(
    source_id: str,
    *,
    notification_id: int,
    caller_terminal_id: str,
) -> MessageContext:
    """Return Linear breadcrumb and work-item context for one provider inbox source."""

    with db_module.SessionLocal() as session:
        delivery = db_module.get_inbox_delivery(notification_id, db=session)
        if delivery is None:
            raise InboxReadNotFoundError(f"inbox notification {notification_id} not found")

        try:
            provider_message_id = int(source_id)
        except ValueError as exc:
            raise InboxReadNotFoundError(
                f"inbox notification {notification_id} has invalid provider conversation message id "
                f"{source_id!r}"
            ) from exc

        message_row = _selected_provider_message_row(
            session,
            provider_message_id=provider_message_id,
            inbox_notification_id=delivery.notification.id,
        )
        thread_id = cast(int, message_row.thread_id)
        thread_row = (
            session.query(db_module.ProviderConversationThreadModel)
            .filter(db_module.ProviderConversationThreadModel.id == thread_id)
            .first()
        )
        if thread_row is None:
            raise InboxReadNotFoundError(
                f"provider conversation thread {thread_id} for inbox notification {notification_id} not found"
            )

        message_metadata = _message_metadata(message_row)
        origin = (
            delivery.notification.metadata
            if isinstance(delivery.notification.metadata, Mapping)
            else None
        )
        require_provider_inbox_authorization(
            delivery,
            caller_terminal_id=caller_terminal_id,
            provider=cast(str, thread_row.provider),
            operation="read",
            thread_metadata=_thread_metadata(thread_row),
            thread_raw_snapshot=_thread_raw_snapshot(thread_row),
            message_metadata=message_metadata,
            message_raw_snapshot=_message_raw_snapshot(message_row),
            error=InboxReadError,
        )

        reply_error = None
        can_reply = True
        if not thread_row.provider or not thread_row.external_id:
            can_reply = False
            reply_error = "backing provider thread ref is missing"
        else:
            reply_decision = provider_inbox_authorization_decision(
                delivery,
                caller_terminal_id=caller_terminal_id,
                provider=cast(str, thread_row.provider),
                operation="reply",
                thread_metadata=_thread_metadata(thread_row),
                thread_raw_snapshot=_thread_raw_snapshot(thread_row),
                message_metadata=message_metadata,
                message_raw_snapshot=_message_raw_snapshot(message_row),
                error=InboxReadError,
            )
            if not reply_decision.allowed:
                can_reply = False
                reply_error = (
                    "reply_to_inbox_message is not authorized by ToolService: "
                    f"{reply_decision.reason}"
                )

        workspace = _provider_conversation_workspace(origin) or _provider_conversation_workspace(
            message_metadata
        )
        return MessageContext(
            from_label=_provider_conversation_source_label(
                origin, message_metadata, message_row, thread_row
            ),
            body=_provider_conversation_body(message_row, thread_row),
            can_reply=can_reply,
            reply_error=reply_error,
            breadcrumb=_workspace_breadcrumb(workspace),
        )


def _selected_provider_message_row(
    session: Any,
    *,
    provider_message_id: int,
    inbox_notification_id: int,
) -> db_module.ProviderConversationMessageModel:
    message_row = (
        session.query(db_module.ProviderConversationMessageModel)
        .filter(db_module.ProviderConversationMessageModel.id == provider_message_id)
        .first()
    )
    if message_row is None:
        raise InboxReadNotFoundError(
            f"provider conversation message {provider_message_id} for inbox notification "
            f"{inbox_notification_id} not found"
        )
    return cast(db_module.ProviderConversationMessageModel, message_row)


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

"""CAO inbox read surface for terminal and provider-backed notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, cast

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxDelivery
from cli_agent_orchestrator.presence.inbox_bridge import PRESENCE_INBOX_ROUTE_KIND
from cli_agent_orchestrator.presence.inbox_presentation import (
    INBOX_PRESENTATION_METADATA_KEY,
)


class InboxReadError(ValueError):
    """Base error for CAO inbox read failures."""


class InboxReadNotFoundError(InboxReadError):
    """Raised when the requested inbox message or backing presence data is missing."""


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


MAX_WORKSPACE_JSON_CHARS = 1000
MAX_METADATA_JSON_CHARS = 4000


def read_inbox_message(inbox_message_id: int) -> InboxReadResult:
    """Read one CAO inbox notification through the slim shared inbox surface."""

    with db_module.SessionLocal() as session:
        delivery = _read_delivery(session, inbox_message_id)
        if delivery is None:
            raise InboxReadNotFoundError(f"inbox notification {inbox_message_id} not found")
        message = delivery.message

        if message.route_kind != PRESENCE_INBOX_ROUTE_KIND:
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
                f"inbox notification {inbox_message_id} does not include a presence thread route id"
            )
        try:
            thread_id = int(message.route_id)
        except ValueError as exc:
            raise InboxReadNotFoundError(
                f"inbox notification {inbox_message_id} has invalid presence thread route id "
                f"{message.route_id!r}"
            ) from exc

        thread_row = (
            session.query(db_module.PresenceThreadModel)
            .filter(db_module.PresenceThreadModel.id == thread_id)
            .first()
        )
        if thread_row is None:
            raise InboxReadNotFoundError(
                f"presence thread {thread_id} for inbox notification {inbox_message_id} not found"
            )

        message_row = _selected_presence_message_row(
            session,
            inbox_notification_id=delivery.notification.id,
        )
        message_metadata = _message_metadata(message_row)
        origin = message.origin if isinstance(message.origin, Mapping) else None

        reply_error = None
        replyable = True
        if not thread_row.provider or not thread_row.external_id:
            replyable = False
            reply_error = "backing provider thread ref is missing"

        return InboxReadResult(
            delivery=delivery,
            from_label=_presence_source_label(origin, message_metadata, message_row, thread_row),
            body=_presence_body(message_row, thread_row),
            replyable=replyable,
            reply_error=reply_error,
            workspace=_presence_workspace(origin) or _presence_workspace(message_metadata),
            thread={"provider": cast(Optional[str], thread_row.provider)},
        )


def read_result_to_dict(result: InboxReadResult) -> Dict[str, Any]:
    """Convert a read result into the slim default MCP shape."""

    payload: Dict[str, Any] = {
        "success": True,
        "id": result.delivery.notification.id,
        "from": result.from_label,
        "body": result.body,
        "replyable": result.replyable,
        "workspace": result.workspace,
    }
    if result.reply_error:
        payload["reply_error"] = result.reply_error
    return payload


def _read_delivery(session: Any, inbox_message_id: int) -> Optional[InboxDelivery]:
    delivery = db_module.get_inbox_delivery(inbox_message_id, db=session)
    if delivery is not None:
        return delivery
    return db_module.get_inbox_delivery_for_legacy_message(inbox_message_id, db=session)


def _selected_presence_message_row(
    session: Any,
    *,
    inbox_notification_id: int,
) -> Optional[db_module.PresenceMessageModel]:
    marker = (
        session.query(db_module.PresenceInboxNotificationModel)
        .filter(
            db_module.PresenceInboxNotificationModel.inbox_notification_id == inbox_notification_id
        )
        .first()
    )
    if marker is not None:
        message_row = (
            session.query(db_module.PresenceMessageModel)
            .filter(db_module.PresenceMessageModel.id == marker.presence_message_id)
            .first()
        )
        if message_row is None:
            raise InboxReadNotFoundError(
                f"presence message {marker.presence_message_id} for inbox notification "
                f"{inbox_notification_id} not found"
            )
        return cast(Optional[db_module.PresenceMessageModel], message_row)

    legacy_marker = (
        session.query(db_module.PresenceInboxNotificationModel)
        .join(
            db_module.InboxNotificationModel,
            db_module.PresenceInboxNotificationModel.inbox_message_id
            == db_module.InboxNotificationModel.legacy_inbox_id,
        )
        .filter(db_module.InboxNotificationModel.id == inbox_notification_id)
        .first()
    )
    if legacy_marker is not None:
        message_row = (
            session.query(db_module.PresenceMessageModel)
            .filter(db_module.PresenceMessageModel.id == legacy_marker.presence_message_id)
            .first()
        )
        if message_row is None:
            raise InboxReadNotFoundError(
                f"presence message {legacy_marker.presence_message_id} for inbox notification "
                f"{inbox_notification_id} not found"
            )
        return cast(Optional[db_module.PresenceMessageModel], message_row)

    raise InboxReadNotFoundError(
        f"presence notification marker for inbox notification {inbox_notification_id} not found"
    )


def _message_metadata(
    message_row: Optional[db_module.PresenceMessageModel],
) -> Optional[Dict[str, Any]]:
    if message_row is None:
        return None
    return _load_bounded_json_object(cast(Optional[str], message_row.metadata_json))


def _presence_workspace(metadata: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
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
    terminal = (
        session.query(db_module.TerminalModel)
        .filter(db_module.TerminalModel.id == message.sender_id)
        .first()
    )
    if terminal is not None and terminal.agent_profile:
        return _display_from_token(cast(str, terminal.agent_profile))

    sender_id = str(cast(str, message.sender_id) or "")
    if sender_id.startswith("agent:"):
        return _display_from_token(sender_id.split(":", 1)[1])

    if message.source_kind and message.source_kind != "terminal":
        return _display_from_token(str(message.source_kind))
    if message.source_kind == "terminal":
        return "Terminal sender"
    return "Inbox sender"


def _presence_source_label(
    origin: Optional[Mapping[str, Any]],
    metadata: Optional[Mapping[str, Any]],
    message_row: Optional[db_module.PresenceMessageModel],
    thread_row: db_module.PresenceThreadModel,
) -> str:
    presentation = _presentation(origin) or _presentation(metadata)
    if presentation is not None:
        label = presentation.get("source_label")
        if label:
            return _bounded_label(str(label))

    if message_row is not None:
        return _provider_label(cast(Optional[str], message_row.provider))
    return _provider_label(cast(Optional[str], thread_row.provider))


def _presence_body(
    message_row: Optional[db_module.PresenceMessageModel],
    thread_row: db_module.PresenceThreadModel,
) -> str:
    if message_row is not None and message_row.body is not None:
        return str(cast(Optional[str], message_row.body))
    return str(cast(Optional[str], thread_row.prompt_context) or "")


def _provider_label(provider: Optional[str]) -> str:
    if provider:
        return _display_from_token(provider)
    return "Provider presence"


def _display_from_token(value: str) -> str:
    label = value.replace("_", " ").replace("-", " ").replace(":", " ").strip()
    return _bounded_label(label.title() if label else "Inbox sender")


def _presentation(metadata: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    if metadata is None:
        return None
    presentation = metadata.get(INBOX_PRESENTATION_METADATA_KEY)
    return presentation if isinstance(presentation, Mapping) else None


def _bounded_label(value: str, max_chars: int = 120) -> str:
    label = " ".join(value.split())
    if len(label) <= max_chars:
        return label
    suffix = "..."
    return label[: max(0, max_chars - len(suffix))].rstrip() + suffix

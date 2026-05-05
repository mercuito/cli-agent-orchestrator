"""Translate Linear payloads into provider-neutral presence models."""

from __future__ import annotations

from typing import Any, Dict, Optional

from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    MessageKind,
    PresenceEvent,
    WorkItem,
)

PROVIDER = "linear"


def _string_value(value: Any) -> Optional[str]:
    return str(value) if value else None


def _work_item_from_issue(issue: Dict[str, Any]) -> Optional[WorkItem]:
    issue_id = _string_value(issue.get("id"))
    if not issue_id:
        return None

    return WorkItem(
        ref=ExternalRef(
            provider=PROVIDER,
            id=issue_id,
            url=_string_value(issue.get("url")),
        ),
        identifier=_string_value(issue.get("identifier")),
        title=_string_value(issue.get("title")),
    )


def _message_kind(activity: Dict[str, Any]) -> MessageKind:
    content = activity.get("content") if isinstance(activity.get("content"), dict) else {}
    value = _string_value(activity.get("type") or content.get("type"))
    if value in {"prompt", "thought", "response", "elicitation", "error", "stop"}:
        return value
    if _string_value(activity.get("signal") or content.get("signal")) == "stop":
        return "stop"
    return "unknown"


def _conversation_message(payload: Dict[str, Any]) -> Optional[ConversationMessage]:
    activity = app_client.agent_activity_from_payload(payload)
    if not activity:
        return None

    content = activity.get("content") if isinstance(activity.get("content"), dict) else {}
    body = _string_value(activity.get("body") or content.get("body"))
    activity_id = _string_value(activity.get("id"))

    return ConversationMessage(
        kind=_message_kind(activity),
        body=body,
        ref=ExternalRef(provider=PROVIDER, id=activity_id) if activity_id else None,
    )


def presence_event_from_agent_session_payload(
    payload: Dict[str, Any],
    *,
    header_event: Optional[str] = None,
    delivery_id: Optional[str] = None,
) -> Optional[PresenceEvent]:
    """Translate a Linear AgentSessionEvent payload into a CAO presence event."""
    if not app_client.is_agent_session_event(payload, header_event):
        return None

    agent_session = app_client.agent_session_from_payload(payload)
    agent_session_id = app_client.agent_session_id_from_payload(payload)
    thread = None
    if agent_session_id:
        issue = agent_session.get("issue")
        thread = ConversationThread(
            ref=ExternalRef(
                provider=PROVIDER,
                id=agent_session_id,
                url=_string_value(agent_session.get("url")),
            ),
            work_item=_work_item_from_issue(issue) if isinstance(issue, dict) else None,
            prompt_context=app_client.prompt_context_from_payload(payload),
        )

    event_type = app_client.webhook_event_type(payload, header_event) or "AgentSessionEvent"
    action = _string_value(payload.get("action"))
    return PresenceEvent(
        provider=PROVIDER,
        event_type=event_type,
        action=action,
        thread=thread,
        message=_conversation_message(payload),
        delivery_id=delivery_id,
        raw_payload=payload,
    )


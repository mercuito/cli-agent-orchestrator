"""Linear PresenceProvider adapter."""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, cast

from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    MessageKind,
    PresenceEvent,
    StopAcknowledgement,
    WorkItem,
)
from cli_agent_orchestrator.presence.inbox_read_presentation import inbox_read_presentation_metadata
from cli_agent_orchestrator.presence.refs import ProviderRefFactory

PROVIDER = "linear"
LINEAR_REFS = ProviderRefFactory(PROVIDER)
HEADER_EVENT_PAYLOAD_KEY = "_linear_header_event"
STOP_ACK_BODY = "CAO received the stop request."
LINEAR_INBOX_CONTEXT_CHARS = 3500
CONTEXT_ONLY_MESSAGE_BODY = "Linear started an AgentSession with prompt context."


def _string_value(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)


def _dict_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def payload_with_header_event(
    payload: Mapping[str, Any],
    *,
    header_event: Optional[str] = None,
) -> Mapping[str, Any]:
    """Attach Linear webhook header event data for manager-based ingestion."""
    if not header_event:
        return payload
    enriched = dict(payload)
    enriched[HEADER_EVENT_PAYLOAD_KEY] = header_event
    return enriched


def _header_event_from_payload(payload: Mapping[str, Any]) -> Optional[str]:
    return _string_value(payload.get(HEADER_EVENT_PAYLOAD_KEY))


def _event_type(payload: Mapping[str, Any], header_event: Optional[str] = None) -> Optional[str]:
    return app_client.webhook_event_type(dict(payload), header_event)


def _is_agent_session_event(
    payload: Mapping[str, Any],
    header_event: Optional[str] = None,
) -> bool:
    return _event_type(payload, header_event) == "AgentSessionEvent"


def _work_item_from_issue(
    issue: Mapping[str, Any],
    refs: ProviderRefFactory = LINEAR_REFS,
) -> Optional[WorkItem]:
    issue_id = _string_value(issue.get("id"))
    if not issue_id:
        return None
    state = issue.get("state")
    state_name = _dict_value(state).get("name") if isinstance(state, Mapping) else state

    return WorkItem(
        ref=refs.ref(issue_id, url=_string_value(issue.get("url"))),
        identifier=_string_value(issue.get("identifier")),
        title=_string_value(issue.get("title")),
        state=_string_value(state_name),
    )


def _thread_from_session(
    agent_session: Mapping[str, Any],
    *,
    prompt_context: Optional[str] = None,
    refs: ProviderRefFactory = LINEAR_REFS,
) -> Optional[ConversationThread]:
    session_id = _string_value(agent_session.get("id"))
    if not session_id:
        return None

    issue = _dict_value(agent_session.get("issue"))
    return ConversationThread(
        ref=refs.ref(session_id, url=_string_value(agent_session.get("url"))),
        work_item=_work_item_from_issue(issue, refs) if issue else None,
        prompt_context=prompt_context
        or _string_value(agent_session.get("promptContext"))
        or _string_value(agent_session.get("context")),
    )


def _message_kind(activity: Mapping[str, Any]) -> MessageKind:
    content = _dict_value(activity.get("content"))
    signal = _string_value(activity.get("signal") or content.get("signal"))
    if signal == "stop":
        return "stop"

    value = _string_value(activity.get("type") or content.get("type"))
    if value in {"prompt", "thought", "response", "elicitation", "error", "stop"}:
        return cast(MessageKind, value)
    return "unknown"


def _message_body(activity: Mapping[str, Any]) -> Optional[str]:
    content = _dict_value(activity.get("content"))
    return _string_value(activity.get("body") or content.get("body"))


def _message_ref(
    activity: Mapping[str, Any],
    refs: ProviderRefFactory = LINEAR_REFS,
) -> Optional[ExternalRef]:
    activity_id = _string_value(activity.get("id"))
    return refs.ref(activity_id) if activity_id else None


def _message_from_activity(
    activity: Mapping[str, Any],
    *,
    direction: str = "inbound",
    state: str = "received",
    metadata: Optional[Mapping[str, Any]] = None,
    refs: ProviderRefFactory = LINEAR_REFS,
) -> Optional[ConversationMessage]:
    if not activity:
        return None
    return ConversationMessage(
        kind=_message_kind(activity),
        body=_message_body(activity),
        ref=_message_ref(activity, refs),
        direction=direction,  # type: ignore[arg-type]
        state=state,  # type: ignore[arg-type]
        metadata=dict(metadata) if metadata is not None else None,
    )


def _activity_nodes(value: Any) -> List[Mapping[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        nodes = value.get("nodes")
        if isinstance(nodes, list):
            return [item for item in nodes if isinstance(item, Mapping)]
    return []


def _linear_message_read_presentation_metadata(
    agent_session: Mapping[str, Any],
    activity: Mapping[str, Any],
    *,
    prompt_context: Optional[str] = None,
) -> Mapping[str, Any]:
    """Build provider-authored metadata for read_inbox_message presentation."""

    return inbox_read_presentation_metadata(
        workspace=_linear_workspace_hint(agent_session),
        source_label=_linear_actor_label(activity) or "Linear",
        context=(
            {"linear_prompt_context": _bounded_prompt_context(prompt_context)}
            if prompt_context
            else None
        ),
    )


def _linear_workspace_hint(agent_session: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    session_id = _string_value(agent_session.get("id"))
    if not session_id:
        return None

    breadcrumb: dict[str, str] = {"agent_session_id": session_id}
    issue = _dict_value(agent_session.get("issue"))
    if issue:
        issue_identifier = _string_value(issue.get("identifier"))
        issue_id = _string_value(issue.get("id"))
        if issue_identifier:
            breadcrumb["issue"] = issue_identifier
        elif issue_id:
            breadcrumb["issue_id"] = issue_id
    return {"name": "Linear", "breadcrumb": breadcrumb}


def _message_from_prompt_context(
    agent_session: Mapping[str, Any],
    *,
    prompt_context: str,
    metadata: Optional[Mapping[str, Any]] = None,
    refs: ProviderRefFactory = LINEAR_REFS,
) -> Optional[ConversationMessage]:
    session_id = _string_value(agent_session.get("id"))
    if not session_id:
        return None
    return ConversationMessage(
        kind="prompt",
        body=CONTEXT_ONLY_MESSAGE_BODY,
        ref=refs.ref(f"agent-session:{session_id}:prompt-context"),
        direction="inbound",
        state="received",
        metadata=dict(metadata) if metadata is not None else None,
    )


class LinearPresenceProvider:
    """Translate Linear Agent Sessions and Activities into CAO presence models."""

    name = PROVIDER

    def __init__(self, client: Any = app_client) -> None:
        self._client = client
        self._refs = ProviderRefFactory(self.name)

    def normalize_event(
        self,
        raw_event: Mapping[str, Any],
        *,
        delivery_id: Optional[str] = None,
        header_event: Optional[str] = None,
    ) -> Optional[PresenceEvent]:
        effective_header_event = header_event or _header_event_from_payload(raw_event)
        payload = dict(raw_event)
        payload.pop(HEADER_EVENT_PAYLOAD_KEY, None)

        if not _is_agent_session_event(payload, effective_header_event):
            return None

        agent_session = self._client.agent_session_from_payload(payload)
        prompt_context = self._client.prompt_context_from_payload(payload)
        thread = _thread_from_session(
            agent_session,
            prompt_context=prompt_context,
            refs=self._refs,
        )
        activity = self._client.agent_activity_from_payload(payload)
        data = _dict_value(payload.get("data"))
        action = _string_value(payload.get("action") or data.get("action"))
        message = _message_from_activity(
            activity,
            metadata=_linear_message_read_presentation_metadata(
                agent_session,
                activity,
                prompt_context=prompt_context,
            ),
            refs=self._refs,
        )
        if (message is None or (message.kind == "prompt" and not message.body)) and prompt_context:
            message = _message_from_prompt_context(
                agent_session,
                prompt_context=prompt_context,
                metadata=_linear_message_read_presentation_metadata(
                    agent_session,
                    activity,
                    prompt_context=prompt_context,
                ),
                refs=self._refs,
            )

        return PresenceEvent(
            provider=PROVIDER,
            event_type=_event_type(payload, effective_header_event) or "AgentSessionEvent",
            action=action,
            thread=thread,
            message=message,
            delivery_id=delivery_id,
            raw_payload=payload,
        )

    def fetch_thread(self, thread_ref: ExternalRef) -> ConversationThread:
        self._require_linear_ref(thread_ref)
        session = self._client.get_agent_session(thread_ref.id)
        thread = _thread_from_session(
            session,
            prompt_context=_string_value(session.get("promptContext") or session.get("context")),
            refs=self._refs,
        )
        if thread is None:
            raise app_client.LinearAppError(f"Linear AgentSession not found: {thread_ref.id}")
        return thread

    def fetch_messages(self, thread_ref: ExternalRef) -> List[ConversationMessage]:
        self._require_linear_ref(thread_ref)
        activities = self._client.list_agent_session_activities(thread_ref.id)
        messages = [
            message
            for activity in activities
            if (message := _message_from_activity(activity, refs=self._refs)) is not None
        ]
        return messages

    def reply_to_thread(
        self,
        thread_ref: ExternalRef,
        body: str,
        *,
        kind: MessageKind = "response",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ConversationMessage:
        self._require_linear_ref(thread_ref)
        content = {"type": kind, "body": body}
        app_key = _app_key_from_reply_metadata(metadata)
        activity = self._client.create_agent_activity(thread_ref.id, content, app_key=app_key)
        activity_id = _string_value(activity.get("id")) if isinstance(activity, Mapping) else None
        return ConversationMessage(
            kind=kind,
            body=body,
            ref=self._refs.ref(activity_id) if activity_id else None,
            direction="outbound",
            state="delivered",
        )

    def acknowledge_stop(
        self,
        thread_ref: ExternalRef,
        *,
        message_ref: Optional[ExternalRef] = None,
        reason: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> StopAcknowledgement:
        self._require_linear_ref(thread_ref)
        body = reason or STOP_ACK_BODY
        message = self.reply_to_thread(
            thread_ref,
            body,
            kind="response",
            metadata=metadata,
        )
        return StopAcknowledgement(
            thread_ref=thread_ref,
            supported=True,
            message=message,
            reason=reason,
        )

    def _require_linear_ref(self, ref: ExternalRef) -> None:
        if ref.provider != PROVIDER:
            raise ValueError(f"Linear provider cannot handle ref for provider {ref.provider}")


def _app_key_from_reply_metadata(metadata: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not metadata:
        return None
    for key in ("_cao_linear_app_key", "app_key", "linear_app_key"):
        value = metadata.get(key)
        if value:
            return str(value)
    for key in ("thread_metadata", "thread_raw_snapshot", "raw_snapshot"):
        found = _app_key_from_nested(metadata.get(key))
        if found:
            return found
    return None


def _app_key_from_nested(value: Any) -> Optional[str]:
    if isinstance(value, Mapping):
        direct = value.get("_cao_linear_app_key") or value.get("app_key") or value.get("appKey")
        if direct:
            return str(direct)
        data = value.get("data")
        if isinstance(data, Mapping):
            found = _app_key_from_nested(data)
            if found:
                return found
        for item in value.values():
            found = _app_key_from_nested(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _app_key_from_nested(item)
            if found:
                return found
    return None


def _linear_actor_label(metadata: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not metadata:
        return None
    for key in ("actor", "author", "user", "creator"):
        item = metadata.get(key)
        if isinstance(item, Mapping):
            name = item.get("name") or item.get("displayName") or item.get("email")
            if name:
                return _bounded_compact(str(name))
        elif isinstance(item, str) and item.strip():
            return _bounded_compact(item)
    data = metadata.get("data")
    if isinstance(data, Mapping):
        found = _linear_actor_label(data)
        if found:
            return found
    return None


def _bounded_compact(value: str, max_chars: int = 120) -> str:
    compacted = " ".join(value.split())
    if len(compacted) <= max_chars:
        return compacted
    suffix = "..."
    return compacted[: max(0, max_chars - len(suffix))].rstrip() + suffix


def _bounded_prompt_context(value: str) -> str:
    if len(value) <= LINEAR_INBOX_CONTEXT_CHARS:
        return value
    suffix = "..."
    return value[: max(0, LINEAR_INBOX_CONTEXT_CHARS - len(suffix))].rstrip() + suffix


def thread_from_agent_session(agent_session: Mapping[str, Any]) -> Optional[ConversationThread]:
    """Translate a Linear AgentSession GraphQL object into a neutral thread."""
    return _thread_from_session(agent_session)


def messages_from_agent_session(agent_session: Mapping[str, Any]) -> List[ConversationMessage]:
    """Translate first-page Linear AgentActivity nodes into neutral messages."""
    activities = _activity_nodes(agent_session.get("agentActivities"))
    if not activities:
        activities = _activity_nodes(agent_session.get("activities"))
    return [
        message
        for activity in activities
        if (message := _message_from_activity(activity)) is not None
    ]

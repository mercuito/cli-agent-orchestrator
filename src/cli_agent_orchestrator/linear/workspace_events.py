"""Linear CAO event declarations and publishers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import field
from datetime import datetime, timezone
from typing import Any, ClassVar, Literal, Mapping, Optional
from uuid import uuid4

from pydantic.dataclasses import dataclass

from cli_agent_orchestrator.events import (
    AgentParticipant,
    CaoCausationId,
    CaoCorrelationId,
    CaoEvent,
    CaoEventDispatcher,
    CaoEventId,
    CaoEventOccurredAt,
    CaoEventPublication,
    CaoEventSourceId,
    CaoEventSourceRef,
    CaoEventSourceType,
    default_cao_event_dispatcher,
)
from cli_agent_orchestrator.workspace_providers.tool_access import ProviderToolInvocationContext

LINEAR_PROVIDER_NAME = "linear"
LINEAR_CAO_SOURCE_TYPE = CaoEventSourceType(LINEAR_PROVIDER_NAME)
LINEAR_AGENT_PARTICIPANT_ROLE_MENTIONED = "mentioned"
LINEAR_AGENT_PARTICIPANT_ROLE_DELEGATED = "delegated"
LINEAR_AGENT_PARTICIPANT_ROLE_PROMPTED = "prompted"
LINEAR_AGENT_PARTICIPANT_ROLE_LIFECYCLE_ACTIVITY = "lifecycle_activity"
LINEAR_AGENT_PARTICIPANT_ROLE_STOP_REQUESTED = "stop_requested"
LINEAR_AGENT_PARTICIPANT_ROLE_CREATED_ISSUE = "created_issue"
LINEAR_AGENT_SESSION_CLASSIFICATION_KEY = "_cao_linear_agent_session_classification"
LINEAR_WEBHOOK_PACKET_METADATA_KEY = "_cao_linear_webhook_packet"
INBOX_READ_PRESENTATION_METADATA_KEY = "_cao_inbox_read_presentation"
LEADING_LINEAR_MENTION_PATTERN = re.compile(
    r"^\s*(?:@\S+|<user\b[^>]*>.*?</user>)\s*",
    re.IGNORECASE | re.DOTALL,
)


def _default_event_id() -> CaoEventId:
    return CaoEventId(f"{LINEAR_PROVIDER_NAME}:event:{uuid4()}")


def _default_source() -> CaoEventSourceRef:
    return CaoEventSourceRef(
        source_type=LINEAR_CAO_SOURCE_TYPE,
        source_id=CaoEventSourceId(LINEAR_PROVIDER_NAME),
    )


def _now() -> CaoEventOccurredAt:
    return CaoEventOccurredAt(datetime.now(timezone.utc))


@dataclass(frozen=True, kw_only=True)
class LinearIssueContextEvent:
    """Linear provider event carrying issue/session facts for workspace context resolution."""

    provider_name: ClassVar[str] = LINEAR_PROVIDER_NAME
    event_name: ClassVar[str] = "issue_context"
    description: ClassVar[str] = "Linear issue/session facts for workspace context resolution."

    event_id: CaoEventId = field(default_factory=_default_event_id)
    source: CaoEventSourceRef = field(default_factory=_default_source)
    occurred_at: CaoEventOccurredAt = field(default_factory=_now)
    correlation_id: CaoCorrelationId | None = None
    causation_id: CaoCausationId | None = None

    event_type: str | None = None
    app_key: str | None = None
    agent_id: str | None = None
    app_user_id: str | None = None
    app_user_name: str | None = None
    issue_id: str | None = None
    issue_identifier: str | None = None
    issue_url: str | None = None
    issue_title: str | None = None
    issue_state: str | None = None
    parent_issue_id: str | None = None
    parent_issue_identifier: str | None = None
    agent_session_id: str | None = None
    thread_id: str | None = None
    thread_url: str | None = None
    prompt_context: str | None = None
    message_id: str | None = None
    message_body: str | None = None
    message_kind: str | None = None
    message_metadata: Mapping[str, Any] | None = None
    action: str | None = None
    should_notify_agent: bool = True
    suppression_reason: str | None = None
    raw_payload: Mapping[str, Any] | None = None
    delivery_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    agent_participants: tuple[AgentParticipant, ...] = ()

    @property
    def canonical_issue_id(self) -> str | None:
        return self.issue_identifier or self.issue_id

    @property
    def boundary_issue_id(self) -> str | None:
        return self.parent_issue_identifier or self.parent_issue_id or self.canonical_issue_id


@dataclass(frozen=True, kw_only=True)
class LinearAgentMentionedEvent(LinearIssueContextEvent):
    """Human mention or prompt routed to a Linear agent."""

    event_name: ClassVar[str] = "agent_mentioned"
    description: ClassVar[str] = "Human mention or prompt routed to a Linear agent."
    kind: Literal["linear.agent_mentioned"] = "linear.agent_mentioned"


@dataclass(frozen=True, kw_only=True)
class LinearIssueDelegatedToAgentEvent(LinearIssueContextEvent):
    """Linear issue delegation routed to an agent."""

    event_name: ClassVar[str] = "issue_delegated_to_agent"
    description: ClassVar[str] = "Linear issue delegation routed to an agent."
    kind: Literal["linear.issue_delegated_to_agent"] = "linear.issue_delegated_to_agent"


@dataclass(frozen=True, kw_only=True)
class LinearAgentSessionPromptedEvent(LinearIssueContextEvent):
    """Follow-up prompt inside an existing Linear AgentSession."""

    event_name: ClassVar[str] = "agent_session_prompted"
    description: ClassVar[str] = "Follow-up prompt inside an existing Linear AgentSession."
    kind: Literal["linear.agent_session_prompted"] = "linear.agent_session_prompted"


@dataclass(frozen=True, kw_only=True)
class LinearAgentSessionLifecycleActivityEvent(LinearIssueContextEvent):
    """Linear AgentSession lifecycle activity that may affect routing or state."""

    event_name: ClassVar[str] = "agent_session_lifecycle_activity"
    description: ClassVar[str] = (
        "Linear AgentSession lifecycle activity that may affect routing or state."
    )
    kind: Literal["linear.agent_session_lifecycle_activity"] = (
        "linear.agent_session_lifecycle_activity"
    )


@dataclass(frozen=True, kw_only=True)
class LinearAgentSessionStopRequestedEvent(LinearIssueContextEvent):
    """Linear stop/cancel signal for an existing AgentSession."""

    event_name: ClassVar[str] = "agent_session_stop_requested"
    description: ClassVar[str] = "Linear stop/cancel signal for an existing AgentSession."
    kind: Literal["linear.agent_session_stop_requested"] = "linear.agent_session_stop_requested"


@dataclass(frozen=True, kw_only=True)
class LinearIssueCreatedEvent:
    """Linear create_issue tool result published by the Linear workspace provider."""

    provider_name: ClassVar[str] = LINEAR_PROVIDER_NAME
    event_name: ClassVar[str] = "issue_created"
    description: ClassVar[str] = "Linear issue created through a CAO-mediated Linear tool."
    kind: Literal["linear.issue_created"] = "linear.issue_created"

    event_id: CaoEventId = field(default_factory=_default_event_id)
    source: CaoEventSourceRef = field(default_factory=_default_source)
    occurred_at: CaoEventOccurredAt = field(default_factory=_now)
    correlation_id: CaoCorrelationId | None = None
    causation_id: CaoCausationId | None = None

    terminal_id: str
    agent_id: str
    tool_name: str
    issue: Mapping[str, Any]
    delivery_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    agent_participants: tuple[AgentParticipant, ...] = ()


LINEAR_CAO_EVENTS = (
    LinearAgentMentionedEvent,
    LinearIssueDelegatedToAgentEvent,
    LinearAgentSessionPromptedEvent,
    LinearAgentSessionLifecycleActivityEvent,
    LinearAgentSessionStopRequestedEvent,
    LinearIssueCreatedEvent,
)


def register_linear_cao_events(
    dispatcher: CaoEventDispatcher | None = None,
) -> CaoEventDispatcher:
    """Register Linear's CAO events on ``dispatcher``."""

    event_dispatcher = dispatcher or default_cao_event_dispatcher()
    event_dispatcher.register_events(LINEAR_CAO_EVENTS)
    return event_dispatcher


def publish_linear_provider_event(
    payload: Mapping[str, Any],
    *,
    delivery_id: str | None = None,
    header_event: str | None = None,
    dispatcher: CaoEventDispatcher | None = None,
) -> CaoEventPublication[LinearIssueContextEvent] | None:
    """Publish the semantic Linear CAO event for a Linear webhook/monitor packet."""

    semantic = linear_provider_event_from_payload(
        payload,
        delivery_id=delivery_id,
        header_event=header_event,
    )
    if semantic is None:
        return None
    event_dispatcher = register_linear_cao_events(dispatcher)
    return event_dispatcher.publish(semantic)


def linear_provider_event_from_payload(
    payload: Mapping[str, Any],
    *,
    delivery_id: str | None = None,
    header_event: str | None = None,
) -> LinearIssueContextEvent | None:
    """Build Linear's typed CAO event from a provider-shaped packet."""

    from cli_agent_orchestrator.linear.webhook_ingestion import parse_linear_webhook_packet

    packet = parse_linear_webhook_packet(payload, header_event=header_event)
    if packet.resource_family != "agent_session" or not packet.supported:
        return None
    classification = packet.agent_session_classification
    if classification is None:
        return None
    event_kwargs = _issue_context_event_kwargs(
        payload,
        packet=packet,
        classification=classification,
        delivery_id=delivery_id,
    )
    if classification.kind == "human_mention_or_prompt":
        return LinearAgentMentionedEvent(**event_kwargs)
    if classification.kind == "human_issue_delegation":
        return LinearIssueDelegatedToAgentEvent(**event_kwargs)
    if classification.kind == "follow_up_user_prompt":
        return LinearAgentSessionPromptedEvent(**event_kwargs)
    if classification.kind == "stop_or_cancel":
        return LinearAgentSessionStopRequestedEvent(**event_kwargs)
    return LinearAgentSessionLifecycleActivityEvent(**event_kwargs)


def publish_linear_issue_created_event(
    context: ProviderToolInvocationContext,
    *,
    dispatcher: CaoEventDispatcher | None = None,
) -> CaoEventPublication[LinearIssueCreatedEvent] | None:
    """Publish a Linear create_issue result from the provider tool lifecycle."""

    event = linear_issue_created_event_from_context(context)
    if event is None:
        return None
    event_dispatcher = register_linear_cao_events(dispatcher)
    return event_dispatcher.publish(event)


def linear_issue_created_event_from_context(
    context: ProviderToolInvocationContext,
) -> LinearIssueCreatedEvent | None:
    """Build a Linear issue-created event from a mediated tool result."""

    result = context.handler_result
    if not isinstance(result, Mapping):
        return None
    issue_id = _string_value(result.get("identifier") or result.get("id"))
    return LinearIssueCreatedEvent(
        event_id=_cao_event_id(
            LinearIssueCreatedEvent.event_name,
            context.terminal_id,
            context.tool_name,
            issue_id,
        ),
        source=_cao_source_ref(issue_id or context.terminal_id),
        occurred_at=_now(),
        correlation_id=CaoCorrelationId(context.terminal_id),
        terminal_id=context.terminal_id,
        agent_id=context.agent.id,
        tool_name=context.tool_name,
        issue=result,
        agent_participants=_agent_participants(
            context.agent.id,
            LINEAR_AGENT_PARTICIPANT_ROLE_CREATED_ISSUE,
        ),
        metadata={"hook_name": context.hook_name, "phase": str(context.phase)},
    )


def _issue_context_event_kwargs(
    payload: Mapping[str, Any],
    *,
    packet: Any,
    classification: Any,
    delivery_id: str | None,
) -> dict[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    raw_payload = _payload_with_linear_metadata(payload, packet, classification)
    issue = _issue_from_raw_payload(raw_payload)
    issue_fields = _issue_fields(issue) if issue is not None else {}
    agent_session = app_client.agent_session_from_payload(dict(raw_payload))
    activity = app_client.agent_activity_from_payload(dict(raw_payload))
    message = _message_fields(agent_session, activity, classification)
    agent_session_id = _string_value(app_client.agent_session_id_from_payload(dict(raw_payload)))
    message_id = message.get("message_id")
    source_id = delivery_id or _string_value(message_id) or agent_session_id
    event_name = _event_name_for_classification(classification.kind)
    return {
        **issue_fields,
        "event_id": _cao_event_id(event_name, source_id, packet.action),
        "source": _cao_source_ref(source_id or packet.event_type),
        "occurred_at": _occurred_at_from_payload(raw_payload),
        "correlation_id": CaoCorrelationId(agent_session_id) if agent_session_id else None,
        "event_type": packet.event_type,
        "app_key": _normalize_app_key(raw_payload.get("_cao_linear_app_key")),
        "agent_id": _string_value(raw_payload.get("_cao_linear_agent_id")),
        "app_user_id": _string_value(raw_payload.get("_cao_linear_app_user_id")),
        "app_user_name": _string_value(raw_payload.get("_cao_linear_app_user_name")),
        "agent_session_id": agent_session_id,
        "thread_id": agent_session_id,
        "thread_url": _string_value(agent_session.get("url")),
        "prompt_context": _string_value(
            app_client.prompt_context_from_payload(dict(raw_payload))
            or agent_session.get("promptContext")
            or agent_session.get("context")
        ),
        **message,
        "action": packet.action,
        "should_notify_agent": classification.should_notify_agent,
        "suppression_reason": classification.suppression_reason,
        "delivery_id": delivery_id,
        "metadata": {"action": packet.action, "classification": classification.kind},
        "agent_participants": _agent_participants(
            _string_value(raw_payload.get("_cao_linear_agent_id")),
            _participant_role_for_classification(classification.kind),
        ),
        "raw_payload": raw_payload,
    }


def _event_name_for_classification(kind: str) -> str:
    if kind == "human_mention_or_prompt":
        return LinearAgentMentionedEvent.event_name
    if kind == "human_issue_delegation":
        return LinearIssueDelegatedToAgentEvent.event_name
    if kind == "follow_up_user_prompt":
        return LinearAgentSessionPromptedEvent.event_name
    if kind == "stop_or_cancel":
        return LinearAgentSessionStopRequestedEvent.event_name
    return LinearAgentSessionLifecycleActivityEvent.event_name


def _participant_role_for_classification(kind: str) -> str:
    if kind == "human_mention_or_prompt":
        return LINEAR_AGENT_PARTICIPANT_ROLE_MENTIONED
    if kind == "human_issue_delegation":
        return LINEAR_AGENT_PARTICIPANT_ROLE_DELEGATED
    if kind == "follow_up_user_prompt":
        return LINEAR_AGENT_PARTICIPANT_ROLE_PROMPTED
    if kind == "stop_or_cancel":
        return LINEAR_AGENT_PARTICIPANT_ROLE_STOP_REQUESTED
    return LINEAR_AGENT_PARTICIPANT_ROLE_LIFECYCLE_ACTIVITY


def _agent_participants(
    agent_id: str | None,
    role: str,
) -> tuple[AgentParticipant, ...]:
    if agent_id is None:
        return ()
    return (AgentParticipant(agent_id=agent_id, role=role),)


def _cao_event_id(event_name: str, *parts: str | None) -> CaoEventId:
    normalized_parts = [part for part in parts if part]
    if normalized_parts:
        source = ":".join(normalized_parts)
    else:
        source = str(uuid4())
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]
    return CaoEventId(f"{LINEAR_PROVIDER_NAME}:{event_name}:{digest}")


def _cao_source_ref(source_id: str | None) -> CaoEventSourceRef:
    return CaoEventSourceRef(
        source_type=LINEAR_CAO_SOURCE_TYPE,
        source_id=CaoEventSourceId(source_id or LINEAR_PROVIDER_NAME),
    )


def _occurred_at_from_payload(payload: Mapping[str, Any]) -> CaoEventOccurredAt:
    for key in ("webhookTimestamp", "createdAt", "updatedAt"):
        value = _string_value(payload.get(key))
        if value is None:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return CaoEventOccurredAt(parsed.astimezone(timezone.utc))
    return _now()


def _issue_from_raw_payload(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    from cli_agent_orchestrator.linear import app_client

    agent_session = app_client.agent_session_from_payload(dict(payload))
    issue = agent_session.get("issue") if isinstance(agent_session, Mapping) else None
    if isinstance(issue, Mapping):
        return issue
    data = payload.get("data")
    if isinstance(data, Mapping):
        issue = data.get("issue")
        if isinstance(issue, Mapping):
            return issue
    issue = payload.get("issue")
    return issue if isinstance(issue, Mapping) else None


def _issue_fields(issue: Mapping[str, Any]) -> dict[str, str | None]:
    issue_id = _string_value(issue.get("id"))
    parent = issue.get("parent") or issue.get("parentIssue")
    parent_issue_id = None
    parent_issue_identifier = None
    if isinstance(parent, Mapping):
        parent_issue_id = _string_value(parent.get("id"))
        parent_issue_identifier = _string_value(parent.get("identifier"))
    return {
        "issue_id": issue_id,
        "issue_identifier": _string_value(issue.get("identifier")),
        "issue_url": _string_value(issue.get("url")),
        "issue_title": _string_value(issue.get("title")),
        "issue_state": _issue_state(issue),
        "parent_issue_id": parent_issue_id,
        "parent_issue_identifier": parent_issue_identifier,
    }


def _payload_with_linear_metadata(
    payload: Mapping[str, Any],
    packet: Any,
    classification: Any,
) -> Mapping[str, Any]:
    raw_payload = dict(payload)
    raw_payload[LINEAR_WEBHOOK_PACKET_METADATA_KEY] = packet.as_metadata()
    raw_payload[LINEAR_AGENT_SESSION_CLASSIFICATION_KEY] = classification.as_metadata()
    return raw_payload


def _message_fields(
    agent_session: Mapping[str, Any],
    activity: Mapping[str, Any],
    classification: Any,
) -> dict[str, Any]:
    if activity:
        body = _string_value(
            activity.get("body") or _dict_value(activity.get("content")).get("body")
        )
        return {
            "message_id": _string_value(activity.get("id")),
            "message_body": body,
            "message_kind": _activity_kind(activity),
            "message_metadata": _message_metadata(agent_session, activity),
        }
    if not classification.should_notify_agent:
        return {
            "message_id": None,
            "message_body": None,
            "message_kind": None,
            "message_metadata": None,
        }
    comment = _dict_value(agent_session.get("comment"))
    body = _message_body_from_session_comment(comment)
    session_id = _string_value(agent_session.get("id"))
    comment_id = _string_value(comment.get("id"))
    return {
        "message_id": comment_id or (f"agent-session:{session_id}:comment" if session_id else None),
        "message_body": body,
        "message_kind": "prompt" if body else None,
        "message_metadata": _message_metadata(agent_session, agent_session),
    }


def _activity_kind(activity: Mapping[str, Any]) -> str:
    content = _dict_value(activity.get("content"))
    signal = _string_value(activity.get("signal") or content.get("signal"))
    if signal == "stop":
        return "stop"
    value = _string_value(activity.get("type") or content.get("type"))
    if value in {"prompt", "thought", "response", "elicitation", "error", "stop"}:
        return value
    return "unknown"


def _message_body_from_session_comment(comment: Mapping[str, Any]) -> str | None:
    body = _string_value(comment.get("body"))
    if not body:
        return None
    stripped = LEADING_LINEAR_MENTION_PATTERN.sub("", body, count=1).strip()
    return stripped or None


def _message_metadata(
    agent_session: Mapping[str, Any],
    source: Mapping[str, Any],
) -> Mapping[str, Any]:
    presentation: dict[str, Any] = {}
    workspace = _linear_workspace_hint(agent_session)
    if workspace:
        presentation["workspace"] = workspace
    source_label = _linear_actor_label(source) or _linear_actor_label(agent_session) or "Linear"
    presentation["source_label"] = source_label
    return {INBOX_READ_PRESENTATION_METADATA_KEY: presentation}


def _linear_workspace_hint(agent_session: Mapping[str, Any]) -> Mapping[str, Any] | None:
    session_id = _string_value(agent_session.get("id"))
    if not session_id:
        return None
    breadcrumb: dict[str, str] = {"agent_session_id": session_id}
    issue = _dict_value(agent_session.get("issue"))
    issue_identifier = _string_value(issue.get("identifier"))
    issue_id = _string_value(issue.get("id"))
    if issue_identifier:
        breadcrumb["issue"] = issue_identifier
    elif issue_id:
        breadcrumb["issue_id"] = issue_id
    return {"name": "Linear", "breadcrumb": breadcrumb}


def _linear_actor_label(value: Mapping[str, Any]) -> str | None:
    actor = _dict_value(value.get("actor") or value.get("creator") or value.get("user"))
    return _string_value(actor.get("name") or actor.get("displayName") or actor.get("email"))


def _issue_state(issue: Mapping[str, Any]) -> str | None:
    state = issue.get("state")
    if isinstance(state, Mapping):
        return _string_value(state.get("name"))
    return _string_value(state)


def _dict_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _normalize_app_key(value: Any) -> str | None:
    text = _string_value(value)
    if not text:
        return None
    from cli_agent_orchestrator.linear.workspace_provider import normalize_app_key

    return normalize_app_key(text)


def _string_value(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    text = str(value).strip()
    return text or None

"""Linear AgentSession packet classification.

This module is the Linear-owned boundary for interpreting AgentSession
webhook/monitor packets before CAO's generic presence persistence and inbox
delivery paths see them.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal, Mapping, Optional

from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.presence.models import PresenceEvent

LEADING_LINEAR_MENTION_PATTERN = re.compile(
    r"^\s*(?:@\S+|<user\b[^>]*>.*?</user>)\s+",
    re.IGNORECASE | re.DOTALL,
)
LINEAR_AGENT_SESSION_CLASSIFICATION_KEY = "_cao_linear_agent_session_classification"

LinearAgentSessionEventKind = Literal[
    "human_mention_or_prompt",
    "human_issue_delegation",
    "app_created_session_bootstrap",
    "follow_up_user_prompt",
    "stop_or_cancel",
    "agent_lifecycle_activity",
    "unknown",
]
LINEAR_AGENT_SESSION_EVENT_KINDS = frozenset(
    {
        "human_mention_or_prompt",
        "human_issue_delegation",
        "app_created_session_bootstrap",
        "follow_up_user_prompt",
        "stop_or_cancel",
        "agent_lifecycle_activity",
        "unknown",
    }
)


@dataclass(frozen=True)
class LinearAgentSessionClassification:
    """Provider-local interpretation of one Linear AgentSession packet."""

    kind: LinearAgentSessionEventKind
    should_notify_agent: bool
    suppression_reason: Optional[str] = None

    def as_metadata(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "should_notify_agent": self.should_notify_agent,
        }
        if self.suppression_reason:
            result["suppression_reason"] = self.suppression_reason
        return result


def classify_agent_session_payload(
    payload: Mapping[str, Any],
    *,
    header_event: Optional[str] = None,
) -> Optional[LinearAgentSessionClassification]:
    """Classify a Linear AgentSession packet for notification decisions."""

    if app_client.webhook_event_type(dict(payload), header_event) != "AgentSessionEvent":
        return None

    activity = app_client.agent_activity_from_payload(dict(payload))
    if activity:
        return _classify_activity(activity)

    agent_session = app_client.agent_session_from_payload(dict(payload))
    if not agent_session:
        return LinearAgentSessionClassification(
            kind="unknown",
            should_notify_agent=False,
            suppression_reason="missing_agent_session",
        )

    if _has_explicit_session_comment_mention(agent_session):
        return LinearAgentSessionClassification(
            kind="human_mention_or_prompt",
            should_notify_agent=True,
        )

    if _looks_like_app_created_session_bootstrap(agent_session):
        return LinearAgentSessionClassification(
            kind="app_created_session_bootstrap",
            should_notify_agent=False,
            suppression_reason="linear_app_created_session_bootstrap",
        )

    if _has_issue_delegate(agent_session):
        return LinearAgentSessionClassification(
            kind="human_issue_delegation",
            should_notify_agent=True,
        )

    return LinearAgentSessionClassification(
        kind="human_mention_or_prompt",
        should_notify_agent=True,
    )


def classification_from_event(
    event: Optional[PresenceEvent],
) -> Optional[LinearAgentSessionClassification]:
    """Read a stored Linear classifier result from a normalized event."""

    if event is None or event.raw_payload is None:
        return None
    raw_value = event.raw_payload.get(LINEAR_AGENT_SESSION_CLASSIFICATION_KEY)
    if not isinstance(raw_value, Mapping):
        return None
    kind = raw_value.get("kind")
    should_notify = raw_value.get("should_notify_agent")
    if not isinstance(kind, str) or not isinstance(should_notify, bool):
        return None
    if kind not in LINEAR_AGENT_SESSION_EVENT_KINDS:
        return None
    suppression = raw_value.get("suppression_reason")
    return LinearAgentSessionClassification(
        kind=kind,  # type: ignore[arg-type]
        should_notify_agent=should_notify,
        suppression_reason=str(suppression) if suppression else None,
    )


def should_notify_agent(event: Optional[PresenceEvent]) -> bool:
    """Return whether the Linear event should create an agent notification."""

    classification = classification_from_event(event)
    return True if classification is None else classification.should_notify_agent


def _classify_activity(activity: Mapping[str, Any]) -> LinearAgentSessionClassification:
    content = _dict_value(activity.get("content"))
    signal = _string_value(activity.get("signal") or content.get("signal"))
    if signal == "stop":
        return LinearAgentSessionClassification(kind="stop_or_cancel", should_notify_agent=True)

    activity_type = _string_value(activity.get("type") or content.get("type"))
    if activity_type == "prompt":
        return LinearAgentSessionClassification(
            kind="follow_up_user_prompt",
            should_notify_agent=True,
        )
    if activity_type in {"thought", "response", "elicitation", "error"}:
        return LinearAgentSessionClassification(
            kind="agent_lifecycle_activity",
            should_notify_agent=False,
            suppression_reason=f"linear_agent_{activity_type}_activity",
        )
    return LinearAgentSessionClassification(kind="unknown", should_notify_agent=True)


def _looks_like_app_created_session_bootstrap(agent_session: Mapping[str, Any]) -> bool:
    # Observed Linear behavior as of May 2026:
    # - app-created sessions from agentSessionCreateOnIssue/Comment arrive with
    #   creator=null and sourceMetadata=null;
    # - human mention/delegation session bootstraps observed so far include a
    #   creator. Keep this assumption local to Linear and revisit if Linear's
    #   AgentSession packet shape changes.
    return not agent_session.get("creator") and not agent_session.get("sourceMetadata")


def _has_issue_delegate(agent_session: Mapping[str, Any]) -> bool:
    issue = _dict_value(agent_session.get("issue"))
    delegate = issue.get("delegate")
    return isinstance(delegate, Mapping) and bool(delegate.get("id") or delegate.get("name"))


def _has_explicit_session_comment_mention(agent_session: Mapping[str, Any]) -> bool:
    # Monitor-recovered AgentSession comments may not include Linear's creator
    # or sourceMetadata fields. Treat an explicit leading Linear mention as the
    # human invocation signal so monitor recovery does not suppress the comment
    # as an app-created bootstrap.
    comment = _dict_value(agent_session.get("comment"))
    body = _string_value(comment.get("body"))
    return bool(body and LEADING_LINEAR_MENTION_PATTERN.match(body))


def _dict_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_value(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)

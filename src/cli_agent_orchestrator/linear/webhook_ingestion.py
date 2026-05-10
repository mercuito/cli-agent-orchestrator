"""Linear webhook packet ingestion boundary.

Linear sends provider-shaped webhook and monitor packets. This module is the
first Linear-owned interpretation layer: it identifies the resource family,
action, support status, and any resource-specific classification before route
or runtime code decides what to do next.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional

from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear.agent_session_classifier import (
    LinearAgentSessionClassification,
    classify_agent_session_payload,
)

LINEAR_WEBHOOK_PACKET_METADATA_KEY = "_cao_linear_webhook_packet"

LinearWebhookResourceFamily = Literal[
    "agent_session",
    "issue",
    "comment",
    "project",
    "user",
    "unknown",
]


@dataclass(frozen=True)
class LinearWebhookPacket:
    """Provider-local routing facts for one Linear webhook/monitor packet."""

    event_type: Optional[str]
    action: Optional[str]
    resource_family: LinearWebhookResourceFamily
    supported: bool
    agent_session_id: Optional[str] = None
    agent_session_classification: Optional[LinearAgentSessionClassification] = None

    def as_metadata(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "event_type": self.event_type,
            "action": self.action,
            "resource_family": self.resource_family,
            "supported": self.supported,
        }
        if self.agent_session_id:
            result["agent_session_id"] = self.agent_session_id
        if self.agent_session_classification is not None:
            result["agent_session_classification"] = self.agent_session_classification.as_metadata()
        return result


def parse_linear_webhook_packet(
    payload: Mapping[str, Any],
    *,
    header_event: Optional[str] = None,
) -> LinearWebhookPacket:
    """Parse Linear webhook routing facts without mutating the raw packet."""

    payload_dict = dict(payload)
    data = _dict_value(payload_dict.get("data"))
    event_type = app_client.webhook_event_type(payload_dict, header_event)
    action = _string_value(payload_dict.get("action") or data.get("action"))
    resource_family = _resource_family(payload_dict, data, event_type)

    if resource_family == "agent_session":
        classification = classify_agent_session_payload(
            payload_dict,
            header_event=header_event,
        )
        return LinearWebhookPacket(
            event_type=event_type,
            action=action,
            resource_family=resource_family,
            supported=True,
            agent_session_id=app_client.agent_session_id_from_payload(payload_dict),
            agent_session_classification=classification,
        )

    return LinearWebhookPacket(
        event_type=event_type,
        action=action,
        resource_family=resource_family,
        supported=False,
    )


def _resource_family(
    payload: Mapping[str, Any],
    data: Mapping[str, Any],
    event_type: Optional[str],
) -> LinearWebhookResourceFamily:
    if event_type == "AgentSessionEvent" or _has_mapping(payload, data, "agentSession"):
        return "agent_session"
    if event_type in {"Issue", "IssueEvent"} or _has_mapping(payload, data, "issue"):
        return "issue"
    if event_type in {"Comment", "CommentEvent"} or _has_mapping(payload, data, "comment"):
        return "comment"
    if event_type in {"Project", "ProjectEvent"} or _has_mapping(payload, data, "project"):
        return "project"
    if event_type in {"User", "UserEvent"} or _has_mapping(payload, data, "user"):
        return "user"
    return "unknown"


def _has_mapping(payload: Mapping[str, Any], data: Mapping[str, Any], key: str) -> bool:
    return isinstance(payload.get(key), Mapping) or isinstance(data.get(key), Mapping)


def _dict_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_value(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)

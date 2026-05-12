"""Tests for the Linear webhook ingestion boundary."""

from __future__ import annotations

from cli_agent_orchestrator.linear.webhook_ingestion import (
    LINEAR_WEBHOOK_PACKET_METADATA_KEY,
    parse_linear_webhook_packet,
)
from cli_agent_orchestrator.linear.workspace_events import (
    LinearIssueContextEvent,
    linear_provider_event_from_payload,
)


def test_ingestion_routes_agent_session_packets_to_agent_session_family():
    packet = parse_linear_webhook_packet(
        {
            "action": "created",
            "data": {
                "agentSession": {
                    "id": "session-1",
                    "creator": {"id": "user-1", "name": "RJ Wilson"},
                    "sourceMetadata": {"type": "comment"},
                }
            },
        },
        header_event="AgentSessionEvent",
    )

    assert packet.event_type == "AgentSessionEvent"
    assert packet.action == "created"
    assert packet.resource_family == "agent_session"
    assert packet.supported is True
    assert packet.agent_session_id == "session-1"
    assert packet.agent_session_classification is not None
    assert packet.agent_session_classification.should_notify_agent is True


def test_ingestion_represents_issue_packets_as_unsupported_linear_family():
    packet = parse_linear_webhook_packet(
        {
            "type": "Issue",
            "action": "update",
            "data": {
                "issue": {
                    "id": "issue-1",
                    "identifier": "CAO-67",
                }
            },
        }
    )

    assert packet.event_type == "Issue"
    assert packet.action == "update"
    assert packet.resource_family == "issue"
    assert packet.supported is False
    assert packet.agent_session_classification is None


def test_linear_provider_event_stores_ingestion_metadata():
    event = linear_provider_event_from_payload(
        {
            "type": "AgentSessionEvent",
            "action": "created",
            "data": {
                "agentSession": {
                    "id": "session-1",
                    "creator": {"id": "user-1", "name": "RJ Wilson"},
                    "sourceMetadata": {"type": "comment"},
                }
            },
        }
    )

    assert event is not None
    assert isinstance(event, LinearIssueContextEvent)
    assert event.raw_payload is not None
    assert event.raw_payload[LINEAR_WEBHOOK_PACKET_METADATA_KEY] == {
        "event_type": "AgentSessionEvent",
        "action": "created",
        "resource_family": "agent_session",
        "supported": True,
        "agent_session_id": "session-1",
        "agent_session_classification": {
            "kind": "human_mention_or_prompt",
            "should_notify_agent": True,
        },
    }

"""Tests for Linear AgentSession packet classification."""

from __future__ import annotations

from cli_agent_orchestrator.linear.agent_session_classifier import (
    LINEAR_AGENT_SESSION_CLASSIFICATION_KEY,
    classify_agent_session_payload,
    classification_from_event,
)
from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider


def _session_payload(agent_session: dict, *, activity: dict | None = None) -> dict:
    data = {"agentSession": agent_session}
    if activity is not None:
        data["agentActivity"] = activity
    return {"type": "AgentSessionEvent", "action": "created", "data": data}


def test_classifies_app_created_issue_bootstrap_from_observed_linear_shape():
    payload = _session_payload(
        {
            "id": "session-proactive",
            "creator": None,
            "sourceMetadata": None,
            "comment": {
                "id": "comment-linear",
                "body": "RJ Wilson connected Discovery Partner to this issue.",
            },
            "issue": {"id": "issue-67", "identifier": "CAO-67"},
        }
    )

    classification = classify_agent_session_payload(payload)

    assert classification is not None
    assert classification.kind == "app_created_session_bootstrap"
    assert classification.should_notify_agent is False
    assert classification.suppression_reason == "linear_app_created_session_bootstrap"


def test_classifies_app_created_comment_bootstrap_from_observed_linear_shape():
    payload = _session_payload(
        {
            "id": "session-comment",
            "creator": None,
            "sourceMetadata": None,
            "comment": {"id": "comment-source", "body": "Original issue comment"},
            "issue": {"id": "issue-67", "identifier": "CAO-67"},
        }
    )

    classification = classify_agent_session_payload(payload)

    assert classification is not None
    assert classification.kind == "app_created_session_bootstrap"
    assert classification.should_notify_agent is False


def test_classifies_human_mention_session_as_notifiable():
    payload = _session_payload(
        {
            "id": "session-human",
            "creator": {"id": "user-1", "name": "RJ Wilson"},
            "sourceMetadata": {
                "type": "comment",
                "agentSessionMetadata": {"sourceCommentId": "comment-1"},
            },
            "comment": {"id": "comment-1", "body": "@discoverypartner testing"},
            "issue": {"id": "issue-67", "identifier": "CAO-67"},
        }
    )

    classification = classify_agent_session_payload(payload)

    assert classification is not None
    assert classification.kind == "human_mention_or_prompt"
    assert classification.should_notify_agent is True


def test_classifies_monitor_recovered_mention_comment_as_notifiable_without_creator_metadata():
    payload = _session_payload(
        {
            "id": "session-monitor",
            "creator": None,
            "sourceMetadata": None,
            "comment": {"id": "comment-1", "body": "@CAO Please recover this"},
            "issue": {"id": "issue-67", "identifier": "CAO-67"},
        }
    )

    classification = classify_agent_session_payload(payload)

    assert classification is not None
    assert classification.kind == "human_mention_or_prompt"
    assert classification.should_notify_agent is True


def test_classifies_human_delegation_session_as_notifiable():
    payload = _session_payload(
        {
            "id": "session-delegated",
            "creator": {"id": "user-1", "name": "RJ Wilson"},
            "sourceMetadata": None,
            "issue": {
                "id": "issue-67",
                "identifier": "CAO-67",
                "delegate": {"id": "app-user-1", "name": "Discovery Partner"},
            },
        }
    )

    classification = classify_agent_session_payload(payload)

    assert classification is not None
    assert classification.kind == "human_issue_delegation"
    assert classification.should_notify_agent is True


def test_classifies_later_user_prompt_activity_as_notifiable():
    payload = _session_payload(
        {"id": "session-proactive", "creator": None, "sourceMetadata": None},
        activity={
            "id": "activity-1",
            "content": {"type": "prompt", "body": "Can we scope this now?"},
        },
    )

    classification = classify_agent_session_payload(payload)

    assert classification is not None
    assert classification.kind == "follow_up_user_prompt"
    assert classification.should_notify_agent is True


def test_classification_metadata_survives_normalization():
    event = LinearPresenceProvider().normalize_event(
        _session_payload({"id": "session-proactive", "creator": None, "sourceMetadata": None})
    )

    assert event is not None
    assert event.raw_payload is not None
    assert event.raw_payload[LINEAR_AGENT_SESSION_CLASSIFICATION_KEY] == {
        "kind": "app_created_session_bootstrap",
        "should_notify_agent": False,
        "suppression_reason": "linear_app_created_session_bootstrap",
    }
    assert classification_from_event(event).should_notify_agent is False

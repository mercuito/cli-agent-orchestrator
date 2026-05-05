"""Tests for translating Linear payloads into provider-neutral presence events."""

from __future__ import annotations

from cli_agent_orchestrator.linear import translator


def test_agent_session_payload_translates_to_presence_event():
    payload = {
        "type": "AgentSessionEvent",
        "action": "prompted",
        "data": {
            "promptContext": "<issue identifier=\"CAO-13\"/>",
            "agentSession": {
                "id": "session-1",
                "url": "https://linear.app/session",
                "issue": {
                    "id": "issue-1",
                    "identifier": "CAO-13",
                    "title": "Discovery smoke",
                    "url": "https://linear.app/issue",
                },
            },
            "agentActivity": {
                "id": "activity-1",
                "content": {"type": "prompt", "body": "Can you scope this?"},
            },
        },
    }

    event = translator.presence_event_from_agent_session_payload(
        payload,
        delivery_id="delivery-1",
    )

    assert event is not None
    assert event.provider == "linear"
    assert event.event_type == "AgentSessionEvent"
    assert event.action == "prompted"
    assert event.delivery_id == "delivery-1"
    assert event.thread is not None
    assert event.thread.ref.id == "session-1"
    assert event.thread.ref.url == "https://linear.app/session"
    assert event.thread.prompt_context == '<issue identifier="CAO-13"/>'
    assert event.thread.work_item is not None
    assert event.thread.work_item.identifier == "CAO-13"
    assert event.message is not None
    assert event.message.ref is not None
    assert event.message.ref.id == "activity-1"
    assert event.message.kind == "prompt"
    assert event.message.body == "Can you scope this?"


def test_top_level_agent_session_payload_translates_to_presence_event():
    payload = {
        "action": "created",
        "agentSession": {"id": "session-1"},
        "agentActivity": {"signal": "stop"},
    }

    event = translator.presence_event_from_agent_session_payload(
        payload,
        header_event="AgentSessionEvent",
    )

    assert event is not None
    assert event.thread is not None
    assert event.thread.ref.id == "session-1"
    assert event.message is not None
    assert event.message.kind == "stop"


def test_non_agent_session_payload_does_not_translate():
    event = translator.presence_event_from_agent_session_payload({"type": "Issue"})

    assert event is None


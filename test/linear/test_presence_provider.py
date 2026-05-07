"""Tests for the Linear PresenceProvider adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider
from cli_agent_orchestrator.presence.manager import PresenceProviderManager
from cli_agent_orchestrator.presence.inbox_read_presentation import (
    INBOX_READ_PRESENTATION_METADATA_KEY,
)
from cli_agent_orchestrator.presence.models import ExternalRef
from cli_agent_orchestrator.presence.persistence import (
    get_message,
    get_processed_event,
    get_thread,
    get_work_item,
)


def _test_session(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=engine))


def _nested_payload() -> Dict[str, Any]:
    return {
        "type": "AgentSessionEvent",
        "action": "prompted",
        "data": {
            "promptContext": '<issue identifier="CAO-13"/>',
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


def test_nested_agent_session_payload_normalizes_to_presence_event():
    event = LinearPresenceProvider().normalize_event(_nested_payload(), delivery_id="delivery-1")

    assert event is not None
    assert event.provider == "linear"
    assert event.event_type == "AgentSessionEvent"
    assert event.action == "prompted"
    assert event.delivery_id == "delivery-1"
    assert event.thread is not None
    assert event.thread.ref == ExternalRef(
        provider="linear",
        id="session-1",
        url="https://linear.app/session",
    )
    assert event.thread.prompt_context == '<issue identifier="CAO-13"/>'
    assert event.thread.work_item is not None
    assert event.thread.work_item.ref == ExternalRef(
        provider="linear",
        id="issue-1",
        url="https://linear.app/issue",
    )
    assert event.thread.work_item.identifier == "CAO-13"
    assert event.thread.work_item.title == "Discovery smoke"
    assert event.message is not None
    assert event.message.ref == ExternalRef(provider="linear", id="activity-1")
    assert event.message.kind == "prompt"
    assert event.message.body == "Can you scope this?"
    assert event.message.metadata == {
        INBOX_READ_PRESENTATION_METADATA_KEY: {
            "workspace": {
                "name": "Linear",
                "breadcrumb": {
                    "agent_session_id": "session-1",
                    "issue": "CAO-13",
                },
            },
            "source_label": "Linear",
            "context": {"linear_prompt_context": '<issue identifier="CAO-13"/>'},
        }
    }


def test_payload_provider_like_fields_do_not_control_primary_ref_ownership():
    payload = _nested_payload()
    payload["provider"] = "github"
    payload["data"]["provider"] = "slack"
    payload["data"]["agentSession"]["provider"] = "jira"
    payload["data"]["agentSession"]["issue"]["provider"] = "asana"
    payload["data"]["agentActivity"]["provider"] = "not-linear"

    event = LinearPresenceProvider().normalize_event(payload)

    assert event is not None
    assert event.provider == "linear"
    assert event.thread is not None
    assert event.thread.ref.provider == "linear"
    assert event.thread.work_item is not None
    assert event.thread.work_item.ref.provider == "linear"
    assert event.message is not None
    assert event.message.ref is not None
    assert event.message.ref.provider == "linear"


def test_top_level_payload_and_header_event_normalize():
    payload = {
        "action": "created",
        "agentSession": {
            "id": "session-1",
            "url": "https://linear.app/session",
            "issue": {"id": "issue-1", "identifier": "CAO-13", "title": "Discovery smoke"},
        },
        "agentActivity": {"id": "activity-1", "signal": "stop"},
    }

    event = LinearPresenceProvider().normalize_event(payload, header_event="AgentSessionEvent")

    assert event is not None
    assert event.thread is not None
    assert event.thread.ref.id == "session-1"
    assert event.thread.work_item is not None
    assert event.thread.work_item.identifier == "CAO-13"
    assert event.message is not None
    assert event.message.kind == "stop"


def test_non_agent_session_payload_returns_none():
    assert LinearPresenceProvider().normalize_event({"type": "Issue"}) is None


def test_missing_session_id_does_not_invent_thread_id():
    payload = {
        "type": "AgentSessionEvent",
        "agentSession": {"url": "https://linear.app/session"},
        "agentActivity": {"id": "activity-1", "body": "Still observable"},
    }

    event = LinearPresenceProvider().normalize_event(payload)

    assert event is not None
    assert event.thread is None
    assert event.message is not None
    assert event.message.ref == ExternalRef(provider="linear", id="activity-1")


def test_created_payload_with_prompt_context_but_no_activity_creates_replyable_message():
    payload = {
        "type": "AgentSessionEvent",
        "action": "created",
        "data": {
            "promptContext": '<issue identifier="CAO-29"><title>Route me</title></issue>',
            "agentSession": {
                "id": "session-context-only",
                "issue": {"id": "issue-29", "identifier": "CAO-29"},
            },
        },
    }

    event = LinearPresenceProvider().normalize_event(payload, delivery_id="delivery-context")

    assert event is not None
    assert event.thread is not None
    assert event.thread.prompt_context == (
        '<issue identifier="CAO-29"><title>Route me</title></issue>'
    )
    assert event.message is not None
    assert event.message.ref == ExternalRef(
        provider="linear",
        id="agent-session:session-context-only:prompt-context",
    )
    assert event.message.body == "Linear started an AgentSession with prompt context."
    assert event.message.metadata[INBOX_READ_PRESENTATION_METADATA_KEY]["context"] == {
        "linear_prompt_context": '<issue identifier="CAO-29"><title>Route me</title></issue>'
    }


def test_linear_prompt_context_metadata_is_bounded_while_thread_keeps_full_context():
    prompt_context = "<issue>Current scope</issue>\n" + ("prior comment " * 800)
    payload = {
        "type": "AgentSessionEvent",
        "action": "created",
        "data": {
            "promptContext": prompt_context,
            "agentSession": {"id": "session-long-context"},
        },
    }

    event = LinearPresenceProvider().normalize_event(payload)

    assert event is not None
    assert event.thread is not None
    assert event.thread.prompt_context == prompt_context
    assert event.message is not None
    assert event.message.body == "Linear started an AgentSession with prompt context."
    assert "prior comment" not in event.message.body
    context = event.message.metadata[INBOX_READ_PRESENTATION_METADATA_KEY]["context"]
    assert context["linear_prompt_context"].startswith("<issue>Current scope</issue>")
    assert len(context["linear_prompt_context"]) <= 3500
    assert context["linear_prompt_context"].endswith("...")


def test_activity_body_extraction_supports_top_level_and_nested_content():
    top_level = {
        "type": "AgentSessionEvent",
        "agentSession": {"id": "session-1"},
        "agentActivity": {"id": "activity-1", "type": "prompt", "body": "Top body"},
    }
    nested = {
        "type": "AgentSessionEvent",
        "agentSession": {"id": "session-1"},
        "agentActivity": {
            "id": "activity-2",
            "content": {"type": "response", "body": "Nested body"},
        },
    }

    assert LinearPresenceProvider().normalize_event(top_level).message.body == "Top body"
    assert LinearPresenceProvider().normalize_event(nested).message.body == "Nested body"


@pytest.mark.parametrize(
    ("activity", "expected_kind"),
    [
        ({"content": {"type": "prompt"}}, "prompt"),
        ({"content": {"type": "thought"}}, "thought"),
        ({"content": {"type": "response"}}, "response"),
        ({"content": {"type": "elicitation"}}, "elicitation"),
        ({"content": {"type": "error"}}, "error"),
        ({"content": {"type": "stop"}}, "stop"),
        ({"signal": "stop"}, "stop"),
        ({"content": {"type": "surprise"}}, "unknown"),
        ({}, "unknown"),
    ],
)
def test_activity_kind_mapping_covers_known_stop_and_unknown(activity, expected_kind):
    payload = {
        "type": "AgentSessionEvent",
        "agentSession": {"id": "session-1"},
        "agentActivity": {"id": "activity-1", **activity},
    }

    event = LinearPresenceProvider().normalize_event(payload)

    assert event is not None
    assert event.message is not None
    assert event.message.kind == expected_kind


def test_manager_ingestion_persists_linear_event_idempotently(monkeypatch):
    _test_session(monkeypatch)
    manager = PresenceProviderManager({"linear": LinearPresenceProvider()})

    first = manager.ingest_event("linear", _nested_payload(), delivery_id="delivery-1")
    second = manager.ingest_event("linear", _nested_payload(), delivery_id="delivery-1")

    assert first is not None
    assert first.work_item is not None
    assert first.thread is not None
    assert first.message is not None
    assert second is not None
    assert second.work_item is None
    assert second.thread is None
    assert second.message is None
    assert get_work_item("linear", "issue-1").identifier == "CAO-13"
    assert get_thread("linear", "session-1").external_url == "https://linear.app/session"
    assert get_message("linear", "activity-1").body == "Can you scope this?"
    assert get_processed_event("linear", "delivery-1").event_type == "AgentSessionEvent"


def test_reply_to_thread_posts_expected_agent_activity_content():
    create_activity = Mock(return_value={"id": "reply-1"})
    client = Mock(
        create_agent_activity=create_activity,
    )
    provider = LinearPresenceProvider(client=client)

    reply = provider.reply_to_thread(
        ExternalRef(provider="linear", id="session-1"),
        "Done reading this.",
    )

    create_activity.assert_called_once_with(
        "session-1",
        {"type": "response", "body": "Done reading this."},
        app_key=None,
    )
    assert reply.ref == ExternalRef(provider="linear", id="reply-1")
    assert reply.direction == "outbound"
    assert reply.state == "delivered"


def test_reply_to_thread_rejects_non_linear_thread_ref():
    provider = LinearPresenceProvider(client=Mock())

    with pytest.raises(ValueError, match="cannot handle ref for provider github"):
        provider.reply_to_thread(ExternalRef(provider="github", id="thread-1"), "Nope")


def test_acknowledge_stop_creates_supported_acknowledgement():
    client = Mock(create_agent_activity=Mock(return_value={"id": "ack-1"}))
    provider = LinearPresenceProvider(client=client)

    ack = provider.acknowledge_stop(ExternalRef(provider="linear", id="session-1"))

    assert ack.supported is True
    assert ack.message is not None
    assert ack.message.ref == ExternalRef(provider="linear", id="ack-1")
    client.create_agent_activity.assert_called_once_with(
        "session-1",
        {"type": "response", "body": "CAO received the stop request."},
        app_key=None,
    )


def test_reply_to_thread_uses_app_key_from_provider_reply_metadata():
    create_activity = Mock(return_value={"id": "reply-1"})
    provider = LinearPresenceProvider(client=Mock(create_agent_activity=create_activity))

    provider.reply_to_thread(
        ExternalRef(provider="linear", id="session-1"),
        "Reply as mapped app.",
        metadata={"thread_raw_snapshot": {"_cao_linear_app_key": "implementation_partner"}},
    )

    create_activity.assert_called_once_with(
        "session-1",
        {"type": "response", "body": "Reply as mapped app."},
        app_key="implementation_partner",
    )


def test_linear_provider_authors_inbox_read_presentation_from_session_and_activity():
    payload = _nested_payload()
    payload["data"]["agentActivity"]["actor"] = {"name": "  Implementation   Partner  "}

    event = LinearPresenceProvider().normalize_event(payload)

    assert event is not None
    assert event.message is not None
    assert event.message.metadata == {
        INBOX_READ_PRESENTATION_METADATA_KEY: {
            "workspace": {
                "name": "Linear",
                "breadcrumb": {
                    "agent_session_id": "session-1",
                    "issue": "CAO-13",
                },
            },
            "source_label": "Implementation Partner",
            "context": {"linear_prompt_context": '<issue identifier="CAO-13"/>'},
        }
    }


def test_fetch_thread_and_messages_translate_app_client_responses():
    client = Mock()
    client.get_agent_session.return_value = {
        "id": "session-1",
        "url": "https://linear.app/session",
        "promptContext": "<issue/>",
        "issue": {"id": "issue-1", "identifier": "CAO-18", "title": "Presence"},
    }
    client.list_agent_session_activities.return_value = [
        {"id": "activity-1", "content": {"type": "prompt", "body": "Please help"}},
        {"id": "activity-2", "type": "thought", "body": "Thinking"},
    ]
    provider = LinearPresenceProvider(client=client)

    thread = provider.fetch_thread(ExternalRef(provider="linear", id="session-1"))
    messages = provider.fetch_messages(ExternalRef(provider="linear", id="session-1"))

    assert thread.ref == ExternalRef(
        provider="linear",
        id="session-1",
        url="https://linear.app/session",
    )
    assert thread.work_item is not None
    assert thread.work_item.identifier == "CAO-18"
    assert [message.kind for message in messages] == ["prompt", "thought"]
    assert [message.body for message in messages] == ["Please help", "Thinking"]


def test_generic_presence_modules_do_not_import_linear_provider_code():
    root = Path(__file__).parents[2]
    for path in (
        root / "src/cli_agent_orchestrator/presence/models.py",
        root / "src/cli_agent_orchestrator/presence/provider.py",
        root / "src/cli_agent_orchestrator/presence/manager.py",
        root / "src/cli_agent_orchestrator/presence/persistence.py",
        root / "src/cli_agent_orchestrator/presence/refs.py",
    ):
        source = path.read_text()
        assert "cli_agent_orchestrator.linear" not in source
        assert "LinearPresenceProvider" not in source

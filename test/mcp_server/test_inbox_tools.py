"""Tests for CAO MCP inbox read/reply tools."""

from __future__ import annotations

from typing import Any, List, Mapping, Optional
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base, create_inbox_message
from cli_agent_orchestrator.mcp_server.server import (
    _read_inbox_message_impl,
    _reply_to_inbox_message_impl,
)
from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider
from cli_agent_orchestrator.presence.inbox_bridge import (
    PRESENCE_INBOX_SOURCE_KIND,
    create_notification_for_message,
)
from cli_agent_orchestrator.presence.manager import presence_provider_manager
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    MessageKind,
    PresenceEvent,
    StopAcknowledgement,
)
from cli_agent_orchestrator.presence.persistence import upsert_message, upsert_thread


@pytest.fixture
def test_session(monkeypatch):
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
    presence_provider_manager.clear_providers()
    yield
    presence_provider_manager.clear_providers()


class FakePresenceProvider:
    name = "example"

    def __init__(self) -> None:
        self.replies: List[dict[str, Any]] = []

    def normalize_event(
        self,
        raw_event: Mapping[str, Any],
        *,
        delivery_id: Optional[str] = None,
    ) -> Optional[PresenceEvent]:
        return None

    def fetch_thread(self, thread_ref: ExternalRef) -> ConversationThread:
        return ConversationThread(ref=thread_ref)

    def fetch_messages(self, thread_ref: ExternalRef) -> List[ConversationMessage]:
        return []

    def reply_to_thread(
        self,
        thread_ref: ExternalRef,
        body: str,
        *,
        kind: MessageKind = "response",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ConversationMessage:
        self.replies.append(
            {"thread_ref": thread_ref, "body": body, "kind": kind, "metadata": metadata}
        )
        return ConversationMessage(
            kind=kind,
            body=body,
            ref=ExternalRef(provider="example", id="reply-1"),
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
        return StopAcknowledgement(thread_ref=thread_ref, supported=False)


def _presence_notification() -> int:
    thread = upsert_thread(
        provider="example",
        external_id="thread-1",
        external_url="https://presence.example/thread-1",
        kind="conversation",
        prompt_context="Full context from provider",
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-1",
        direction="inbound",
        kind="prompt",
        body="Full provider body",
        raw_snapshot={"provider": {"body": "Full provider body", "extra": "metadata"}},
    )
    return create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:example",
    ).inbox_message.id


def _linear_presence_notification() -> int:
    thread = upsert_thread(
        provider="linear",
        external_id="session-1",
        kind="conversation",
        raw_snapshot={"_cao_linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-1",
        direction="inbound",
        kind="prompt",
        body="Linear body",
    )
    return create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:implementation_partner",
    ).inbox_message.id


def test_read_inbox_message_returns_full_provider_context(test_session):
    inbox_id = _presence_notification()

    result = _read_inbox_message_impl(inbox_id)

    assert result["success"] is True
    assert result["provider_context"]["message"]["body"] == "Full provider body"
    assert result["provider_context"]["thread"]["prompt_context"] == "Full context from provider"
    assert result["provider_context"]["message"]["raw_snapshot"]["provider"]["extra"] == (
        "metadata"
    )
    assert result["reply"] == {
        "replyable": True,
        "error": None,
        "tool": "reply_to_inbox_message",
        "inbox_message_id": inbox_id,
    }


def test_reply_to_inbox_message_routes_through_provider_presence_registry(test_session):
    inbox_id = _presence_notification()
    provider = FakePresenceProvider()
    presence_provider_manager.register_provider("example", provider)

    result = _reply_to_inbox_message_impl(inbox_id, "Reply through CAO")

    assert result["success"] is True
    assert result["provider"] == "example"
    assert result["thread_id"] == "thread-1"
    assert result["outbound_message"]["external_id"] == "reply-1"
    assert provider.replies[0]["thread_ref"] == ExternalRef(
        provider="example",
        id="thread-1",
        url="https://presence.example/thread-1",
    )


def test_reply_to_inbox_message_registers_linear_provider_in_mcp_process(
    test_session,
    monkeypatch,
):
    inbox_id = _linear_presence_notification()
    create_activity = Mock(return_value={"id": "reply-1"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.presence.builtins._create_linear_presence_provider",
        lambda: LinearPresenceProvider(client=Mock(create_agent_activity=create_activity)),
    )

    result = _reply_to_inbox_message_impl(inbox_id, "Reply through default Linear provider")

    assert result["success"] is True
    create_activity.assert_called_once_with(
        "session-1",
        {"type": "response", "body": "Reply through default Linear provider"},
        app_key="implementation_partner",
    )


def test_read_and_reply_fail_clearly_for_non_replyable_inbox_message(test_session):
    inbox = create_inbox_message("terminal-a", "terminal-b", "Plain terminal message")

    read_result = _read_inbox_message_impl(inbox.id)
    reply_result = _reply_to_inbox_message_impl(inbox.id, "No provider target")

    assert read_result["success"] is False
    assert read_result["error_type"] == "InboxReadUnsupportedSourceError"
    assert reply_result["success"] is False
    assert reply_result["error_type"] == "PresenceReplyUnsupportedSourceError"


def test_reply_to_inbox_message_surfaces_provider_failure(test_session):
    inbox_id = _presence_notification()

    result = _reply_to_inbox_message_impl(inbox_id, "No registered provider")

    assert result["success"] is False
    assert result["error_type"] == "PresenceReplyDeliveryError"
    assert result["failed_message_state"] == "failed"

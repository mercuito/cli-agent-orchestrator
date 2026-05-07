"""Tests for routing inbox replies back to provider-backed presence threads."""

from __future__ import annotations

from typing import Any, List, Mapping, Optional

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base, create_inbox_delivery
from cli_agent_orchestrator.presence.inbox_bridge import (
    PRESENCE_INBOX_SOURCE_KIND,
    create_notification_for_message,
)
from cli_agent_orchestrator.presence.manager import PresenceProviderManager
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    MessageKind,
    PresenceEvent,
    StopAcknowledgement,
)
from cli_agent_orchestrator.presence.persistence import list_messages, upsert_message, upsert_thread
from cli_agent_orchestrator.presence.reply_service import (
    PresenceReplyDeliveryError,
    PresenceReplyNotFoundError,
    PresenceReplyUnsupportedSourceError,
    reply_to_inbox_message,
)


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
    TestSession = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


class FakePresenceProvider:
    name = "example"

    def __init__(self) -> None:
        self.replies: List[dict[str, Any]] = []
        self.fail_with: Optional[Exception] = None

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
        if self.fail_with is not None:
            raise self.fail_with
        return ConversationMessage(
            kind=kind,
            body=body,
            ref=ExternalRef(provider=self.name, id=f"reply-{len(self.replies)}"),
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


def _presence_inbox_message() -> tuple[int, int]:
    thread = upsert_thread(
        provider="example",
        external_id="thread-1",
        external_url="https://presence.example/thread-1",
        kind="conversation",
    )
    inbound = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-1",
        direction="inbound",
        kind="prompt",
        body="Can you reply?",
    )
    notification = create_notification_for_message(
        presence_message_id=inbound.id,
        receiver_id="terminal-a",
    )
    return notification.delivery.notification.id, inbound.id


def test_successful_reply_resolves_inbox_thread_and_provider_registry(test_session):
    inbox_id, _ = _presence_inbox_message()
    provider = FakePresenceProvider()
    manager = PresenceProviderManager({"example": provider})

    result = reply_to_inbox_message(inbox_id, "I am on it", provider_manager=manager)

    assert result.delivery.notification.id == inbox_id
    assert result.thread.external_id == "thread-1"
    assert result.outbound_message.direction == "outbound"
    assert result.outbound_message.state == "delivered"
    assert result.outbound_message.external_id == "reply-1"
    assert result.outbound_message.metadata == {
        "inbox_notification_id": inbox_id,
        "provider_reply_ref": {
            "provider": "example",
            "id": "reply-1",
            "url": None,
        },
        "reply_status": "delivered",
    }


def test_provider_receives_thread_external_ref_and_body_not_message_ref(test_session):
    inbox_id, inbound_id = _presence_inbox_message()
    provider = FakePresenceProvider()
    manager = PresenceProviderManager({"example": provider})

    reply_to_inbox_message(inbox_id, "Thread-level reply", provider_manager=manager)

    assert provider.replies == [
        {
            "thread_ref": ExternalRef(
                provider="example",
                id="thread-1",
                url="https://presence.example/thread-1",
            ),
            "body": "Thread-level reply",
            "kind": "response",
            "metadata": {"inbox_notification_id": inbox_id},
        }
    ]
    inbound = list_messages(1)[0]
    assert inbound.id == inbound_id
    assert provider.replies[0]["thread_ref"].id != inbound.external_id


def test_successful_provider_response_is_recorded_durably(test_session):
    inbox_id, _ = _presence_inbox_message()
    provider = FakePresenceProvider()
    manager = PresenceProviderManager({"example": provider})

    result = reply_to_inbox_message(inbox_id, "Persist me", provider_manager=manager)

    messages = list_messages(result.thread.id)
    assert [message.direction for message in messages] == ["inbound", "outbound"]
    assert messages[1].id == result.outbound_message.id
    assert messages[1].body == "Persist me"
    assert messages[1].state == "delivered"


def test_provider_error_records_visible_failed_state(test_session):
    inbox_id, _ = _presence_inbox_message()
    provider = FakePresenceProvider()
    provider.fail_with = RuntimeError("provider is down")
    manager = PresenceProviderManager({"example": provider})

    with pytest.raises(PresenceReplyDeliveryError, match="provider reply failed"):
        reply_to_inbox_message(inbox_id, "This will fail", provider_manager=manager)

    failed = list_messages(1)[-1]
    assert failed.direction == "outbound"
    assert failed.state == "failed"
    assert failed.body == "This will fail"
    assert failed.metadata == {
        "error": "provider is down",
        "error_type": "RuntimeError",
        "inbox_notification_id": inbox_id,
        "reply_status": "failed",
    }


def test_unknown_provider_records_visible_failed_state(test_session):
    inbox_id, _ = _presence_inbox_message()
    manager = PresenceProviderManager()

    with pytest.raises(PresenceReplyDeliveryError, match="Unknown presence provider: example"):
        reply_to_inbox_message(inbox_id, "No registered provider", provider_manager=manager)

    failed = list_messages(1)[-1]
    assert failed.direction == "outbound"
    assert failed.state == "failed"
    assert failed.metadata["error_type"] == "UnknownPresenceProviderError"
    assert failed.metadata["error"] == "Unknown presence provider: example"


def test_missing_inbox_id_fails_clearly(test_session):
    with pytest.raises(PresenceReplyNotFoundError, match="inbox notification 999 not found"):
        reply_to_inbox_message(999, "No inbox")


def test_non_presence_source_fails_as_unsupported(test_session):
    delivery = create_inbox_delivery(
        "worker-a",
        "terminal-a",
        "Plain terminal message",
        source_kind="terminal",
        source_id="worker-a",
    )

    with pytest.raises(
        PresenceReplyUnsupportedSourceError,
        match="route_kind None is not supported",
    ):
        reply_to_inbox_message(delivery.notification.id, "No presence target")


def test_missing_presence_thread_source_fails_clearly(test_session):
    delivery = create_inbox_delivery(
        "presence",
        "terminal-a",
        "Presence update",
        source_kind=PRESENCE_INBOX_SOURCE_KIND,
        source_id="999",
        route_kind=PRESENCE_INBOX_SOURCE_KIND,
        route_id="999",
    )

    with pytest.raises(
        PresenceReplyNotFoundError,
        match=f"presence thread 999 for inbox notification {delivery.notification.id} not found",
    ):
        reply_to_inbox_message(delivery.notification.id, "No durable thread")

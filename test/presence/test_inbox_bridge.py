"""Tests for bridging provider-neutral presence messages into the terminal inbox."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.presence.inbox_bridge import (
    PRESENCE_INBOX_ROUTE_KIND,
    PRESENCE_INBOX_SOURCE_KIND,
    create_notification_for_message,
    create_notification_for_persisted_event,
)
from cli_agent_orchestrator.presence.models import PersistedPresenceEvent
from cli_agent_orchestrator.presence.persistence import (
    upsert_message,
    upsert_thread,
    upsert_work_item,
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


def _persist_message(
    *,
    provider: str = "example",
    thread_external_id: str = "thread-1",
    message_external_id: str = "message-1",
    body: str = "Please look at the failing handoff test.",
    metadata: dict | None = None,
    raw_snapshot: dict | None = None,
):
    work_item = upsert_work_item(
        provider=provider,
        external_id=f"work-{thread_external_id}",
        identifier="WORK-123",
        title="Bridge durable presence into inbox",
    )
    thread = upsert_thread(
        provider=provider,
        external_id=thread_external_id,
        work_item_id=work_item.id,
        kind="work_item_discussion",
    )
    message = upsert_message(
        thread_id=thread.id,
        provider=provider,
        external_id=message_external_id,
        direction="inbound",
        kind="comment",
        body=body,
        raw_snapshot=raw_snapshot,
        metadata=metadata,
    )
    return work_item, thread, message


def test_presence_notification_uses_presence_thread_source_and_internal_thread_id(test_session):
    _, thread, message = _persist_message()

    result = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="terminal-a",
    )

    assert result.created is True
    assert result.delivery.message.source_kind == PRESENCE_INBOX_SOURCE_KIND
    assert result.delivery.message.source_id == str(thread.id)
    assert result.delivery.message.source_id != thread.external_id
    assert result.delivery.message.route_kind == PRESENCE_INBOX_ROUTE_KIND
    assert result.delivery.message.route_id == str(thread.id)
    assert result.delivery.notification.receiver_id == "terminal-a"
    assert result.delivery.notification.status == MessageStatus.PENDING


def test_message_backed_notification_body_is_compact_and_message_body_is_durable(test_session):
    _, _, message = _persist_message(
        provider="generic-chat",
        body="The worker is blocked on a missing migration test.",
    )

    result = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="terminal-a",
    )

    assert result.delivery.message is not None
    assert result.delivery.message.body == "The worker is blocked on a missing migration test."

    body = result.delivery.notification.body
    assert "[CAO inbox notification]" in body
    assert f"ID: {result.delivery.notification.id}" in body
    assert "Source: generic-chat" in body
    assert "Issue: WORK-123 - Bridge durable presence into inbox" in body
    assert f"Read: read_inbox_message(notification_id={result.delivery.notification.id})" in body
    assert (
        f"Reply: reply_to_inbox_message(notification_id={result.delivery.notification.id}" in body
    )
    assert "missing migration test" in body


def test_semantic_notification_body_is_bounded(test_session):
    _, _, message = _persist_message(
        body="Latest actionable line. "
        + "older transcript line that should not be copied wholesale " * 20,
    )

    result = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="terminal-a",
        preview_chars=35,
        notification_chars=180,
    )

    assert len(result.delivery.notification.body) <= 180
    assert "Latest actionable line" in result.delivery.notification.body
    assert result.delivery.notification.body.count("older transcript line") <= 1
    assert "older transcript line" in result.delivery.message.body


def test_duplicate_notification_for_same_receiver_and_presence_message_is_idempotent(
    test_session,
):
    _, _, message = _persist_message()

    first = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="terminal-a",
    )
    second = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="terminal-a",
    )

    assert first.created is True
    assert second.created is False
    assert second.delivery.notification.id == first.delivery.notification.id
    assert len(db_module.list_pending_inbox_notifications("terminal-a", limit=10)) == 1
    with db_module.SessionLocal() as session:
        assert session.query(db_module.InboxNotificationModel).count() == 1


def test_persisted_event_wrapper_bridges_its_message(test_session):
    _, thread, message = _persist_message()

    result = create_notification_for_persisted_event(
        PersistedPresenceEvent(processed_event=None, work_item=None, thread=None, message=message),
        receiver_id="terminal-a",
    )

    assert result.created is True
    assert result.delivery.message.source_kind == PRESENCE_INBOX_SOURCE_KIND
    assert result.delivery.message.source_id == str(thread.id)


def test_different_presence_threads_do_not_coalesce_into_same_source(test_session):
    _, first_thread, first_message = _persist_message(
        thread_external_id="thread-1",
        message_external_id="message-1",
    )
    _, second_thread, second_message = _persist_message(
        thread_external_id="thread-2",
        message_external_id="message-2",
    )

    first = create_notification_for_message(
        presence_message_id=first_message.id,
        receiver_id="terminal-a",
    )
    second = create_notification_for_message(
        presence_message_id=second_message.id,
        receiver_id="terminal-a",
    )

    assert first.delivery.message.source_id == str(first_thread.id)
    assert second.delivery.message.source_id == str(second_thread.id)
    assert first.delivery.message.source_id != second.delivery.message.source_id


def test_missing_presence_thread_or_message_fails_clearly(test_session):
    with pytest.raises(ValueError, match="presence message 999 not found"):
        create_notification_for_message(
            presence_message_id=999,
            receiver_id="terminal-a",
        )

    _, _, message = _persist_message()
    with db_module.SessionLocal() as session:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        session.query(db_module.PresenceThreadModel).delete()
        session.commit()

    with pytest.raises(ValueError, match=f"presence thread .* for message {message.id} not found"):
        create_notification_for_message(
            presence_message_id=message.id,
            receiver_id="terminal-a",
        )


def test_attachment_metadata_does_not_block_semantic_message(test_session):
    _, _, message = _persist_message(
        body="Text that should still notify.",
        metadata={"attachments": [{"content_type": "image/png", "name": "trace.png"}]},
    )

    result = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="terminal-a",
    )

    assert result.created is True
    assert result.delivery.message.body == "Text that should still notify."
    assert "Attachment/media metadata present." in result.delivery.notification.body
    assert result.delivery.message.origin == {
        "attachments": [{"content_type": "image/png", "name": "trace.png"}]
    }


def test_semantic_message_origin_does_not_copy_raw_snapshot(test_session):
    _, _, message = _persist_message(
        body="Text that should still notify.",
        raw_snapshot={"author": {"name": "Raw Snapshot Author Should Not Leak"}},
        metadata=None,
    )

    result = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="terminal-a",
    )

    assert result.delivery.message.origin is None


def test_presence_sources_use_existing_inbox_batching_behavior(test_session):
    _, thread, first_message = _persist_message(
        message_external_id="message-1",
        body="First update",
    )
    second_message = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-2",
        kind="comment",
        body="Second update",
    )

    first = create_notification_for_message(
        presence_message_id=first_message.id,
        receiver_id="terminal-a",
    )
    create_notification_for_message(
        presence_message_id=second_message.id,
        receiver_id="terminal-a",
    )

    batch = db_module.list_pending_inbox_deliveries_for_effective_source(
        "terminal-a", first.delivery
    )

    assert [delivery.message.source_kind for delivery in batch] == [
        PRESENCE_INBOX_SOURCE_KIND,
        PRESENCE_INBOX_SOURCE_KIND,
    ]
    assert [delivery.message.source_id for delivery in batch] == [str(thread.id), str(thread.id)]
    assert [delivery.notification.id for delivery in batch] == [1, 2]

"""Tests for bridging provider-neutral presence messages into the terminal inbox."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base, get_inbox_messages
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.presence.inbox_bridge import (
    PRESENCE_INBOX_SOURCE_KIND,
    create_notification_for_persisted_event,
    create_notification_for_message,
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
    assert result.inbox_message.source_kind == PRESENCE_INBOX_SOURCE_KIND
    assert result.inbox_message.source_id == str(thread.id)
    assert result.inbox_message.source_id != thread.external_id
    assert result.inbox_message.receiver_id == "terminal-a"
    assert result.inbox_message.status == MessageStatus.PENDING


def test_notification_body_includes_preview_and_work_context(test_session):
    _, _, message = _persist_message(
        provider="generic-chat",
        body="The worker is blocked on a missing migration test.",
    )

    result = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="terminal-a",
    )

    assert "Presence update from generic-chat" in result.inbox_message.message
    assert "WORK-123 - Bridge durable presence into inbox" in result.inbox_message.message
    assert "Message: comment" in result.inbox_message.message
    assert "missing migration test" in result.inbox_message.message


def test_notification_body_is_bounded_and_does_not_include_transcript_history(test_session):
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

    assert len(result.inbox_message.message) <= 180
    assert "Latest actionable line" in result.inbox_message.message
    assert result.inbox_message.message.count("older transcript line") <= 1


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
    assert second.inbox_message.id == first.inbox_message.id
    assert len(get_inbox_messages("terminal-a", limit=10)) == 1


def test_persisted_event_wrapper_bridges_its_message(test_session):
    _, thread, message = _persist_message()

    result = create_notification_for_persisted_event(
        PersistedPresenceEvent(processed_event=None, work_item=None, thread=None, message=message),
        receiver_id="terminal-a",
    )

    assert result.created is True
    assert result.inbox_message.source_kind == PRESENCE_INBOX_SOURCE_KIND
    assert result.inbox_message.source_id == str(thread.id)


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

    assert first.inbox_message.source_id == str(first_thread.id)
    assert second.inbox_message.source_id == str(second_thread.id)
    assert first.inbox_message.source_id != second.inbox_message.source_id


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


def test_attachment_metadata_does_not_block_text_notification(test_session):
    _, _, message = _persist_message(
        body="Text that should still notify.",
        metadata={"attachments": [{"content_type": "image/png", "name": "trace.png"}]},
    )

    result = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="terminal-a",
    )

    assert result.created is True
    assert "Text that should still notify." in result.inbox_message.message
    assert "Attachment/media metadata present." in result.inbox_message.message


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

    batch = db_module.get_pending_messages_for_effective_source("terminal-a", first.inbox_message)

    assert [message.source_kind for message in batch] == [
        PRESENCE_INBOX_SOURCE_KIND,
        PRESENCE_INBOX_SOURCE_KIND,
    ]
    assert [message.source_id for message in batch] == [str(thread.id), str(thread.id)]
    assert [message.id for message in batch] == [1, 2]

"""Tests for provider-neutral presence persistence."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event as sa_event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    PresenceEvent,
    WorkItem,
)
from cli_agent_orchestrator.presence.persistence import (
    get_message,
    get_processed_event,
    get_thread,
    get_work_item,
    list_messages,
    mark_processed_event,
    persist_presence_event,
    upsert_message,
    upsert_processed_event,
    upsert_thread,
    upsert_work_item,
)


def _test_session(monkeypatch):
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
    return engine


def test_presence_tables_are_registered_without_provider_specific_columns():
    assert "presence_work_items" in Base.metadata.tables
    assert "presence_threads" in Base.metadata.tables
    assert "presence_messages" in Base.metadata.tables
    assert "processed_provider_events" in Base.metadata.tables

    all_columns = set()
    for table_name in (
        "presence_work_items",
        "presence_threads",
        "presence_messages",
        "processed_provider_events",
    ):
        all_columns.update(c.name for c in Base.metadata.tables[table_name].columns)

    assert not any(column.startswith(("linear_", "jira_", "discord_")) for column in all_columns)


def test_presence_migration_creates_tables_on_existing_database(tmp_path, monkeypatch):
    db_path = tmp_path / "existing.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "engine", engine)

    db_module._migrate_ensure_presence_tables()

    table_names = set(inspect(engine).get_table_names())
    assert {
        "presence_work_items",
        "presence_threads",
        "presence_messages",
        "processed_provider_events",
    }.issubset(table_names)


def test_linear_shaped_work_thread_message_and_event_are_upserted_idempotently(monkeypatch):
    _test_session(monkeypatch)

    work_item = upsert_work_item(
        provider="linear",
        external_id="issue-1",
        external_url="https://linear.app/yards/issue/CAO-16",
        identifier="CAO-16",
        title="Presence persistence",
        state="Todo",
        raw_snapshot={"id": "issue-1", "identifier": "CAO-16"},
    )
    updated_work_item = upsert_work_item(
        provider="linear",
        external_id="issue-1",
        external_url="https://linear.app/yards/issue/CAO-16",
        identifier="CAO-16",
        title="Presence persistence updated",
        state="In Progress",
    )

    assert updated_work_item.id == work_item.id
    assert get_work_item("linear", "issue-1").title == "Presence persistence updated"

    thread = upsert_thread(
        provider="linear",
        external_id="agent-session-1",
        external_url="https://linear.app/session/agent-session-1",
        work_item_id=work_item.id,
        kind="conversation",
        state="awaiting_input",
        prompt_context='<issue identifier="CAO-16"/>',
    )
    updated_thread = upsert_thread(
        provider="linear",
        external_id="agent-session-1",
        work_item_id=work_item.id,
        kind="conversation",
        state="active",
    )

    assert updated_thread.id == thread.id
    assert get_thread("linear", "agent-session-1").state == "active"

    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="agent-activity-1",
        direction="inbound",
        kind="prompt",
        body="Can you implement CAO-16?",
        state="received",
    )
    updated_message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="agent-activity-1",
        direction="inbound",
        kind="prompt",
        body="Can you implement CAO-16 with tests?",
        state="acknowledged",
    )

    assert updated_message.id == message.id
    assert get_message("linear", "agent-activity-1").state == "acknowledged"
    assert len(list_messages(thread.id)) == 1

    processed = upsert_processed_event(
        provider="linear",
        external_event_id="delivery-1",
        event_type="AgentSessionEvent",
        metadata={"action": "prompted"},
    )
    repeated = upsert_processed_event(
        provider="linear",
        external_event_id="delivery-1",
        event_type="AgentSessionEvent",
        metadata={"action": "prompted"},
    )

    assert repeated.id == processed.id
    assert get_processed_event("linear", "delivery-1").metadata == {"action": "prompted"}


def test_jira_shaped_issue_discussion_and_comment_fit_same_schema(monkeypatch):
    _test_session(monkeypatch)

    work_item = upsert_work_item(
        provider="jira",
        external_id="10001",
        external_url="https://jira.example/browse/CAO-16",
        identifier="CAO-16",
        title="Presence persistence",
        metadata={"project": "CAO"},
    )
    thread = upsert_thread(
        provider="jira",
        external_id="discussion-10001",
        work_item_id=work_item.id,
        kind="work_item_discussion",
        state="active",
    )
    comment = upsert_message(
        thread_id=thread.id,
        provider="jira",
        external_id="comment-55",
        direction="inbound",
        kind="comment",
        body="Jira comment body",
        raw_snapshot={"id": "comment-55", "body": "Jira comment body"},
    )

    assert work_item.provider == "jira"
    assert thread.kind == "work_item_discussion"
    assert comment.kind == "comment"
    assert get_message("jira", "comment-55").raw_snapshot == {
        "id": "comment-55",
        "body": "Jira comment body",
    }


def test_discord_thread_and_message_fit_without_work_item(monkeypatch):
    _test_session(monkeypatch)

    thread = upsert_thread(
        provider="discord",
        external_id="channel-thread-1",
        kind="channel_thread",
        state="active",
        metadata={"guild_id": "guild-1"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="discord",
        external_id="message-1",
        direction="outbound",
        kind="response",
        body="Posted back to the thread",
        state="delivered",
    )

    assert thread.work_item_id is None
    assert get_thread("discord", "channel-thread-1").metadata == {"guild_id": "guild-1"}
    assert message.state == "delivered"


def test_persist_presence_event_stores_normalized_event_once(monkeypatch):
    _test_session(monkeypatch)
    event = PresenceEvent(
        provider="linear",
        event_type="AgentSessionEvent",
        action="prompted",
        delivery_id="delivery-1",
        thread=ConversationThread(
            ref=ExternalRef(
                provider="linear",
                id="agent-session-1",
                url="https://linear.app/session/agent-session-1",
            ),
            work_item=WorkItem(
                ref=ExternalRef(provider="linear", id="issue-1"),
                identifier="CAO-16",
                title="Presence persistence",
            ),
            prompt_context='<issue identifier="CAO-16"/>',
        ),
        message=ConversationMessage(
            kind="prompt",
            body="Can you implement this?",
            ref=ExternalRef(provider="linear", id="agent-activity-1"),
        ),
        raw_payload={"type": "AgentSessionEvent"},
    )

    first = persist_presence_event(event)
    second = persist_presence_event(event)

    assert first.processed_event is not None
    assert first.work_item is not None
    assert first.thread is not None
    assert first.message is not None
    assert second.processed_event.id == first.processed_event.id
    assert second.work_item is None
    assert len(list_messages(first.thread.id)) == 1


def test_mark_processed_event_reports_first_observation(monkeypatch):
    _test_session(monkeypatch)

    first, first_created = mark_processed_event(
        provider="jira",
        external_event_id="event-1",
        event_type="comment_created",
    )
    second, second_created = mark_processed_event(
        provider="jira",
        external_event_id="event-1",
        event_type="comment_created",
    )

    assert first_created is True
    assert second_created is False
    assert second.id == first.id


def test_duplicate_upserts_update_existing_database_rows(monkeypatch):
    _test_session(monkeypatch)
    with db_module.SessionLocal() as session:
        work_row = db_module.PresenceWorkItemModel(
            provider="linear",
            external_id="issue-1",
            title="old title",
        )
        session.add(work_row)
        session.flush()
        thread_row = db_module.PresenceThreadModel(
            provider="linear",
            external_id="session-1",
            work_item_id=work_row.id,
            kind="conversation",
            state="active",
        )
        session.add(thread_row)
        session.flush()
        message_row = db_module.PresenceMessageModel(
            thread_id=thread_row.id,
            provider="linear",
            external_id="activity-1",
            direction="inbound",
            kind="prompt",
            body="old body",
            state="received",
        )
        event_row = db_module.ProcessedProviderEventModel(
            provider="linear",
            external_event_id="delivery-1",
            event_type="old_event",
        )
        session.add_all([message_row, event_row])
        session.commit()
        work_id = work_row.id
        thread_id = thread_row.id
        message_id = message_row.id
        event_id = event_row.id

    work = upsert_work_item(
        provider="linear",
        external_id="issue-1",
        title="new title",
        state="triaged",
    )
    thread = upsert_thread(
        provider="linear",
        external_id="session-1",
        work_item_id=work.id,
        kind="conversation",
        state="awaiting_input",
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-1",
        direction="inbound",
        kind="response",
        body="new body",
        state="acknowledged",
    )
    processed_event = upsert_processed_event(
        provider="linear",
        external_event_id="delivery-1",
        event_type="AgentSessionEvent",
        metadata={"action": "prompted"},
    )

    assert work.id == work_id
    assert work.title == "new title"
    assert thread.id == thread_id
    assert thread.state == "awaiting_input"
    assert message.id == message_id
    assert message.body == "new body"
    assert processed_event.id == event_id
    assert processed_event.metadata == {"action": "prompted"}
    with db_module.SessionLocal() as session:
        assert session.query(db_module.PresenceWorkItemModel).count() == 1
        assert session.query(db_module.PresenceThreadModel).count() == 1
        assert session.query(db_module.PresenceMessageModel).count() == 1
        assert session.query(db_module.ProcessedProviderEventModel).count() == 1


def test_persist_event_without_delivery_id_still_dedupes_provider_refs(monkeypatch):
    _test_session(monkeypatch)
    event = PresenceEvent(
        provider="linear",
        event_type="AgentSessionEvent",
        action="prompted",
        delivery_id=None,
        thread=ConversationThread(
            ref=ExternalRef(provider="linear", id="session-1"),
            work_item=WorkItem(
                ref=ExternalRef(provider="linear", id="issue-1"),
                identifier="CAO-16",
                title="Presence persistence",
            ),
        ),
        message=ConversationMessage(
            kind="prompt",
            body="Can you implement this?",
            ref=ExternalRef(provider="linear", id="activity-1"),
        ),
    )

    first = persist_presence_event(event)
    second = persist_presence_event(event)

    assert first.processed_event is None
    assert second.processed_event is None
    assert second.work_item.id == first.work_item.id
    assert second.thread.id == first.thread.id
    assert second.message.id == first.message.id
    with db_module.SessionLocal() as session:
        assert session.query(db_module.PresenceWorkItemModel).count() == 1
        assert session.query(db_module.PresenceThreadModel).count() == 1
        assert session.query(db_module.PresenceMessageModel).count() == 1


def test_messages_without_provider_external_id_are_not_deduped(monkeypatch):
    _test_session(monkeypatch)
    thread = upsert_thread(provider="custom", external_id="room-1")

    first = upsert_message(
        thread_id=thread.id,
        provider="custom",
        external_id=None,
        kind="comment",
        body="first anonymous provider message",
    )
    second = upsert_message(
        thread_id=thread.id,
        provider="custom",
        external_id=None,
        kind="comment",
        body="second anonymous provider message",
    )

    assert first.id != second.id
    assert [message.body for message in list_messages(thread.id)] == [
        "first anonymous provider message",
        "second anonymous provider message",
    ]


def test_validation_errors_and_absent_reads(monkeypatch):
    _test_session(monkeypatch)
    thread = upsert_thread(provider="linear", external_id="session-1")

    with pytest.raises(ValueError, match="provider is required"):
        upsert_work_item(provider="", external_id="issue-1")
    with pytest.raises(ValueError, match="external_id is required"):
        upsert_work_item(provider="linear", external_id="")
    with pytest.raises(ValueError, match="external_id is required"):
        upsert_thread(provider="linear", external_id="")
    with pytest.raises(ValueError, match="provider is required"):
        upsert_message(thread_id=thread.id, provider="")
    with pytest.raises(ValueError, match="external_id is required"):
        upsert_processed_event(provider="linear", external_event_id="")
    with pytest.raises(ValueError, match="provider is required"):
        upsert_processed_event(provider="", external_event_id="event-1")
    with pytest.raises(ValueError, match="external_id is required"):
        mark_processed_event(provider="linear", external_event_id="")

    assert get_work_item("linear", "missing-issue") is None
    assert get_thread("linear", "missing-thread") is None
    assert get_message("linear", "missing-message") is None
    assert get_processed_event("linear", "missing-event") is None


def test_foreign_keys_reject_missing_thread_and_cascade_thread_delete(monkeypatch):
    _test_session(monkeypatch)

    with pytest.raises(IntegrityError):
        upsert_message(
            thread_id=999,
            provider="linear",
            external_id="activity-1",
        )

    work_item = upsert_work_item(provider="linear", external_id="issue-1")
    thread = upsert_thread(
        provider="linear",
        external_id="session-1",
        work_item_id=work_item.id,
    )
    upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-2",
    )

    with db_module.SessionLocal() as session:
        row = (
            session.query(db_module.PresenceWorkItemModel)
            .filter(db_module.PresenceWorkItemModel.id == work_item.id)
            .one()
        )
        session.delete(row)
        session.commit()
    assert get_thread("linear", "session-1").work_item_id is None

    with db_module.SessionLocal() as session:
        row = (
            session.query(db_module.PresenceThreadModel)
            .filter(db_module.PresenceThreadModel.id == thread.id)
            .one()
        )
        session.delete(row)
        session.commit()

    with db_module.SessionLocal() as session:
        assert session.query(db_module.PresenceMessageModel).count() == 0


def test_raw_snapshot_and_metadata_round_trip_for_all_presence_records(monkeypatch):
    _test_session(monkeypatch)

    work_item = upsert_work_item(
        provider="jira",
        external_id="10001",
        raw_snapshot={"fields": {"summary": "Presence persistence"}, "labels": ["cao"]},
        metadata={"project": "CAO", "rank": 1},
    )
    thread = upsert_thread(
        provider="jira",
        external_id="discussion-10001",
        work_item_id=work_item.id,
        raw_snapshot={"comments": [{"id": "comment-1"}]},
        metadata={"source": "issue-discussion"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="jira",
        external_id="comment-1",
        raw_snapshot={"author": {"id": "user-1"}, "body": "hello"},
        metadata={"visibility": "public"},
    )
    processed_event = upsert_processed_event(
        provider="jira",
        external_event_id="event-1",
        event_type="comment_created",
        metadata={"webhook": {"delivery": "event-1"}},
    )

    assert get_work_item("jira", "10001").raw_snapshot == {
        "fields": {"summary": "Presence persistence"},
        "labels": ["cao"],
    }
    assert get_work_item("jira", "10001").metadata == {"project": "CAO", "rank": 1}
    assert get_thread("jira", "discussion-10001").raw_snapshot == {
        "comments": [{"id": "comment-1"}]
    }
    assert get_thread("jira", "discussion-10001").metadata == {"source": "issue-discussion"}
    assert get_message("jira", "comment-1").raw_snapshot == {
        "author": {"id": "user-1"},
        "body": "hello",
    }
    assert get_message("jira", "comment-1").metadata == {"visibility": "public"}
    assert message.metadata == {"visibility": "public"}
    assert get_processed_event("jira", "event-1").metadata == {"webhook": {"delivery": "event-1"}}
    assert processed_event.metadata == {"webhook": {"delivery": "event-1"}}

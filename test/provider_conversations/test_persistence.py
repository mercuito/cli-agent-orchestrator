"""Tests for provider-owned conversation/work-item persistence."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.provider_conversations.persistence import (
    get_message,
    get_processed_event,
    get_thread,
    get_thread_by_id,
    get_work_item,
    list_messages,
    mark_processed_event,
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


def test_provider_conversation_tables_are_registered_without_provider_specific_columns():
    assert "provider_work_items" in Base.metadata.tables
    assert "provider_conversation_threads" in Base.metadata.tables
    assert "provider_conversation_messages" in Base.metadata.tables
    assert "processed_provider_events" in Base.metadata.tables

    all_columns = set()
    for table_name in (
        "provider_work_items",
        "provider_conversation_threads",
        "provider_conversation_messages",
        "processed_provider_events",
    ):
        all_columns.update(c.name for c in Base.metadata.tables[table_name].columns)

    assert not any(column.startswith(("linear_", "jira_", "discord_")) for column in all_columns)


def test_provider_conversation_migration_creates_tables_on_existing_database(tmp_path, monkeypatch):
    db_path = tmp_path / "existing.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

    db_module._migrate_ensure_provider_conversation_tables()

    table_names = set(inspect(engine).get_table_names())
    assert {
        "provider_work_items",
        "provider_conversation_threads",
        "provider_conversation_messages",
        "processed_provider_events",
    }.issubset(table_names)


def test_provider_conversation_migration_copies_legacy_presence_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy-presence.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE inbox_notifications (
                id INTEGER NOT NULL,
                receiver_id VARCHAR NOT NULL,
                body TEXT NOT NULL,
                source_kind VARCHAR NOT NULL,
                source_id VARCHAR NOT NULL,
                metadata_json TEXT,
                status VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                delivered_at DATETIME,
                failed_at DATETIME,
                error_detail TEXT,
                PRIMARY KEY (id)
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO inbox_notifications (
                id, receiver_id, body, source_kind, source_id, status, created_at
            )
            VALUES (
                301, 'agent-123', 'Please handle CAO-38', 'linear_issue', 'CAO-38',
                'pending', '2026-05-07 12:00:00'
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE presence_work_items (
                id INTEGER NOT NULL,
                provider VARCHAR NOT NULL,
                external_id VARCHAR NOT NULL,
                external_url VARCHAR,
                identifier VARCHAR,
                title VARCHAR,
                state VARCHAR,
                raw_snapshot_json TEXT,
                metadata_json TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (provider, external_id)
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO presence_work_items (
                id, provider, external_id, external_url, identifier, title, state,
                raw_snapshot_json, metadata_json, created_at, updated_at
            )
            VALUES (
                401, 'linear', 'issue-1', 'https://linear.example/CAO-38', 'CAO-38',
                'Legacy planning issue', 'Todo', '{"id": "issue-1"}', '{"team": "CAO"}',
                '2026-05-07 12:00:00', '2026-05-07 12:00:00'
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE presence_threads (
                id INTEGER NOT NULL,
                provider VARCHAR NOT NULL,
                external_id VARCHAR NOT NULL,
                external_url VARCHAR,
                work_item_id INTEGER,
                kind VARCHAR NOT NULL,
                state VARCHAR NOT NULL,
                prompt_context TEXT,
                raw_snapshot_json TEXT,
                metadata_json TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (provider, external_id)
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO presence_threads (
                id, provider, external_id, external_url, work_item_id, kind, state,
                prompt_context, raw_snapshot_json, metadata_json, created_at, updated_at
            )
            VALUES (
                501, 'linear', 'thread-1', 'https://linear.example/thread-1', 401,
                'conversation', 'active', '<issue identifier="CAO-38"/>',
                '{"id": "thread-1"}', '{"app_key": "implementation_partner"}',
                '2026-05-07 12:00:00', '2026-05-07 12:00:00'
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE presence_messages (
                id INTEGER NOT NULL,
                thread_id INTEGER NOT NULL,
                provider VARCHAR NOT NULL,
                external_id VARCHAR,
                direction VARCHAR NOT NULL,
                kind VARCHAR NOT NULL,
                body TEXT,
                state VARCHAR NOT NULL,
                raw_snapshot_json TEXT,
                metadata_json TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (provider, external_id)
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO presence_messages (
                id, thread_id, provider, external_id, direction, kind, body, state,
                raw_snapshot_json, metadata_json, created_at, updated_at
            )
            VALUES (
                601, 501, 'linear', 'message-1', 'inbound', 'prompt',
                'Please handle CAO-38', 'received', '{"id": "message-1"}',
                '{"kind": "prompt"}', '2026-05-07 12:00:00', '2026-05-07 12:00:00'
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE presence_inbox_notifications (
                id INTEGER NOT NULL,
                receiver_id VARCHAR NOT NULL,
                presence_message_id INTEGER NOT NULL,
                inbox_notification_id INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (receiver_id, presence_message_id)
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO presence_inbox_notifications (
                id, receiver_id, presence_message_id, inbox_notification_id, created_at
            )
            VALUES (701, 'agent-123', 601, 301, '2026-05-07 12:00:00')
        """)

    db_module._migrate_ensure_provider_conversation_tables()

    table_names = set(inspect(engine).get_table_names())
    assert {
        "provider_work_items",
        "provider_conversation_threads",
        "provider_conversation_messages",
        "provider_conversation_inbox_notifications",
    }.issubset(table_names)
    assert {
        "presence_work_items",
        "presence_threads",
        "presence_messages",
        "presence_inbox_notifications",
    }.issubset(table_names)
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT title FROM provider_work_items WHERE id = 401"
            ).scalar_one()
            == "Legacy planning issue"
        )
        assert (
            connection.exec_driver_sql(
                "SELECT work_item_id FROM provider_conversation_threads WHERE id = 501"
            ).scalar_one()
            == 401
        )
        assert (
            connection.exec_driver_sql(
                "SELECT thread_id FROM provider_conversation_messages WHERE id = 601"
            ).scalar_one()
            == 501
        )
        assert (
            connection.exec_driver_sql(
                "SELECT provider_message_id FROM provider_conversation_inbox_notifications WHERE id = 701"
            ).scalar_one()
            == 601
        )


def test_linear_shaped_work_thread_message_and_event_are_upserted_idempotently(monkeypatch):
    _test_session(monkeypatch)

    work_item = upsert_work_item(
        provider="linear",
        external_id="issue-1",
        external_url="https://linear.app/yards/issue/CAO-16",
        identifier="CAO-16",
        title="Provider conversation persistence",
        state="Todo",
        raw_snapshot={"id": "issue-1", "identifier": "CAO-16"},
    )
    updated_work_item = upsert_work_item(
        provider="linear",
        external_id="issue-1",
        external_url="https://linear.app/yards/issue/CAO-16",
        identifier="CAO-16",
        title="Provider conversation persistence updated",
        state="In Progress",
    )

    assert updated_work_item.id == work_item.id
    assert get_work_item("linear", "issue-1").title == "Provider conversation persistence updated"

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
    assert get_thread_by_id(thread.id).external_id == "agent-session-1"

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
        title="Provider conversation persistence",
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
        work_row = db_module.ProviderWorkItemModel(
            provider="linear",
            external_id="issue-1",
            title="old title",
        )
        session.add(work_row)
        session.flush()
        thread_row = db_module.ProviderConversationThreadModel(
            provider="linear",
            external_id="session-1",
            work_item_id=work_row.id,
            kind="conversation",
            state="active",
        )
        session.add(thread_row)
        session.flush()
        message_row = db_module.ProviderConversationMessageModel(
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
        assert session.query(db_module.ProviderWorkItemModel).count() == 1
        assert session.query(db_module.ProviderConversationThreadModel).count() == 1
        assert session.query(db_module.ProviderConversationMessageModel).count() == 1
        assert session.query(db_module.ProcessedProviderEventModel).count() == 1


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
            session.query(db_module.ProviderWorkItemModel)
            .filter(db_module.ProviderWorkItemModel.id == work_item.id)
            .one()
        )
        session.delete(row)
        session.commit()
    assert get_thread("linear", "session-1").work_item_id is None

    with db_module.SessionLocal() as session:
        row = (
            session.query(db_module.ProviderConversationThreadModel)
            .filter(db_module.ProviderConversationThreadModel.id == thread.id)
            .one()
        )
        session.delete(row)
        session.commit()

    with db_module.SessionLocal() as session:
        assert session.query(db_module.ProviderConversationMessageModel).count() == 0


def test_raw_snapshot_and_metadata_round_trip_for_all_provider_conversation_records(monkeypatch):
    _test_session(monkeypatch)

    work_item = upsert_work_item(
        provider="jira",
        external_id="10001",
        raw_snapshot={
            "fields": {"summary": "Provider conversation persistence"},
            "labels": ["cao"],
        },
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
        "fields": {"summary": "Provider conversation persistence"},
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

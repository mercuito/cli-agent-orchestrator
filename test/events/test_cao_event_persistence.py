"""Tests for durable typed CAO event persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.events import (
    AgentParticipant,
    CaoCausationId,
    CaoCorrelationId,
    CaoEventDispatcher,
    CaoEventId,
    CaoEventOccurredAt,
    CaoEventSourceId,
    CaoEventSourceRef,
    CaoEventSourceType,
    serialization,
)
from cli_agent_orchestrator.linear.workspace_events import LinearAgentMentionedEvent
from cli_agent_orchestrator.runtime.events import (
    AgentRuntimeLifecycleEvent,
    lifecycle_event,
)

OCCURRED_AT = CaoEventOccurredAt(datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc))
SOURCE = CaoEventSourceRef(
    source_type=CaoEventSourceType("linear"),
    source_id=CaoEventSourceId("msg-1"),
)


def _linear_mentioned_event(
    *,
    event_id: str = "linear:agent_mentioned:event-1",
    occurred_at: CaoEventOccurredAt = OCCURRED_AT,
    participants: tuple[AgentParticipant, ...] | None = None,
) -> LinearAgentMentionedEvent:
    return LinearAgentMentionedEvent(
        event_id=CaoEventId(event_id),
        source=SOURCE,
        occurred_at=occurred_at,
        correlation_id=CaoCorrelationId("session-1"),
        causation_id=CaoCausationId("provider-event-1"),
        event_type="AgentSession",
        app_key="linear-app",
        agent_id="implementation_partner",
        app_user_id="user-1",
        app_user_name="RJ Wilson",
        issue_id="issue-id-1",
        issue_identifier="CAO-96",
        issue_url="https://linear.app/yards-framework/issue/CAO-96/example",
        issue_title="Persist events",
        issue_state="Backlog",
        parent_issue_id="parent-id-1",
        parent_issue_identifier="CAO-89",
        agent_session_id="session-1",
        thread_id="session-1",
        thread_url="https://linear.app/session/1",
        prompt_context="Please implement this.",
        message_id="msg-1",
        message_body="Please implement CAO-96.",
        message_kind="comment",
        message_metadata={"visibility": "public"},
        action="create",
        should_notify_agent=True,
        suppression_reason=None,
        raw_payload={"typed_contract_field": True},
        delivery_id="delivery-1",
        metadata={"classification": "human_mention_or_prompt"},
        agent_participants=(
            participants
            if participants is not None
            else (
                AgentParticipant(
                    agent_identity_id="implementation_partner",
                    role="mentioned",
                ),
            )
        ),
    )


def test_persistent_dispatcher_persists_and_reconstructs_linear_event(
    runtime_inbox_db_session,
) -> None:
    event = _linear_mentioned_event()
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    publication = dispatcher.publish(event)
    record = db_module.get_cao_event(str(event.event_id))

    assert publication.event is event
    assert record is not None
    assert record.event_name == LinearAgentMentionedEvent.event_name
    assert record.source_type == "linear"
    assert record.source_id == "msg-1"
    assert record.correlation_id == "session-1"
    assert record.causation_id == "provider-event-1"
    assert isinstance(record.event, LinearAgentMentionedEvent)
    assert record.event == event


def test_persisted_event_reconstructs_after_serializer_registry_restart(
    runtime_inbox_db_session,
    monkeypatch,
) -> None:
    event = _linear_mentioned_event()
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)
    dispatcher.publish(event)
    monkeypatch.setattr(
        serialization,
        "_DEFAULT_CAO_EVENT_SERIALIZER_REGISTRY",
        serialization.CaoEventSerializerRegistry(),
    )

    record = db_module.get_cao_event(str(event.event_id))

    assert record is not None
    assert isinstance(record.event, LinearAgentMentionedEvent)
    assert record.event == event


def test_runtime_event_persists_and_reconstructs_as_exact_type(runtime_inbox_db_session) -> None:
    event = lifecycle_event(
        agent_identity_id="implementation_partner",
        workspace_context_id="wctx-1",
        action="launch",
        runtime_status="ready",
        terminal_id="terminal-1",
        ready=True,
        fresh=True,
        error=None,
    )
    dispatcher = CaoEventDispatcher((AgentRuntimeLifecycleEvent,), persist_events=True)

    dispatcher.publish(event)

    record = db_module.get_cao_event(str(event.event_id))
    assert record is not None
    assert isinstance(record.event, AgentRuntimeLifecycleEvent)
    assert record.event == event


def test_event_log_queries_common_metadata_paths(runtime_inbox_db_session) -> None:
    first = _linear_mentioned_event(
        event_id="linear:agent_mentioned:first",
        occurred_at=OCCURRED_AT,
    )
    second = _linear_mentioned_event(
        event_id="linear:agent_mentioned:second",
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=1)),
    )
    other = _linear_mentioned_event(
        event_id="linear:agent_mentioned:other",
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=2)),
    )
    other = LinearAgentMentionedEvent(
        **{
            **other.__dict__,
            "source": CaoEventSourceRef(
                source_type=CaoEventSourceType("linear"),
                source_id=CaoEventSourceId("msg-2"),
            ),
            "correlation_id": CaoCorrelationId("session-2"),
            "causation_id": CaoCausationId("provider-event-2"),
        }
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    for event in (second, other, first):
        dispatcher.publish(event)

    assert [
        record.event_id for record in db_module.list_cao_events_by_event_name("agent_mentioned")
    ] == [
        str(first.event_id),
        str(second.event_id),
        str(other.event_id),
    ]
    assert [
        record.event_id
        for record in db_module.list_cao_events_by_source(source_type="linear", source_id="msg-1")
    ] == [
        str(first.event_id),
        str(second.event_id),
    ]
    assert [
        record.event_id for record in db_module.list_cao_events_by_correlation_id("session-1")
    ] == [
        str(first.event_id),
        str(second.event_id),
    ]
    assert [
        record.event_id for record in db_module.list_cao_events_by_causation_id("provider-event-1")
    ] == [
        str(first.event_id),
        str(second.event_id),
    ]


def test_agent_participant_queries_support_broadcasts_without_duplicate_payload_rows(
    runtime_inbox_db_session,
) -> None:
    event = _linear_mentioned_event(
        participants=(
            AgentParticipant(agent_identity_id="implementation_partner", role="mentioned"),
            AgentParticipant(agent_identity_id="reviewer", role="mentioned"),
        )
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    dispatcher.publish(event)
    dispatcher.publish(event)

    partner_records = db_module.list_cao_events_by_agent_identity("implementation_partner")
    reviewer_records = db_module.list_cao_events_by_agent_identity("reviewer")
    with runtime_inbox_db_session() as session:
        canonical_event_count = session.query(db_module.CaoEventModel).count()
        participant_count = session.query(db_module.CaoEventAgentParticipantModel).count()

    assert [record.event_id for record in partner_records] == [str(event.event_id)]
    assert [record.event_id for record in reviewer_records] == [str(event.event_id)]
    assert canonical_event_count == 1
    assert participant_count == 2


def test_duplicate_event_id_does_not_add_participants_from_conflicting_replay(
    runtime_inbox_db_session,
) -> None:
    original = _linear_mentioned_event(
        participants=(
            AgentParticipant(agent_identity_id="implementation_partner", role="mentioned"),
        )
    )
    conflicting_replay = _linear_mentioned_event(
        participants=(AgentParticipant(agent_identity_id="reviewer", role="mentioned"),)
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    dispatcher.publish(original)
    dispatcher.publish(conflicting_replay)

    record = db_module.get_cao_event(str(original.event_id))
    with runtime_inbox_db_session() as session:
        participant_rows = session.query(db_module.CaoEventAgentParticipantModel).all()

    assert record is not None
    assert record.event == original
    assert db_module.list_cao_events_by_agent_identity("reviewer") == ()
    assert [(row.agent_identity_id, row.participant_role) for row in participant_rows] == [
        ("implementation_partner", "mentioned")
    ]


def test_events_without_participants_persist_but_do_not_match_participant_queries(
    runtime_inbox_db_session,
) -> None:
    event = _linear_mentioned_event(participants=())
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    dispatcher.publish(event)

    assert db_module.get_cao_event(str(event.event_id)) is not None
    assert db_module.list_cao_events_by_agent_identity("implementation_partner") == ()


def test_local_dispatchers_remain_non_persistent_by_default(runtime_inbox_db_session) -> None:
    event = _linear_mentioned_event()
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,))

    dispatcher.publish(event)

    assert db_module.get_cao_event(str(event.event_id)) is None


def test_cao_event_migration_creates_event_log_tables(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "existing.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "engine", engine)

    db_module._migrate_ensure_cao_event_tables()
    db_module._migrate_ensure_cao_event_tables()

    table_names = set(inspect(engine).get_table_names())
    assert {"cao_events", "cao_event_agent_participants"}.issubset(table_names)
    participant_columns = {
        column["name"] for column in inspect(engine).get_columns("cao_event_agent_participants")
    }
    participant_indexes = {
        index["name"]: index["column_names"]
        for index in inspect(engine).get_indexes("cao_event_agent_participants")
    }
    assert "occurred_at" in participant_columns
    assert participant_indexes["ix_cao_event_agent_participants_agent_occurred"] == [
        "agent_identity_id",
        "occurred_at",
        "event_id",
    ]


def test_cao_event_migration_updates_legacy_participant_occurrence_index(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "legacy-event-log.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "engine", engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE cao_events (
                event_id VARCHAR NOT NULL,
                event_name VARCHAR NOT NULL,
                event_type_key VARCHAR NOT NULL,
                source_type VARCHAR NOT NULL,
                source_id VARCHAR NOT NULL,
                occurred_at DATETIME NOT NULL,
                correlation_id VARCHAR,
                causation_id VARCHAR,
                event_data_json TEXT NOT NULL,
                PRIMARY KEY (event_id)
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE cao_event_agent_participants (
                id INTEGER NOT NULL,
                event_id VARCHAR NOT NULL,
                agent_identity_id VARCHAR NOT NULL,
                participant_role VARCHAR NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (event_id, agent_identity_id, participant_role)
            )
        """)
        connection.exec_driver_sql("""
            CREATE INDEX ix_cao_event_agent_participants_agent_occurred
            ON cao_event_agent_participants (agent_identity_id, event_id)
        """)
        connection.exec_driver_sql("""
            INSERT INTO cao_events (
                event_id,
                event_name,
                event_type_key,
                source_type,
                source_id,
                occurred_at,
                event_data_json
            )
            VALUES (
                'event-1',
                'agent_mentioned',
                'cli_agent_orchestrator.linear.workspace_events.LinearAgentMentionedEvent',
                'linear',
                'msg-1',
                '2026-05-13 12:00:00',
                '{}'
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO cao_event_agent_participants (
                event_id, agent_identity_id, participant_role
            )
            VALUES ('event-1', 'implementation_partner', 'mentioned')
        """)

    db_module._migrate_ensure_cao_event_tables()

    participant_indexes = {
        index["name"]: index["column_names"]
        for index in inspect(engine).get_indexes("cao_event_agent_participants")
    }
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT occurred_at FROM cao_event_agent_participants WHERE event_id = 'event-1'"
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert participant_indexes["ix_cao_event_agent_participants_agent_occurred"] == [
        "agent_identity_id",
        "occurred_at",
        "event_id",
    ]

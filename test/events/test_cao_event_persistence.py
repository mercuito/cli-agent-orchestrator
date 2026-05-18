"""Tests for durable typed CAO event persistence."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.cao_event_store import (
    CaoEventAgentParticipantModel,
    CaoEventModel,
)
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
    UnknownCaoEventError,
    serialization,
)
from cli_agent_orchestrator.linear.workspace_events import (
    LINEAR_CAO_EVENTS,
    LinearAgentMentionedEvent,
    LinearAgentSessionLifecycleActivityEvent,
    LinearAgentSessionPromptedEvent,
    LinearAgentSessionStopRequestedEvent,
    LinearIssueContextEvent,
    LinearIssueCreatedEvent,
    LinearIssueDelegatedToAgentEvent,
    register_linear_cao_events,
)
from cli_agent_orchestrator.runtime.events import (
    RUNTIME_CAO_EVENTS,
    AgentRuntimeLifecycleEvent,
    AgentRuntimeNotificationAcceptedEvent,
    AgentRuntimeNotificationDeliveryEvent,
    AgentRuntimeWorkspaceContextSwitchEvent,
    RuntimeWorkspaceEvent,
    lifecycle_event,
    notification_accepted_event,
    notification_delivery_event,
    workspace_context_switch_event,
    workspace_runtime_event,
)
from cli_agent_orchestrator.services.agent_timeline import AgentTimelineService

OCCURRED_AT = CaoEventOccurredAt(datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc))
LEGACY_LINEAR_MENTIONED_TYPE_KEY = (
    "cli_agent_orchestrator.linear.workspace_events.LinearAgentMentionedEvent"
)


def _linear_issue_context_kwargs(
    *,
    event_id: str = "linear:agent_mentioned:event-1",
    occurred_at: CaoEventOccurredAt = OCCURRED_AT,
    source_id: str = "msg-1",
    correlation_id: str | None = "session-1",
    causation_id: str | None = "provider-event-1",
    participants: tuple[AgentParticipant, ...] | None = None,
) -> dict[str, object]:
    return {
        "event_id": CaoEventId(event_id),
        "source": CaoEventSourceRef(
            source_type=CaoEventSourceType("linear"),
            source_id=CaoEventSourceId(source_id),
        ),
        "occurred_at": occurred_at,
        "correlation_id": CaoCorrelationId(correlation_id) if correlation_id is not None else None,
        "causation_id": CaoCausationId(causation_id) if causation_id is not None else None,
        "event_type": "AgentSession",
        "app_key": "linear-app",
        "agent_id": "implementation_partner",
        "app_user_id": "user-1",
        "app_user_name": "RJ Wilson",
        "issue_id": "issue-id-1",
        "issue_identifier": "CAO-96",
        "issue_url": "https://linear.app/yards-framework/issue/CAO-96/example",
        "issue_title": "Persist events",
        "issue_state": "Backlog",
        "parent_issue_id": "parent-id-1",
        "parent_issue_identifier": "CAO-89",
        "agent_session_id": "session-1",
        "thread_id": "session-1",
        "thread_url": "https://linear.app/session/1",
        "prompt_context": "Please implement this.",
        "message_id": "msg-1",
        "message_body": "Please implement CAO-96.",
        "message_kind": "comment",
        "message_metadata": {"visibility": "public"},
        "action": "create",
        "should_notify_agent": True,
        "suppression_reason": None,
        "raw_payload": {"typed_contract_field": True},
        "delivery_id": "delivery-1",
        "metadata": {"classification": "human_mention_or_prompt"},
        "agent_participants": (
            participants
            if participants is not None
            else (
                AgentParticipant(
                    agent_id="implementation_partner",
                    role="mentioned",
                ),
            )
        ),
    }


def _linear_mentioned_event(
    *,
    event_id: str = "linear:agent_mentioned:event-1",
    occurred_at: CaoEventOccurredAt = OCCURRED_AT,
    source_id: str = "msg-1",
    correlation_id: str | None = "session-1",
    causation_id: str | None = "provider-event-1",
    participants: tuple[AgentParticipant, ...] | None = None,
) -> LinearAgentMentionedEvent:
    return LinearAgentMentionedEvent(
        **_linear_issue_context_kwargs(
            event_id=event_id,
            occurred_at=occurred_at,
            source_id=source_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            participants=participants,
        )
    )


def _linear_issue_context_event(
    event_type: type[LinearIssueContextEvent],
    *,
    event_name: str,
    participant_role: str,
) -> LinearIssueContextEvent:
    return event_type(
        **_linear_issue_context_kwargs(
            event_id=f"linear:{event_name}:all-events",
            source_id=f"msg-{event_name}",
            participants=(
                AgentParticipant(
                    agent_id="implementation_partner",
                    role=participant_role,
                ),
            ),
        )
    )


def _linear_issue_created_event() -> LinearIssueCreatedEvent:
    return LinearIssueCreatedEvent(
        event_id=CaoEventId("linear:issue_created:all-events"),
        source=CaoEventSourceRef(
            source_type=CaoEventSourceType("linear"),
            source_id=CaoEventSourceId("CAO-100"),
        ),
        occurred_at=OCCURRED_AT,
        correlation_id=CaoCorrelationId("terminal-1"),
        terminal_id="terminal-1",
        agent_id="implementation_partner",
        tool_name="create_issue",
        issue={"identifier": "CAO-100", "title": "All event round trip"},
        delivery_id="delivery-created-1",
        metadata={"hook_name": "linear", "phase": "after"},
        agent_participants=(
            AgentParticipant(
                agent_id="implementation_partner",
                role="created_issue",
            ),
        ),
    )


def _all_registered_event_instances() -> tuple[object, ...]:
    mention = _linear_issue_context_event(
        LinearAgentMentionedEvent,
        event_name="agent_mentioned",
        participant_role="mentioned",
    )
    return (
        mention,
        _linear_issue_context_event(
            LinearIssueDelegatedToAgentEvent,
            event_name="issue_delegated_to_agent",
            participant_role="delegated",
        ),
        _linear_issue_context_event(
            LinearAgentSessionPromptedEvent,
            event_name="agent_session_prompted",
            participant_role="prompted",
        ),
        _linear_issue_context_event(
            LinearAgentSessionLifecycleActivityEvent,
            event_name="agent_session_lifecycle_activity",
            participant_role="lifecycle_activity",
        ),
        _linear_issue_context_event(
            LinearAgentSessionStopRequestedEvent,
            event_name="agent_session_stop_requested",
            participant_role="stop_requested",
        ),
        _linear_issue_created_event(),
        notification_accepted_event(
            agent_id="implementation_partner",
            workspace_context_id="wctx-accepted",
            inbox_notification_id=101,
            inbox_receiver_id="implementation_partner",
            sender_id="sender-1",
            source_kind="linear",
            source_id="msg-accepted",
            causing_event=mention,
        ),
        notification_delivery_event(
            agent_id="implementation_partner",
            workspace_context_id="wctx-delivery",
            inbox_notification_id=102,
            inbox_receiver_id="implementation_partner",
            terminal_id="terminal-delivery",
            runtime_status="ready",
            outcome="delivered",
            attempted=True,
            delivered=True,
            error=None,
            source_kind="linear",
            message_body="Delivered.",
            causing_event=mention,
        ),
        lifecycle_event(
            agent_id="implementation_partner",
            workspace_context_id="wctx-lifecycle",
            action="launch",
            runtime_status="ready",
            terminal_id="terminal-lifecycle",
            ready=True,
            fresh=True,
            error=None,
            causing_event=mention,
        ),
        workspace_context_switch_event(
            agent_id="implementation_partner",
            from_workspace_context_id="wctx-old",
            to_workspace_context_id="wctx-new",
            terminal_id="terminal-switch",
            runtime_status="ready",
            outcome="switched",
            error=None,
            causing_event=mention,
        ),
        workspace_runtime_event(
            workspace_context_id="wctx-workspace",
            action="refresh",
            runtime_status="ready",
            correlation_id=CaoCorrelationId("workspace-refresh-all-events"),
        ),
    )


def test_persistent_dispatcher_persists_and_reconstructs_linear_event(
    runtime_inbox_db_session,
) -> None:
    event = _linear_mentioned_event(
        source_id="msg-1",
        correlation_id="session-1",
        causation_id="provider-event-1",
    )
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
    assert record.event_data["message_body"] == "Please implement CAO-96."
    assert record.event_data["raw_payload"] == {"typed_contract_field": True}
    assert isinstance(record.event, LinearAgentMentionedEvent)
    assert record.event == event


def test_each_registered_cao_event_round_trips_through_kinded_storage(
    runtime_inbox_db_session,
) -> None:
    dispatcher = CaoEventDispatcher((*LINEAR_CAO_EVENTS, *RUNTIME_CAO_EVENTS), persist_events=True)

    for event in _all_registered_event_instances():
        dispatcher.publish(event)
        record = db_module.get_cao_event(str(event.event_id))

        assert record is not None
        assert record.event == event
        assert record.event_data["kind"] == event.kind


def test_new_cao_event_writes_store_kind_without_legacy_discriminator(
    runtime_inbox_db_session,
) -> None:
    event = _linear_mentioned_event()
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    dispatcher.publish(event)

    columns = {
        column["name"]
        for column in inspect(runtime_inbox_db_session.kw["bind"]).get_columns("cao_events")
    }
    with runtime_inbox_db_session() as session:
        row = session.query(CaoEventModel).filter_by(event_id=str(event.event_id)).one()
    assert "kind" in columns
    assert "event_type_key" not in columns
    assert row.kind == "linear.agent_mentioned"


def test_persisted_event_reconstructs_after_serializer_registry_restart_and_registration(
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
    register_linear_cao_events(CaoEventDispatcher())

    record = db_module.get_cao_event(str(event.event_id))

    assert record is not None
    assert isinstance(record.event, LinearAgentMentionedEvent)
    assert record.event == event


def test_persisted_event_requires_explicit_kind_registration_after_registry_restart(
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

    with pytest.raises(UnknownCaoEventError, match="linear.agent_mentioned"):
        db_module.get_cao_event(str(event.event_id))

    register_linear_cao_events(CaoEventDispatcher())
    record = db_module.get_cao_event(str(event.event_id))

    assert record is not None
    assert isinstance(record.event, LinearAgentMentionedEvent)
    assert record.event == event


def test_runtime_event_persists_and_reconstructs_as_exact_type(runtime_inbox_db_session) -> None:
    event = lifecycle_event(
        agent_id="implementation_partner",
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


def test_agent_history_orders_linear_mention_and_runtime_delivery_by_occurrence(
    runtime_inbox_db_session,
) -> None:
    mention = _linear_mentioned_event(
        occurred_at=OCCURRED_AT,
        correlation_id="session-1",
    )
    delivery = replace(
        notification_delivery_event(
            agent_id="implementation_partner",
            workspace_context_id="wctx-1",
            inbox_notification_id=42,
            inbox_receiver_id="implementation_partner",
            terminal_id="terminal-1",
            runtime_status="ready",
            outcome="delivered",
            attempted=True,
            delivered=True,
            error=None,
            causing_event=mention,
        ),
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=1)),
    )
    dispatcher = CaoEventDispatcher(
        (LinearAgentMentionedEvent, AgentRuntimeNotificationDeliveryEvent),
        persist_events=True,
    )

    dispatcher.publish(delivery)
    dispatcher.publish(mention)

    delivery_record = db_module.get_cao_event(str(delivery.event_id))
    assert delivery_record is not None
    assert delivery_record.event == delivery
    assert isinstance(delivery_record.event, AgentRuntimeNotificationDeliveryEvent)
    assert delivery_record.event.agent_participants == (
        AgentParticipant(agent_id="implementation_partner", role="delivery_target"),
    )
    assert [
        record.event_id for record in db_module.list_cao_events_by_agent("implementation_partner")
    ] == [
        str(mention.event_id),
        str(delivery.event_id),
    ]
    assert [
        record.event_id for record in db_module.list_cao_events_by_correlation_id("session-1")
    ] == [
        str(mention.event_id),
        str(delivery.event_id),
    ]
    assert [
        record.event_id
        for record in db_module.list_cao_events_by_causation_id(str(mention.event_id))
    ] == [str(delivery.event_id)]


def test_event_log_queries_common_metadata_paths(runtime_inbox_db_session) -> None:
    first = _linear_mentioned_event(
        event_id="linear:agent_mentioned:first",
        occurred_at=OCCURRED_AT,
        source_id="msg-1",
        correlation_id="session-1",
        causation_id="provider-event-1",
    )
    second = _linear_mentioned_event(
        event_id="linear:agent_mentioned:second",
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=1)),
        source_id="msg-1",
        correlation_id="session-1",
        causation_id="provider-event-1",
    )
    other = _linear_mentioned_event(
        event_id="linear:agent_mentioned:other",
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=2)),
        source_id="msg-2",
        correlation_id="session-2",
        causation_id="provider-event-2",
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
            AgentParticipant(agent_id="implementation_partner", role="mentioned"),
            AgentParticipant(agent_id="reviewer", role="mentioned"),
        )
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    dispatcher.publish(event)
    dispatcher.publish(event)

    partner_records = db_module.list_cao_events_by_agent("implementation_partner")
    reviewer_records = db_module.list_cao_events_by_agent("reviewer")
    with runtime_inbox_db_session() as session:
        canonical_event_count = session.query(CaoEventModel).count()
        participant_rows = (
            session.query(CaoEventAgentParticipantModel)
            .order_by(
                CaoEventAgentParticipantModel.agent_id.asc(),
                CaoEventAgentParticipantModel.participant_role.asc(),
            )
            .all()
        )

    assert [record.event_id for record in partner_records] == [str(event.event_id)]
    assert [record.event_id for record in reviewer_records] == [str(event.event_id)]
    assert canonical_event_count == 1
    assert [(row.event_id, row.agent_id, row.participant_role) for row in participant_rows] == [
        (str(event.event_id), "implementation_partner", "mentioned"),
        (str(event.event_id), "reviewer", "mentioned"),
    ]


def test_agent_history_uses_participant_index_not_typed_body_mentions(
    runtime_inbox_db_session,
) -> None:
    event = _linear_mentioned_event(
        event_id="linear:agent_mentioned:body-only",
        participants=(AgentParticipant(agent_id="reviewer", role="mentioned"),),
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    dispatcher.publish(event)

    assert event.agent_id == "implementation_partner"
    assert db_module.list_cao_events_by_agent("implementation_partner") == ()
    assert [record.event_id for record in db_module.list_cao_events_by_agent("reviewer")] == [
        str(event.event_id)
    ]


def test_agent_timeline_read_exposes_selected_participant_role_from_index(
    runtime_inbox_db_session,
) -> None:
    event = _linear_mentioned_event(
        event_id="linear:agent_mentioned:broadcast-role-proof",
        participants=(
            AgentParticipant(agent_id="implementation_partner", role="mentioned"),
            AgentParticipant(agent_id="reviewer", role="observer"),
        ),
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    dispatcher.publish(event)

    partner_records = db_module.list_cao_event_participants_by_agent("implementation_partner")
    reviewer_records = db_module.list_cao_event_participants_by_agent("reviewer")
    assert [(record.record.event_id, record.participant_role) for record in partner_records] == [
        (str(event.event_id), "mentioned")
    ]
    assert [(record.record.event_id, record.participant_role) for record in reviewer_records] == [
        (str(event.event_id), "observer")
    ]


def test_duplicate_event_id_does_not_add_participants_from_conflicting_replay(
    runtime_inbox_db_session,
) -> None:
    original = _linear_mentioned_event(
        participants=(AgentParticipant(agent_id="implementation_partner", role="mentioned"),)
    )
    conflicting_replay = _linear_mentioned_event(
        participants=(AgentParticipant(agent_id="reviewer", role="mentioned"),)
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    dispatcher.publish(original)
    dispatcher.publish(conflicting_replay)

    record = db_module.get_cao_event(str(original.event_id))
    with runtime_inbox_db_session() as session:
        participant_rows = session.query(CaoEventAgentParticipantModel).all()

    assert record is not None
    assert record.event == original
    assert db_module.list_cao_events_by_agent("reviewer") == ()
    assert [(row.agent_id, row.participant_role) for row in participant_rows] == [
        ("implementation_partner", "mentioned")
    ]


def test_events_without_participants_persist_but_do_not_match_participant_queries(
    runtime_inbox_db_session,
) -> None:
    event = workspace_runtime_event(
        workspace_context_id="wctx-1",
        action="refresh",
        runtime_status="ready",
        correlation_id=CaoCorrelationId("workspace-refresh-1"),
    )
    dispatcher = CaoEventDispatcher((RuntimeWorkspaceEvent,), persist_events=True)

    dispatcher.publish(event)

    record = db_module.get_cao_event(str(event.event_id))
    assert record is not None
    assert isinstance(record.event, RuntimeWorkspaceEvent)
    assert db_module.list_cao_events_by_event_name(RuntimeWorkspaceEvent.event_name) == (record,)
    assert db_module.list_cao_events_by_source(
        source_type="cao_runtime",
        source_id="workspace:wctx-1",
    ) == (record,)
    assert db_module.list_cao_events_by_correlation_id("workspace-refresh-1") == (record,)
    assert db_module.list_cao_events_by_agent("implementation_partner") == ()
    with runtime_inbox_db_session() as session:
        participant_count = (
            session.query(CaoEventAgentParticipantModel)
            .filter(CaoEventAgentParticipantModel.event_id == str(event.event_id))
            .count()
        )
    assert participant_count == 0


def test_event_log_queries_return_empty_results_for_unknown_facts(runtime_inbox_db_session) -> None:
    event = _linear_mentioned_event()
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)

    dispatcher.publish(event)

    assert db_module.get_cao_event("missing-event") is None
    assert db_module.list_cao_events_by_agent("missing-agent") == ()
    assert db_module.list_cao_events_by_event_name("missing-event-name") == ()
    assert (
        db_module.list_cao_events_by_source(source_type="linear", source_id="missing-source") == ()
    )
    assert db_module.list_cao_events_by_correlation_id("missing-correlation") == ()
    assert db_module.list_cao_events_by_causation_id("missing-causation") == ()


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
    event_columns = {column["name"] for column in inspect(engine).get_columns("cao_events")}
    participant_columns = {
        column["name"] for column in inspect(engine).get_columns("cao_event_agent_participants")
    }
    participant_indexes = {
        index["name"]: index["column_names"]
        for index in inspect(engine).get_indexes("cao_event_agent_participants")
    }
    assert "kind" in event_columns
    assert "event_type_key" not in event_columns
    assert "occurred_at" in participant_columns
    assert participant_indexes["ix_cao_event_agent_participants_agent_occurred"] == [
        "agent_id",
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
                agent_id VARCHAR NOT NULL,
                participant_role VARCHAR NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (event_id, agent_id, participant_role)
            )
        """)
        connection.exec_driver_sql("""
            CREATE INDEX ix_cao_event_agent_participants_agent_occurred
            ON cao_event_agent_participants (agent_id, event_id)
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
                event_id, agent_id, participant_role
            )
            VALUES ('event-1', 'implementation_partner', 'mentioned')
        """)

    db_module._migrate_ensure_cao_event_tables()

    participant_indexes = {
        index["name"]: index["column_names"]
        for index in inspect(engine).get_indexes("cao_event_agent_participants")
    }
    event_columns = {column["name"] for column in inspect(engine).get_columns("cao_events")}
    with engine.connect() as connection:
        participant_row = connection.exec_driver_sql("""
            SELECT occurred_at
            FROM cao_event_agent_participants
            WHERE event_id = 'event-1'
            """).fetchone()
        event_row = connection.exec_driver_sql(
            "SELECT kind FROM cao_events WHERE event_id = 'event-1'"
        ).fetchone()
    assert participant_row is not None
    assert participant_row[0] is not None
    assert event_row == ("linear.agent_mentioned",)
    assert "event_type_key" not in event_columns
    assert participant_indexes["ix_cao_event_agent_participants_agent_occurred"] == [
        "agent_id",
        "occurred_at",
        "event_id",
    ]


def test_cao_event_migration_backfills_kind_and_reconstructs_legacy_rows(
    tmp_path,
    monkeypatch,
    agent_manager_factory,
    implementation_partner_agent_factory,
) -> None:
    control = _linear_mentioned_event(event_id="linear:agent_mentioned:legacy-migration")
    register_linear_cao_events(CaoEventDispatcher())
    _, event_data_json = serialization.serialize_cao_event(control)
    legacy_payload = json.loads(event_data_json)
    legacy_payload.pop("kind", None)
    db_path = tmp_path / "legacy-kind-read-path.db"
    engine = create_engine(f"sqlite:///{db_path}")
    test_session = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", test_session)
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
                agent_id VARCHAR NOT NULL,
                participant_role VARCHAR NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (event_id, agent_id, participant_role)
            )
        """)
        connection.exec_driver_sql(
            """
            INSERT INTO cao_events (
                event_id,
                event_name,
                event_type_key,
                source_type,
                source_id,
                occurred_at,
                correlation_id,
                causation_id,
                event_data_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(control.event_id),
                control.event_name,
                LEGACY_LINEAR_MENTIONED_TYPE_KEY,
                str(control.source.source_type),
                str(control.source.source_id),
                control.occurred_at,
                str(control.correlation_id),
                str(control.causation_id),
                json.dumps(legacy_payload, sort_keys=True, separators=(",", ":")),
            ),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO cao_event_agent_participants (
                event_id, agent_id, participant_role
            )
            VALUES (?, ?, ?)
            """,
            (str(control.event_id), "implementation_partner", "mentioned"),
        )

    db_module._migrate_ensure_cao_event_tables()
    register_linear_cao_events(CaoEventDispatcher())
    manager = agent_manager_factory(implementation_partner_agent_factory())
    timeline = AgentTimelineService(manager)

    record = db_module.get_cao_event(str(control.event_id))
    agent_records = db_module.list_cao_events_by_agent("implementation_partner")
    event_name_records = db_module.list_cao_events_by_event_name(control.event_name)
    source_records = db_module.list_cao_events_by_source(
        source_type=str(control.source.source_type),
        source_id=str(control.source.source_id),
    )
    correlation_records = db_module.list_cao_events_by_correlation_id(str(control.correlation_id))
    causation_records = db_module.list_cao_events_by_causation_id(str(control.causation_id))
    timeline_read = timeline.timeline_for_agent("implementation_partner")

    assert record is not None
    assert isinstance(record.event, LinearAgentMentionedEvent)
    assert record.event == control
    assert agent_records == (record,)
    assert event_name_records == (record,)
    assert source_records == (record,)
    assert correlation_records == (record,)
    assert causation_records == (record,)
    assert [event.event_id for event in timeline_read.events] == [str(control.event_id)]
    assert timeline_read.events[0].event_type_key == LEGACY_LINEAR_MENTIONED_TYPE_KEY

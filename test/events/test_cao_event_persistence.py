"""Tests for durable typed CAO event persistence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.events import CaoEventDispatcher, CaoEventOccurredAt
from cli_agent_orchestrator.runtime.events import (
    AgentRuntimeNotificationDeliveryEvent,
    RuntimeWorkspaceEvent,
    notification_delivery_event,
    workspace_runtime_event,
)

OCCURRED_AT = CaoEventOccurredAt(datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc))


def test_runtime_event_persistence_round_trips_typed_payload(runtime_inbox_db_session) -> None:
    event = notification_delivery_event(
        agent_id="implementation_partner",
        workspace_context_id="wctx-1",
        inbox_notification_id=42,
        receiver_agent_id="implementation_partner",
        terminal_id="terminal-1",
        runtime_status="idle",
        outcome="delivered",
        attempted=True,
        delivered=True,
        error=None,
        message_body="Please review this.",
    )
    event = replace(event, occurred_at=OCCURRED_AT)

    CaoEventDispatcher((AgentRuntimeNotificationDeliveryEvent,), persist_events=True).publish(event)

    record = db_module.get_cao_event(str(event.event_id))
    assert record is not None
    assert record.event_type_key == (
        "cli_agent_orchestrator.runtime.events.AgentRuntimeNotificationDeliveryEvent"
    )
    assert record.event_data["message_body"] == "Please review this."
    participant = db_module.list_cao_event_participants_by_agent("implementation_partner")[0]
    assert participant.record.event_id == str(event.event_id)


def test_agent_timeline_indexes_runtime_agent_participants(runtime_inbox_db_session) -> None:
    delivery = replace(
        notification_delivery_event(
            agent_id="implementation_partner",
            workspace_context_id="wctx-1",
            inbox_notification_id=42,
            receiver_agent_id="implementation_partner",
            terminal_id="terminal-1",
            runtime_status="idle",
            outcome="delivered",
            attempted=True,
            delivered=True,
            error=None,
            message_body="Please review this.",
        ),
        occurred_at=OCCURRED_AT,
    )
    workspace = replace(
        workspace_runtime_event(
            workspace_context_id="wctx-1",
            action="refresh",
            runtime_status="idle",
        ),
        occurred_at=OCCURRED_AT,
    )
    dispatcher = CaoEventDispatcher(
        (AgentRuntimeNotificationDeliveryEvent, RuntimeWorkspaceEvent),
        persist_events=True,
    )
    dispatcher.publish(workspace)
    dispatcher.publish(delivery)

    reads = db_module.list_cao_event_participants_by_agent("implementation_partner")

    assert [read.record.event_id for read in reads] == [str(delivery.event_id)]
    assert reads[0].participant_role == "delivery_target"
    assert reads[0].record.event_data["message_body"] == "Please review this."


def test_cao_event_migration_rejects_unmapped_legacy_type_key(tmp_path, monkeypatch) -> None:
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
                'removed_legacy_event',
                'removed.provider.LegacyEvent',
                'removed_provider',
                'msg-1',
                '2026-05-13 12:00:00',
                '{}'
            )
        """)

    with pytest.raises(ValueError, match="Unresolved legacy CAO event type keys"):
        db_module._migrate_ensure_cao_event_tables()

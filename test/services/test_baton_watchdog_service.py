"""Tests for baton watchdog nudges and orphan recovery."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base, BatonEventModel, BatonModel
from cli_agent_orchestrator.models.baton import BatonStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.services import baton_service, baton_watchdog_service, inbox_service


@pytest.fixture
def patched_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def _config(*, grace_seconds=1, rate_limit_seconds=60):
    return baton_watchdog_service.BatonWatchdogConfig(
        interval_seconds=0.01,
        grace_seconds=grace_seconds,
        nudge_rate_limit_seconds=rate_limit_seconds,
    )


def _create_terminal(terminal_id: str):
    db_module.create_terminal(
        terminal_id=terminal_id,
        tmux_session="cao-test",
        tmux_window=terminal_id,
        provider="codex",
    )


def _provider(status: TerminalStatus):
    provider = MagicMock()
    provider.get_status.return_value = status
    return provider


def _messages(receiver_id: str):
    return db_module.list_pending_inbox_notifications(receiver_id, limit=50)


def _events(baton_id: str):
    return db_module.list_baton_events(baton_id)


@pytest.mark.parametrize("status", [TerminalStatus.IDLE, TerminalStatus.COMPLETED])
def test_idle_or_completed_holder_receives_nudge_after_grace(patched_db, monkeypatch, status):
    _create_terminal("impl")
    provider = _provider(status)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
        expected_next_action="run the review loop",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now() + timedelta(seconds=5),
    )

    assert result.scanned == 1
    assert result.nudged == 1
    baton = db_module.get_baton_record("baton-1")
    assert baton.status == BatonStatus.ACTIVE.value
    assert baton.current_holder_id == "impl"
    assert baton.last_nudged_at is not None
    assert [event.event_type for event in _events("baton-1")] == ["create", "nudge"]
    queued = _messages("impl")
    assert len(queued) == 2
    assert queued[-1].message.sender_id == baton_watchdog_service.WATCHDOG_ACTOR_ID
    assert "Baton id: baton-1" in queued[-1].message.body
    assert "Title: T05" in queued[-1].message.body
    assert "Expected next action: run the review loop" in queued[-1].message.body
    assert "If you are waiting on another agent to make the next move" in queued[-1].message.body
    assert "pass the baton to that agent with pass_baton" in queued[-1].message.body
    assert "Idle detection is advisory" in queued[-1].message.body
    assert "pass_baton" in queued[-1].message.body
    assert "return_baton" in queued[-1].message.body
    assert "complete_baton" in queued[-1].message.body
    assert "block_baton" in queued[-1].message.body


def test_processing_holder_is_not_nudged(patched_db, monkeypatch):
    _create_terminal("impl")
    provider = _provider(TerminalStatus.PROCESSING)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now() + timedelta(seconds=5),
    )

    assert result.scanned == 1
    assert result.nudged == 0
    assert [event.event_type for event in _events("baton-1")] == ["create"]
    assert len(_messages("impl")) == 1


def test_nudges_are_rate_limited_by_last_nudged_at(patched_db, monkeypatch):
    _create_terminal("impl")
    provider = _provider(TerminalStatus.IDLE)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )
    first_scan_at = datetime.now() + timedelta(seconds=5)

    first = baton_watchdog_service.scan_active_batons(
        config=_config(grace_seconds=0, rate_limit_seconds=60),
        now=first_scan_at,
    )
    second = baton_watchdog_service.scan_active_batons(
        config=_config(grace_seconds=0, rate_limit_seconds=60),
        now=first_scan_at + timedelta(seconds=10),
    )

    assert first.nudged == 1
    assert second.nudged == 0
    assert [event.event_type for event in _events("baton-1")] == ["create", "nudge"]
    assert len(_messages("impl")) == 2


def test_watchdog_nudge_notification_delivers_through_semantic_inbox(
    patched_db,
    monkeypatch,
):
    _create_terminal("impl")
    provider = _provider(TerminalStatus.IDLE)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )
    baton_watchdog_service.scan_active_batons(
        config=_config(grace_seconds=0),
        now=datetime.now() + timedelta(seconds=5),
    )
    queued = _messages("impl")
    sent = []
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.inbox_service.terminal_service.send_input",
        lambda terminal_id, message: sent.append((terminal_id, message)),
    )

    assert inbox_service.check_and_send_pending_messages("impl") is True
    assert inbox_service.check_and_send_pending_messages("impl") is True

    delivered = db_module.get_inbox_delivery(queued[-1].notification.id)
    assert delivered is not None
    assert delivered.notification.status.value == "delivered"
    assert "Gentle reminder" in sent[-1][1]


def test_missing_holder_metadata_marks_baton_orphaned_and_notifies_originator(
    patched_db, monkeypatch
):
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: None,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="missing",
        expected_next_action="finish T05",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now(),
    )

    assert result.scanned == 1
    assert result.orphaned == 1
    baton = db_module.get_baton_record("baton-1")
    assert baton.status == BatonStatus.ORPHANED.value
    assert baton.current_holder_id is None
    assert [event.event_type for event in _events("baton-1")] == ["create", "orphan"]
    queued = _messages("originator")
    assert len(queued) == 1
    assert queued[0].message.sender_id == baton_watchdog_service.WATCHDOG_ACTOR_ID
    assert "Baton id: baton-1" in queued[0].message.body
    assert "Previous holder: missing" in queued[0].message.body
    assert "marked orphaned" in queued[0].message.body


def test_missing_holder_provider_marks_baton_orphaned_and_notifies_originator(
    patched_db, monkeypatch
):
    _create_terminal("impl")

    def provider_missing(terminal_id: str):
        raise ValueError(f"Provider not found for {terminal_id}")

    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        provider_missing,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now(),
    )

    assert result.orphaned == 1
    baton = db_module.get_baton_record("baton-1")
    assert baton.status == BatonStatus.ORPHANED.value
    assert [event.event_type for event in _events("baton-1")] == ["create", "orphan"]


def test_only_active_batons_are_scanned(patched_db, monkeypatch):
    _create_terminal("impl")
    provider = _provider(TerminalStatus.IDLE)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )
    with patched_db() as db:
        row = db.query(BatonModel).filter(BatonModel.id == "baton-1").one()
        row.status = BatonStatus.BLOCKED.value
        db.add(
            BatonEventModel(
                baton_id="baton-1",
                event_type="block",
                actor_id="impl",
                from_holder_id="impl",
                to_holder_id="originator",
                message="blocked",
                created_at=datetime.now(),
            )
        )
        db.commit()

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now() + timedelta(seconds=5),
    )

    assert result.scanned == 0
    assert result.nudged == 0
    assert len(_messages("impl")) == 1

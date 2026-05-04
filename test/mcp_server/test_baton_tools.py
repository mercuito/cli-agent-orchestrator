"""Tests for baton MCP tool implementations."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.mcp_server import server
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.services import baton_service


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


def _pending(receiver_id):
    return db_module.get_inbox_messages(receiver_id, status=MessageStatus.PENDING)


def test_create_baton_infers_originator_from_cao_terminal_id(patched_db, monkeypatch):
    monkeypatch.setenv("CAO_TERMINAL_ID", "originator")

    result = server._create_baton_impl(
        title="T03",
        holder_id="impl",
        message="Implement the delivery slice",
        expected_next_action="implement",
        artifact_paths=["/tmp/task.md"],
    )

    assert result["success"] is True
    assert result["baton"]["originator_id"] == "originator"
    assert result["baton"]["current_holder_id"] == "impl"
    assert result["status"] == "active"
    queued = _pending("impl")
    assert len(queued) == 1
    assert queued[0].sender_id == "originator"
    assert "Baton id:" in queued[0].message
    assert "Implement the delivery slice" in queued[0].message
    assert "/tmp/task.md" in queued[0].message


def test_baton_tool_requires_cao_terminal_id(patched_db, monkeypatch):
    monkeypatch.delenv("CAO_TERMINAL_ID", raising=False)

    result = server._create_baton_impl(
        title="T03",
        holder_id="impl",
        message="start",
    )

    assert result == {
        "success": False,
        "error_type": "missing_context",
        "error": "CAO_TERMINAL_ID not set - baton tools must run inside a CAO terminal",
    }


def test_pass_baton_non_holder_returns_actionable_error(patched_db, monkeypatch):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T03",
        originator_id="originator",
        holder_id="impl",
    )
    monkeypatch.setenv("CAO_TERMINAL_ID", "reviewer")

    result = server._pass_baton_impl(
        baton_id="baton-1",
        receiver_id="other",
        message="I should not be able to pass this",
    )

    assert result["success"] is False
    assert result["error_type"] == "authorization_error"
    assert "not current holder" in result["error"]


def test_pass_baton_waiting_receiver_returns_invalid_transition(patched_db, monkeypatch):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T03",
        originator_id="originator",
        holder_id="impl",
    )
    baton_service.pass_baton(
        baton_id="baton-1",
        actor_id="impl",
        receiver_id="reviewer",
    )
    monkeypatch.setenv("CAO_TERMINAL_ID", "reviewer")

    result = server._pass_baton_impl(
        baton_id="baton-1",
        receiver_id="impl",
        message="This would form a control loop",
    )

    assert result["success"] is False
    assert result["error_type"] == "invalid_transition"
    assert "impl is waiting for this baton to come back from you" in result["error"]
    assert "return_baton" in result["error"]


def test_get_my_batons_lists_current_holder_with_optional_status(patched_db, monkeypatch):
    baton_service.create_baton(
        baton_id="active-baton",
        title="Active",
        originator_id="originator",
        holder_id="impl",
    )
    baton_service.create_baton(
        baton_id="blocked-baton",
        title="Blocked",
        originator_id="originator",
        holder_id="impl",
    )
    baton_service.block_baton(
        baton_id="blocked-baton",
        actor_id="impl",
        reason="waiting on contract",
    )
    monkeypatch.setenv("CAO_TERMINAL_ID", "impl")

    all_result = server._get_my_batons_impl()
    active_result = server._get_my_batons_impl(status="active")
    blocked_result = server._get_my_batons_impl(status="blocked")

    assert all_result["success"] is True
    assert {baton["id"] for baton in all_result["batons"]} == {
        "active-baton",
        "blocked-baton",
    }
    assert [baton["id"] for baton in active_result["batons"]] == ["active-baton"]
    assert [baton["id"] for baton in blocked_result["batons"]] == ["blocked-baton"]


def test_get_baton_returns_events_for_involved_terminal(patched_db, monkeypatch):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T03",
        originator_id="originator",
        holder_id="impl",
    )
    monkeypatch.setenv("CAO_TERMINAL_ID", "impl")

    result = server._get_baton_impl("baton-1")

    assert result["success"] is True
    assert result["baton"]["id"] == "baton-1"
    assert [event["event_type"] for event in result["events"]] == ["create"]


def test_get_baton_rejects_uninvolved_terminal(patched_db, monkeypatch):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T03",
        originator_id="originator",
        holder_id="impl",
    )
    monkeypatch.setenv("CAO_TERMINAL_ID", "stranger")

    result = server._get_baton_impl("baton-1")

    assert result["success"] is False
    assert result["error_type"] == "authorization_error"


def test_pending_registry_includes_baton_tools():
    names = {name for name, _, _ in server._PENDING_TOOLS}

    assert {
        "create_baton",
        "pass_baton",
        "return_baton",
        "complete_baton",
        "block_baton",
        "get_my_batons",
        "get_baton",
    } <= names

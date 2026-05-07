"""Offline smoke test for the baton review loop.

Exercises service-driven baton transitions through the real SQLite layer while
observing each state through the HTTP API. No provider/model agents are started.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.services import baton_service

pytestmark = pytest.mark.integration


@pytest.fixture
def live_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


@pytest.fixture
def client(live_db, monkeypatch):
    monkeypatch.setenv("CAO_BATON_ENABLED", "true")
    from test.api.conftest import TestClientWithHost

    from cli_agent_orchestrator.api.main import app

    return TestClientWithHost(app)


def _pending_messages(receiver_id: str):
    return db_module.list_pending_inbox_notifications(receiver_id, limit=50)


def _get_baton(client, baton_id: str):
    response = client.get(f"/batons/{baton_id}")
    assert response.status_code == 200
    return response.json()


def _event_types(client, baton_id: str):
    response = client.get(f"/batons/{baton_id}/events")
    assert response.status_code == 200
    return [event["event_type"] for event in response.json()]


def _active_baton_ids(client, *, holder_id: str | None = None):
    params = {"status": "active"}
    if holder_id is not None:
        params["holder_id"] = holder_id
    response = client.get("/batons", params=params)
    assert response.status_code == 200
    return [baton["id"] for baton in response.json()]


def test_baton_review_loop_is_observable_over_http(client, live_db):
    baton_id = "smoke-baton-1"

    baton_service.create_baton(
        baton_id=baton_id,
        title="T09 smoke workflow",
        originator_id="originator",
        holder_id="implementer",
        message="Implement the task and pass to review.",
        expected_next_action="implement and request review",
    )

    baton = _get_baton(client, baton_id)
    assert baton["status"] == "active"
    assert baton["current_holder_id"] == "implementer"
    assert baton["return_stack"] == []
    assert _event_types(client, baton_id) == ["create"]
    assert _active_baton_ids(client, holder_id="implementer") == [baton_id]

    implementer_messages = _pending_messages("implementer")
    assert len(implementer_messages) == 1
    assert implementer_messages[0].message.sender_id == "originator"
    assert "Implement the task and pass to review." in implementer_messages[0].message.body

    baton_service.pass_baton(
        baton_id=baton_id,
        actor_id="implementer",
        receiver_id="reviewer",
        message="Please review the implementation artifacts.",
        expected_next_action="review and return findings",
    )

    baton = _get_baton(client, baton_id)
    assert baton["status"] == "active"
    assert baton["current_holder_id"] == "reviewer"
    assert baton["return_stack"] == ["implementer"]
    assert _event_types(client, baton_id) == ["create", "pass"]
    assert _active_baton_ids(client, holder_id="implementer") == []
    assert _active_baton_ids(client, holder_id="reviewer") == [baton_id]

    reviewer_messages = _pending_messages("reviewer")
    assert len(reviewer_messages) == 1
    assert reviewer_messages[0].message.sender_id == "implementer"
    assert "Please review the implementation artifacts." in reviewer_messages[0].message.body

    baton_service.return_baton(
        baton_id=baton_id,
        actor_id="reviewer",
        message="Changes requested before approval.",
        expected_next_action="revise and complete",
    )

    baton = _get_baton(client, baton_id)
    assert baton["status"] == "active"
    assert baton["current_holder_id"] == "implementer"
    assert baton["return_stack"] == []
    assert _event_types(client, baton_id) == ["create", "pass", "return"]
    assert _active_baton_ids(client, holder_id="implementer") == [baton_id]
    assert _active_baton_ids(client, holder_id="reviewer") == []

    implementer_messages = _pending_messages("implementer")
    assert len(implementer_messages) == 2
    assert implementer_messages[-1].message.sender_id == "reviewer"
    assert "Changes requested before approval." in implementer_messages[-1].message.body

    baton_service.complete_baton(
        baton_id=baton_id,
        actor_id="implementer",
        message="Implemented, reviewed, and complete.",
    )

    baton = _get_baton(client, baton_id)
    assert baton["status"] == "completed"
    assert baton["current_holder_id"] is None
    assert baton["return_stack"] == []
    assert baton["completed_at"] is not None
    assert _event_types(client, baton_id) == ["create", "pass", "return", "complete"]
    assert baton_id not in _active_baton_ids(client)

    originator_messages = _pending_messages("originator")
    assert len(originator_messages) == 1
    assert originator_messages[0].message.sender_id == "implementer"
    assert "Implemented, reviewed, and complete." in originator_messages[0].message.body

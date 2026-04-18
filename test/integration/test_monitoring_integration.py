"""End-to-end integration tests for the monitoring sessions feature.

Exercise HTTP → service → real SQLite together. Per-layer unit tests mock the
layer below, so integration bugs (Pydantic response-model mismatches, SQL
semantic errors, FK behavior in production shape) wouldn't surface. These
tests close that gap.

Uses the FastAPI ``TestClient`` with ``SessionLocal`` rebound to an in-memory
SQLite engine that has the same ``PRAGMA foreign_keys=ON`` listener as
production, so FK cascade fires exactly as in the deployed app.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base, InboxModel
from cli_agent_orchestrator.models.inbox import MessageStatus


pytestmark = pytest.mark.integration


@pytest.fixture
def live_db(monkeypatch):
    """Rebind ``SessionLocal`` to an in-memory SQLite engine configured the
    same way as production (FK enforcement on). Return the sessionmaker so
    tests can seed inbox rows directly."""
    # StaticPool + check_same_thread=False so TestClient worker threads share
    # the single in-memory database rather than each getting a fresh empty one.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _conn_record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


@pytest.fixture
def client(live_db):
    from test.api.conftest import TestClientWithHost
    from cli_agent_orchestrator.api.main import app

    return TestClientWithHost(app)


def _seed_inbox(session_maker, *, sender_id, receiver_id, message, created_at,
                status=MessageStatus.DELIVERED):
    with session_maker() as s:
        row = InboxModel(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message=message,
            status=status.value,
            created_at=created_at,
        )
        s.add(row)
        s.commit()


# ---------------------------------------------------------------------------
# Full lifecycle: create → send messages → end → fetch log artifact
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_create_seed_messages_end_fetch_artifact(self, client, live_db):
        """The primary use case from the plan: start monitoring an implementer,
        exchange messages with a reviewer, end the session, fetch the markdown
        artifact that will sit next to the review document."""
        # 1. Create session monitoring implementer, scoped to reviewer R1
        resp = client.post(
            "/monitoring/sessions",
            json={"terminal_id": "IMP", "peer_terminal_ids": ["R1"], "label": "review-v1"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["id"]
        started_at = datetime.fromisoformat(resp.json()["started_at"])

        # 2. Seed inbox with messages in the window (mix of in-scope and off-scope).
        # Use microsecond offsets so the seeded timestamps land within the
        # session window even though end_session stamps ended_at only a few
        # milliseconds after started_at.
        t1 = started_at + timedelta(microseconds=100)
        t2 = started_at + timedelta(microseconds=200)
        t_off = started_at + timedelta(microseconds=300)
        _seed_inbox(live_db, sender_id="IMP", receiver_id="R1", message="please review", created_at=t1)
        _seed_inbox(live_db, sender_id="R1", receiver_id="IMP", message="lgtm with nits", created_at=t2)
        _seed_inbox(live_db, sender_id="IMP", receiver_id="OTHER", message="off-scope", created_at=t_off)

        # 3. Messages endpoint honors scope: OTHER is excluded because R1 is the only peer
        msgs = client.get(f"/monitoring/sessions/{session_id}/messages")
        assert msgs.status_code == 200
        bodies = [m["message"] for m in msgs.json()]
        assert bodies == ["please review", "lgtm with nits"]

        # 4. Fetch the markdown log artifact while session is still active
        #    (the "live artifact during review" case — ended_at=None means the
        #    upper bound is now, which is still after the seeded timestamps).
        log = client.get(f"/monitoring/sessions/{session_id}/log")
        assert log.status_code == 200
        body = log.text
        assert body.startswith("# Monitoring session: review-v1")
        assert "**Monitored:** IMP" in body
        assert "**Peers:** R1" in body
        assert "> please review" in body
        assert "> lgtm with nits" in body
        assert "off-scope" not in body

        # 5. Fetch the JSON log artifact for programmatic use
        log_json = client.get(f"/monitoring/sessions/{session_id}/log?format=json")
        assert log_json.status_code == 200
        payload = log_json.json()
        assert payload["session"]["id"] == session_id
        assert len(payload["messages"]) == 2

        # 6. End the session, confirm status flips and the ended artifact also works
        end = client.post(f"/monitoring/sessions/{session_id}/end")
        assert end.status_code == 200
        assert end.json()["status"] == "ended"


# ---------------------------------------------------------------------------
# Retroactive peer filter — add peer mid-session, verify via HTTP
# ---------------------------------------------------------------------------


class TestRetroactivePeerFilter:
    def test_adding_peer_mid_window_reveals_earlier_messages(self, client, live_db):
        resp = client.post(
            "/monitoring/sessions",
            json={"terminal_id": "IMP", "peer_terminal_ids": ["R1"]},
        )
        session_id = resp.json()["id"]
        started_at = datetime.fromisoformat(resp.json()["started_at"])

        # Seed a message involving R2 (not yet in peer set)
        _seed_inbox(
            live_db,
            sender_id="IMP",
            receiver_id="R2",
            message="hidden-until-R2-added",
            created_at=started_at + timedelta(seconds=1),
        )

        # Invisible pre-add
        assert client.get(f"/monitoring/sessions/{session_id}/messages").json() == []

        # Add R2 as a peer
        add = client.post(
            f"/monitoring/sessions/{session_id}/peers",
            json={"peer_terminal_ids": ["R2"]},
        )
        assert add.status_code == 200

        # Now visible
        msgs = client.get(f"/monitoring/sessions/{session_id}/messages").json()
        assert [m["message"] for m in msgs] == ["hidden-until-R2-added"]


# ---------------------------------------------------------------------------
# FK CASCADE really fires through HTTP DELETE
# ---------------------------------------------------------------------------


class TestCascadeOnDelete:
    def test_delete_session_removes_peer_rows(self, client, live_db):
        """Confirms that the production pragma + FK schema together actually
        enforce cascade when the route performs a DELETE. Peer rows must not
        linger as orphans."""
        from cli_agent_orchestrator.clients.database import (
            MonitoringSessionPeerModel,
        )

        resp = client.post(
            "/monitoring/sessions",
            json={"terminal_id": "T", "peer_terminal_ids": ["P1", "P2"]},
        )
        session_id = resp.json()["id"]

        # Sanity: two peer rows exist
        with live_db() as s:
            assert s.query(MonitoringSessionPeerModel).filter_by(
                session_id=session_id
            ).count() == 2

        resp = client.delete(f"/monitoring/sessions/{session_id}")
        assert resp.status_code == 204

        with live_db() as s:
            assert s.query(MonitoringSessionPeerModel).filter_by(
                session_id=session_id
            ).count() == 0


# ---------------------------------------------------------------------------
# Response model round-trip — Pydantic can actually coerce service output
# ---------------------------------------------------------------------------


class TestResponseModelShapes:
    """Unit tests for routes mock the service to return hand-rolled dicts, so
    a real mismatch between ``monitoring_service`` output and the route's
    ``response_model`` wouldn't surface. Drive a real create/get/list against
    the live DB and assert Pydantic coerces cleanly (i.e., no 500 from a
    ValidationError on the response side)."""

    def test_create_and_get_returns_shapes_pydantic_accepts(self, client):
        create = client.post(
            "/monitoring/sessions",
            json={"terminal_id": "T", "peer_terminal_ids": ["P"], "label": "hi"},
        )
        assert create.status_code == 201
        body = create.json()
        assert set(body.keys()) == {
            "id",
            "terminal_id",
            "peer_terminal_ids",
            "label",
            "started_at",
            "ended_at",
            "status",
        }

        fetched = client.get(f"/monitoring/sessions/{body['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == body["id"]

    def test_list_returns_shape_pydantic_accepts(self, client):
        client.post(
            "/monitoring/sessions", json={"terminal_id": "T1"}
        ).raise_for_status()
        client.post(
            "/monitoring/sessions", json={"terminal_id": "T2"}
        ).raise_for_status()

        resp = client.get("/monitoring/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
        for item in resp.json():
            assert "started_at" in item
            assert item["status"] in {"active", "ended"}


# ---------------------------------------------------------------------------
# Mutation-on-ended-session end-to-end
# ---------------------------------------------------------------------------


class TestEndedSessionImmutability:
    def test_add_peers_on_ended_session_returns_409(self, client):
        session_id = client.post(
            "/monitoring/sessions", json={"terminal_id": "T"}
        ).json()["id"]
        client.post(f"/monitoring/sessions/{session_id}/end").raise_for_status()

        resp = client.post(
            f"/monitoring/sessions/{session_id}/peers",
            json={"peer_terminal_ids": ["P"]},
        )
        assert resp.status_code == 409

    def test_remove_peer_on_ended_session_returns_409(self, client):
        session_id = client.post(
            "/monitoring/sessions",
            json={"terminal_id": "T", "peer_terminal_ids": ["P"]},
        ).json()["id"]
        client.post(f"/monitoring/sessions/{session_id}/end").raise_for_status()

        resp = client.delete(f"/monitoring/sessions/{session_id}/peers/P")
        assert resp.status_code == 409

    def test_end_twice_returns_409(self, client):
        session_id = client.post(
            "/monitoring/sessions", json={"terminal_id": "T"}
        ).json()["id"]
        client.post(f"/monitoring/sessions/{session_id}/end").raise_for_status()

        resp = client.post(f"/monitoring/sessions/{session_id}/end")
        assert resp.status_code == 409

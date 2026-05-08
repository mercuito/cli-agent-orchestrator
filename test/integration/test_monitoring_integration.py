"""End-to-end integration tests for the monitoring sessions feature.

Exercises HTTP → service → real SQLite together under the single-session,
query-time-filter model. Per-layer unit tests mock the layer below, so
integration bugs (Pydantic response-model mismatches, SQL semantic errors)
wouldn't surface. These tests close that gap.

Uses the FastAPI ``TestClient`` with ``SessionLocal`` rebound to an
in-memory SQLite engine configured the same way as production (FK
enforcement on, ``StaticPool`` so the worker thread shares the single
in-memory DB).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import (
    Base,
    INBOX_NOTIFICATION_TARGET_KIND_MESSAGE,
    INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY,
    InboxMessageModel,
    InboxNotificationModel,
    InboxNotificationTargetModel,
)
from cli_agent_orchestrator.models.inbox import MessageStatus

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


def _seed_inbox(
    session_maker, *, sender_id, receiver_id, message, created_at, status=MessageStatus.DELIVERED
):
    with session_maker() as s:
        message_row = InboxMessageModel(
            sender_id=sender_id,
            body=message,
            source_kind="terminal",
            source_id=sender_id,
            created_at=created_at,
        )
        s.add(message_row)
        s.flush()
        notification_row = InboxNotificationModel(
            receiver_id=receiver_id,
            body=message,
            source_kind="terminal",
            source_id=sender_id,
            status=status.value,
            created_at=created_at,
        )
        s.add(notification_row)
        s.flush()
        s.add(
            InboxNotificationTargetModel(
                notification_id=notification_row.id,
                target_kind=INBOX_NOTIFICATION_TARGET_KIND_MESSAGE,
                target_id=str(message_row.id),
                role=INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY,
            )
        )
        s.commit()


class TestFullLifecycle:
    def test_create_seed_messages_end_fetch_artifact(self, client, live_db):
        """Primary use case: start monitoring an implementer, exchange
        messages with reviewers (no peer scoping — we capture everything),
        fetch the unfiltered markdown artifact, then a per-reviewer
        filtered view from the same recording, then end the session."""
        resp = client.post(
            "/monitoring/sessions",
            json={"terminal_id": "IMP", "label": "review-v1"},
        )
        assert resp.status_code == 201
        assert "peer_terminal_ids" not in resp.json()
        session_id = resp.json()["id"]
        started_at = datetime.fromisoformat(resp.json()["started_at"])

        # Seed three in-window messages — two with R1, one with R2
        t1 = started_at + timedelta(microseconds=100)
        t2 = started_at + timedelta(microseconds=200)
        t3 = started_at + timedelta(microseconds=300)
        _seed_inbox(live_db, sender_id="IMP", receiver_id="R1", message="hi R1", created_at=t1)
        _seed_inbox(live_db, sender_id="R1", receiver_id="IMP", message="hi IMP", created_at=t2)
        _seed_inbox(live_db, sender_id="IMP", receiver_id="R2", message="hi R2", created_at=t3)

        # Unfiltered messages — all three captured
        unfiltered = client.get(f"/monitoring/sessions/{session_id}/messages").json()
        assert [m["message"] for m in unfiltered] == ["hi R1", "hi IMP", "hi R2"]

        # Filtered to R1 — only the two R1 messages
        filtered = client.get(
            f"/monitoring/sessions/{session_id}/messages",
            params=[("peer", "R1")],
        ).json()
        assert [m["message"] for m in filtered] == ["hi R1", "hi IMP"]

        # Unfiltered markdown log — header omits Filter line
        log = client.get(f"/monitoring/sessions/{session_id}/log")
        assert log.status_code == 200
        body = log.text
        assert body.startswith("# Monitoring session: review-v1")
        assert "Filter:" not in body
        assert "> hi R1" in body and "> hi R2" in body

        # Filtered markdown artifact — Filter line present, R2 excluded
        filtered_log = client.get(
            f"/monitoring/sessions/{session_id}/log",
            params=[("peer", "R1")],
        )
        assert filtered_log.status_code == 200
        fbody = filtered_log.text
        assert "**Filter:** peers = R1" in fbody
        assert "> hi R1" in fbody
        assert "> hi R2" not in fbody

        # End the session; status flips
        end = client.post(f"/monitoring/sessions/{session_id}/end")
        assert end.status_code == 200
        assert end.json()["status"] == "ended"


class TestIdempotentCreate:
    def test_create_on_monitored_terminal_returns_existing(self, client, live_db):
        a = client.post(
            "/monitoring/sessions",
            json={"terminal_id": "T", "label": "first"},
        ).json()
        b = client.post(
            "/monitoring/sessions",
            json={"terminal_id": "T", "label": "second-ignored"},
        ).json()
        assert a["id"] == b["id"]
        assert b["label"] == "first"

    def test_create_after_ending_yields_new_session(self, client, live_db):
        first_id = client.post("/monitoring/sessions", json={"terminal_id": "T"}).json()["id"]
        client.post(f"/monitoring/sessions/{first_id}/end").raise_for_status()
        second_id = client.post("/monitoring/sessions", json={"terminal_id": "T"}).json()["id"]
        assert first_id != second_id


class TestTimeWindowFilter:
    def test_sub_window_query_narrows_messages(self, client, live_db):
        """Extract a sub-window (e.g. 'step 3' of a long recording)."""
        from cli_agent_orchestrator.clients.database import MonitoringSessionModel

        resp = client.post("/monitoring/sessions", json={"terminal_id": "IMP"})
        session_id = resp.json()["id"]

        # Pin the session start to a known timestamp so we can seed deterministically
        start = datetime(2026, 4, 18, 10, 0, 0)
        with live_db() as s:
            s.query(MonitoringSessionModel).filter_by(id=session_id).update({"started_at": start})
            s.commit()

        for i in range(5):
            _seed_inbox(
                live_db,
                sender_id="IMP",
                receiver_id="R",
                message=f"m{i}",
                created_at=start + timedelta(minutes=i),
            )

        resp = client.get(
            f"/monitoring/sessions/{session_id}/messages",
            params={
                "started_after": (start + timedelta(minutes=2)).isoformat(),
                "started_before": (start + timedelta(minutes=3)).isoformat(),
            },
        )
        assert resp.status_code == 200
        assert [m["message"] for m in resp.json()] == ["m2", "m3"]


class TestResponseModelShapes:
    """Per-layer tests mock the service; real coercion isn't exercised
    until HTTP→service→DB run together. Catches Pydantic shape drift."""

    def test_create_and_get_shapes_pydantic_accepts(self, client, live_db):
        body = client.post("/monitoring/sessions", json={"terminal_id": "T", "label": "hi"})
        assert body.status_code == 201
        payload = body.json()
        assert set(payload.keys()) == {
            "id",
            "terminal_id",
            "label",
            "started_at",
            "ended_at",
            "status",
        }

        fetched = client.get(f"/monitoring/sessions/{payload['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == payload["id"]

    def test_list_shape_pydantic_accepts(self, client, live_db):
        client.post("/monitoring/sessions", json={"terminal_id": "T1"}).raise_for_status()
        client.post("/monitoring/sessions", json={"terminal_id": "T2"}).raise_for_status()
        resp = client.get("/monitoring/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
        for item in resp.json():
            assert "peer_terminal_ids" not in item
            assert item["status"] in {"active", "ended"}


class TestPeerEndpointsGone:
    def test_add_peer_endpoint_removed(self, client, live_db):
        session_id = client.post("/monitoring/sessions", json={"terminal_id": "T"}).json()["id"]
        resp = client.post(
            f"/monitoring/sessions/{session_id}/peers",
            json={"peer_terminal_ids": ["P"]},
        )
        assert resp.status_code in (404, 405)

    def test_remove_peer_endpoint_removed(self, client, live_db):
        session_id = client.post("/monitoring/sessions", json={"terminal_id": "T"}).json()["id"]
        resp = client.delete(f"/monitoring/sessions/{session_id}/peers/P")
        assert resp.status_code in (404, 405)


class TestEndedSessionImmutability:
    def test_end_twice_returns_409(self, client, live_db):
        session_id = client.post("/monitoring/sessions", json={"terminal_id": "T"}).json()["id"]
        client.post(f"/monitoring/sessions/{session_id}/end").raise_for_status()

        resp = client.post(f"/monitoring/sessions/{session_id}/end")
        assert resp.status_code == 409

    def test_create_after_ending_on_same_terminal_is_fine(self, client, live_db):
        """Ending doesn't block future sessions — the idempotency contract
        is 'while active' not 'ever'."""
        sid = client.post("/monitoring/sessions", json={"terminal_id": "T"}).json()["id"]
        client.post(f"/monitoring/sessions/{sid}/end").raise_for_status()

        resp = client.post("/monitoring/sessions", json={"terminal_id": "T"})
        assert resp.status_code == 201
        assert resp.json()["id"] != sid
        assert resp.json()["status"] == "active"

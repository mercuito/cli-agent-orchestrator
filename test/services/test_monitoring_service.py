"""Tests for monitoring_service under the single-session, query-time-filter
model. See docs/plans/monitoring-sessions.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base, InboxModel
from cli_agent_orchestrator.models.inbox import MessageStatus


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
# create / get / end / delete
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_create_with_minimum_args(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import create_session

        result = create_session(terminal_id="term-A")

        assert isinstance(result["id"], str) and result["id"]
        assert result["terminal_id"] == "term-A"
        assert result["label"] is None
        assert result["status"] == "active"
        assert result["ended_at"] is None
        assert isinstance(result["started_at"], datetime)
        # Confirm the simplified shape — no peer_terminal_ids key
        assert "peer_terminal_ids" not in result

    def test_create_with_label(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import create_session

        result = create_session(terminal_id="term-A", label="review-v2")
        assert result["label"] == "review-v2"

    def test_create_is_idempotent_when_active_session_exists(self, patched_db):
        """Clicking 'Monitor' when already recording must not create a
        duplicate. Return the existing session unchanged."""
        from cli_agent_orchestrator.services.monitoring_service import create_session

        first = create_session(terminal_id="term-A", label="original")
        second = create_session(terminal_id="term-A", label="ignored")

        assert first["id"] == second["id"]
        assert second["label"] == "original"  # not overwritten

    def test_create_after_ending_makes_a_new_session(self, patched_db):
        """Ending the previous session releases the terminal for a new one."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
        )

        first = create_session(terminal_id="term-A")
        end_session(first["id"])
        second = create_session(terminal_id="term-A")

        assert first["id"] != second["id"]

    def test_create_on_different_terminals_always_independent(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import create_session

        a = create_session(terminal_id="term-A")
        b = create_session(terminal_id="term-B")
        assert a["id"] != b["id"]


class TestGetSession:
    def test_get_existing_session_round_trip(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session,
        )

        created = create_session(terminal_id="term-A", label="x")
        fetched = get_session(created["id"])

        assert fetched is not None
        assert fetched["id"] == created["id"]
        assert fetched["terminal_id"] == "term-A"
        assert fetched["label"] == "x"
        assert fetched["status"] == "active"

    def test_get_missing_session_returns_none(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import get_session

        assert get_session("nope") is None


class TestEndSession:
    def test_end_active_session(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
            get_session,
        )

        created = create_session(terminal_id="term-A")
        result = end_session(created["id"])

        assert result["ended_at"] is not None
        assert result["status"] == "ended"
        assert get_session(created["id"])["status"] == "ended"

    def test_end_already_ended_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionAlreadyEnded,
            create_session,
            end_session,
        )

        created = create_session(terminal_id="term-A")
        end_session(created["id"])

        with pytest.raises(SessionAlreadyEnded):
            end_session(created["id"])

    def test_end_missing_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionNotFound,
            end_session,
        )

        with pytest.raises(SessionNotFound):
            end_session("nope")


class TestDeleteSession:
    def test_delete_removes_session(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            delete_session,
            get_session,
        )

        created = create_session(terminal_id="term-A")
        delete_session(created["id"])
        assert get_session(created["id"]) is None

    def test_delete_missing_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionNotFound,
            delete_session,
        )

        with pytest.raises(SessionNotFound):
            delete_session("nope")


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_list_all_when_no_filters(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        create_session(terminal_id="A")
        create_session(terminal_id="B")
        assert len(list_sessions()) == 2

    def test_filter_by_terminal_id(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        create_session(terminal_id="A")
        create_session(terminal_id="B")
        result = list_sessions(terminal_id="A")
        assert [r["terminal_id"] for r in result] == ["A"]

    def test_filter_status_active(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
            list_sessions,
        )

        active = create_session(terminal_id="A")
        ended = create_session(terminal_id="B")
        end_session(ended["id"])
        assert [s["id"] for s in list_sessions(status="active")] == [active["id"]]

    def test_filter_status_ended(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
            list_sessions,
        )

        create_session(terminal_id="A")
        ended = create_session(terminal_id="B")
        end_session(ended["id"])
        assert [s["id"] for s in list_sessions(status="ended")] == [ended["id"]]

    def test_filter_label_exact(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        a = create_session(terminal_id="A", label="hit")
        create_session(terminal_id="B", label="miss")
        assert [s["id"] for s in list_sessions(label="hit")] == [a["id"]]

    def test_multiple_filters_combined_are_ANDed(self, patched_db):
        """Each filter must narrow the result independently. Using distinct
        terminals per case so idempotency doesn't interfere — we want to
        prove AND semantics, not side-effect arithmetic."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
            list_sessions,
        )

        # Only `target` matches all three filters simultaneously.
        target = create_session(terminal_id="A", label="t")
        create_session(terminal_id="B", label="t")        # wrong terminal
        create_session(terminal_id="C", label="other")    # wrong label
        ended = create_session(terminal_id="D", label="t")  # wrong status
        end_session(ended["id"])

        result = list_sessions(terminal_id="A", label="t", status="active")
        assert [s["id"] for s in result] == [target["id"]]

        # Sanity: flipping any single filter picks up a different row and
        # never collapses to the same one-row result by accident.
        assert len(list_sessions(label="t", status="active")) == 2  # A + B
        assert len(list_sessions(terminal_id="A")) == 1             # just A
        assert len(list_sessions(status="ended")) == 1              # just D

    def test_filter_time_range(self, patched_db):
        from cli_agent_orchestrator.clients.database import MonitoringSessionModel
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        old = create_session(terminal_id="A")
        new = create_session(terminal_id="B")

        with patched_db() as s:
            s.query(MonitoringSessionModel).filter_by(id=old["id"]).update(
                {"started_at": datetime(2026, 1, 1)}
            )
            s.query(MonitoringSessionModel).filter_by(id=new["id"]).update(
                {"started_at": datetime(2026, 6, 1)}
            )
            s.commit()

        cutoff = datetime(2026, 3, 1)
        assert [s["id"] for s in list_sessions(started_after=cutoff)] == [new["id"]]
        assert [s["id"] for s in list_sessions(started_before=cutoff)] == [old["id"]]

    def test_pagination(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        # Distinct terminals since idempotent create collapses same-terminal calls
        for i in range(5):
            create_session(terminal_id=f"t-{i}")

        page1 = list_sessions(limit=2, offset=0)
        page2 = list_sessions(limit=2, offset=2)
        page3 = list_sessions(limit=2, offset=4)
        assert len(page1) == 2 and len(page2) == 2 and len(page3) == 1
        ids = {s["id"] for s in page1 + page2 + page3}
        assert len(ids) == 5


# ---------------------------------------------------------------------------
# get_session_messages — all filtering is query-time now
# ---------------------------------------------------------------------------


class TestGetSessionMessages:
    def test_captures_all_io_of_monitored_terminal_by_default(self, patched_db):
        """No peer filter = record everything touching the terminal.
        Under the new model this is ALWAYS the default at capture time;
        narrowing happens at read time."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        base = datetime.now()
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R1", message="to-r1",
                    created_at=base + timedelta(seconds=1))
        _seed_inbox(patched_db, sender_id="R2", receiver_id="IMP", message="from-r2",
                    created_at=base + timedelta(seconds=2))
        # Off-scope (doesn't involve IMP) — must be excluded
        _seed_inbox(patched_db, sender_id="R1", receiver_id="R2", message="noise",
                    created_at=base + timedelta(seconds=3))

        result = get_session_messages(session["id"])
        assert [m["message"] for m in result] == ["to-r1", "from-r2"]

    def test_peer_filter_at_query_time_or_semantics_either_side(self, patched_db):
        """``peers`` matches against sender OR receiver. Covers both
        directions — peer as receiver and peer as sender — in one test."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        base = datetime.now()
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R1", message="peer-recv",
                    created_at=base + timedelta(seconds=1))
        _seed_inbox(patched_db, sender_id="R1", receiver_id="IMP", message="peer-sent",
                    created_at=base + timedelta(seconds=2))
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R2", message="other-recv",
                    created_at=base + timedelta(seconds=3))

        result = get_session_messages(session["id"], peers=["R1"])
        assert [m["message"] for m in result] == ["peer-recv", "peer-sent"]

    def test_peer_filter_accepts_multiple_peers(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        base = datetime.now()
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R1", message="r1",
                    created_at=base + timedelta(seconds=1))
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R2", message="r2",
                    created_at=base + timedelta(seconds=2))
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R3", message="r3",
                    created_at=base + timedelta(seconds=3))

        result = get_session_messages(session["id"], peers=["R1", "R3"])
        assert [m["message"] for m in result] == ["r1", "r3"]

    def test_empty_peer_list_is_treated_as_no_filter(self, patched_db):
        """Callers might pass ``peers=[]`` from a UI where the selection is
        empty. Treat this the same as ``peers=None`` — no filter. Otherwise
        the caller would get an empty result every time they forgot to
        populate the list."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R1", message="a",
                    created_at=datetime.now())

        result = get_session_messages(session["id"], peers=[])
        assert len(result) == 1

    def test_messages_ordered_by_created_at_asc(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        base = datetime.now()
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R", message="third",
                    created_at=base + timedelta(seconds=3))
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R", message="first",
                    created_at=base + timedelta(seconds=1))
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R", message="second",
                    created_at=base + timedelta(seconds=2))

        result = get_session_messages(session["id"])
        assert [m["message"] for m in result] == ["first", "second", "third"]

    def test_bounded_by_session_started_at(self, patched_db):
        from cli_agent_orchestrator.clients.database import MonitoringSessionModel
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        start = datetime(2026, 4, 18, 10, 0, 0)
        with patched_db() as s:
            s.query(MonitoringSessionModel).filter_by(id=session["id"]).update(
                {"started_at": start}
            )
            s.commit()

        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R", message="before",
                    created_at=start - timedelta(minutes=5))
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R", message="after",
                    created_at=start + timedelta(minutes=5))

        assert [m["message"] for m in get_session_messages(session["id"])] == ["after"]

    def test_bounded_by_session_ended_at(self, patched_db):
        from cli_agent_orchestrator.clients.database import MonitoringSessionModel
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        start = datetime(2026, 4, 18, 10, 0, 0)
        end = datetime(2026, 4, 18, 11, 0, 0)
        with patched_db() as s:
            s.query(MonitoringSessionModel).filter_by(id=session["id"]).update(
                {"started_at": start, "ended_at": end}
            )
            s.commit()

        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R", message="in",
                    created_at=start + timedelta(minutes=30))
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R", message="after",
                    created_at=end + timedelta(minutes=5))

        assert [m["message"] for m in get_session_messages(session["id"])] == ["in"]

    def test_ongoing_session_upper_bound_is_now(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        _seed_inbox(patched_db, sender_id="IMP", receiver_id="R", message="live",
                    created_at=datetime.now() + timedelta(seconds=1))

        assert [m["message"] for m in get_session_messages(session["id"])] == ["live"]

    def test_query_time_sub_window_narrows_within_session(self, patched_db):
        """Callers can slice out a sub-window of a longer recording — e.g.
        extract just the "step 3" portion of a run-long session."""
        from cli_agent_orchestrator.clients.database import MonitoringSessionModel
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        start = datetime(2026, 4, 18, 10, 0, 0)
        with patched_db() as s:
            s.query(MonitoringSessionModel).filter_by(id=session["id"]).update(
                {"started_at": start}
            )
            s.commit()

        for i in range(5):
            _seed_inbox(
                patched_db,
                sender_id="IMP",
                receiver_id="R",
                message=f"m{i}",
                created_at=start + timedelta(minutes=i),
            )

        # Only messages between +2m and +3m (inclusive)
        result = get_session_messages(
            session["id"],
            started_after=start + timedelta(minutes=2),
            started_before=start + timedelta(minutes=3),
        )
        assert [m["message"] for m in result] == ["m2", "m3"]

    def test_get_messages_on_missing_session_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionNotFound,
            get_session_messages,
        )

        with pytest.raises(SessionNotFound):
            get_session_messages("nope")

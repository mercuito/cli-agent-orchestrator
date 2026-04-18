"""Tests for monitoring_service.

Phase 2 of the monitoring sessions feature. See docs/plans/monitoring-sessions.md.

These tests hit real in-memory SQLite (via a fixture that monkeypatches
``SessionLocal``) because the business logic being verified — retroactive peer
filter on messages, list filtering, FK CASCADE on delete, bounded time windows
— is SQL-semantic. Mocks wouldn't catch mistakes in these queries.
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
    """Swap ``database.SessionLocal`` for an in-memory SQLite sessionmaker.

    The service layer imports ``SessionLocal`` at call time via ``with
    SessionLocal() as db:``, so monkeypatching the attribute on the module is
    sufficient. FK enforcement is turned on to match production behavior.
    """
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
    """Insert a row into the inbox table at an explicit created_at.

    ``created_at`` has to be set explicitly because ``InboxModel.created_at``
    defaults to ``datetime.now`` at insert time — the time-window tests below
    need historical timestamps.
    """
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
    def test_create_with_minimum_args_returns_populated_dict(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import create_session

        result = create_session(terminal_id="term-A")

        assert "id" in result and isinstance(result["id"], str) and result["id"]
        assert result["terminal_id"] == "term-A"
        assert result["label"] is None
        assert result["peer_terminal_ids"] == []
        assert result["ended_at"] is None
        assert result["status"] == "active"
        assert isinstance(result["started_at"], datetime)

    def test_create_with_peers_and_label(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import create_session

        result = create_session(
            terminal_id="term-A",
            peer_terminal_ids=["P1", "P2"],
            label="review-v2",
        )

        assert result["label"] == "review-v2"
        assert sorted(result["peer_terminal_ids"]) == ["P1", "P2"]

    def test_create_deduplicates_peer_terminal_ids_in_input(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import create_session

        result = create_session(
            terminal_id="term-A",
            peer_terminal_ids=["P1", "P1", "P2"],
        )

        assert sorted(result["peer_terminal_ids"]) == ["P1", "P2"]

    def test_create_returns_unique_ids(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import create_session

        a = create_session(terminal_id="term-A")
        b = create_session(terminal_id="term-A")
        assert a["id"] != b["id"]


class TestGetSession:
    def test_get_existing_session_round_trip(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session,
        )

        created = create_session(
            terminal_id="term-A", peer_terminal_ids=["P1"], label="x"
        )
        fetched = get_session(created["id"])

        assert fetched is not None
        assert fetched["id"] == created["id"]
        assert fetched["terminal_id"] == "term-A"
        assert fetched["peer_terminal_ids"] == ["P1"]
        assert fetched["label"] == "x"
        assert fetched["status"] == "active"

    def test_get_missing_session_returns_none(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import get_session

        assert get_session("nope") is None


class TestEndSession:
    def test_end_active_session_sets_ended_at_and_status(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
            get_session,
        )

        created = create_session(terminal_id="term-A")
        result = end_session(created["id"])

        assert result["ended_at"] is not None
        assert result["status"] == "ended"

        refetched = get_session(created["id"])
        assert refetched["status"] == "ended"

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
    def test_delete_removes_session_and_cascades_to_peers(self, patched_db):
        from cli_agent_orchestrator.clients.database import MonitoringSessionPeerModel
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            delete_session,
            get_session,
        )

        created = create_session(terminal_id="term-A", peer_terminal_ids=["P1", "P2"])
        delete_session(created["id"])

        assert get_session(created["id"]) is None
        with patched_db() as s:
            remaining = (
                s.query(MonitoringSessionPeerModel)
                .filter_by(session_id=created["id"])
                .count()
            )
            assert remaining == 0

    def test_delete_missing_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionNotFound,
            delete_session,
        )

        with pytest.raises(SessionNotFound):
            delete_session("nope")


# ---------------------------------------------------------------------------
# add/remove peer
# ---------------------------------------------------------------------------


class TestAddPeers:
    def test_add_to_active_session(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            add_peers,
            create_session,
            get_session,
        )

        created = create_session(terminal_id="term-A", peer_terminal_ids=["P1"])
        add_peers(created["id"], ["P2", "P3"])

        refetched = get_session(created["id"])
        assert sorted(refetched["peer_terminal_ids"]) == ["P1", "P2", "P3"]

    def test_add_existing_peer_is_idempotent(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            add_peers,
            create_session,
            get_session,
        )

        created = create_session(terminal_id="term-A", peer_terminal_ids=["P1"])
        add_peers(created["id"], ["P1", "P2"])  # P1 already present

        refetched = get_session(created["id"])
        assert sorted(refetched["peer_terminal_ids"]) == ["P1", "P2"]

    def test_add_on_ended_session_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionAlreadyEnded,
            add_peers,
            create_session,
            end_session,
        )

        created = create_session(terminal_id="term-A")
        end_session(created["id"])

        with pytest.raises(SessionAlreadyEnded):
            add_peers(created["id"], ["P1"])

    def test_add_on_missing_session_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionNotFound,
            add_peers,
        )

        with pytest.raises(SessionNotFound):
            add_peers("nope", ["P1"])


class TestRemovePeer:
    def test_remove_existing_peer(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session,
            remove_peer,
        )

        created = create_session(terminal_id="term-A", peer_terminal_ids=["P1", "P2"])
        remove_peer(created["id"], "P1")

        refetched = get_session(created["id"])
        assert refetched["peer_terminal_ids"] == ["P2"]

    def test_remove_nonexistent_peer_is_noop(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session,
            remove_peer,
        )

        created = create_session(terminal_id="term-A", peer_terminal_ids=["P1"])
        remove_peer(created["id"], "not-a-peer")  # must not raise

        refetched = get_session(created["id"])
        assert refetched["peer_terminal_ids"] == ["P1"]

    def test_remove_on_ended_session_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionAlreadyEnded,
            create_session,
            end_session,
            remove_peer,
        )

        created = create_session(terminal_id="term-A", peer_terminal_ids=["P1"])
        end_session(created["id"])

        with pytest.raises(SessionAlreadyEnded):
            remove_peer(created["id"], "P1")

    def test_remove_on_missing_session_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionNotFound,
            remove_peer,
        )

        with pytest.raises(SessionNotFound):
            remove_peer("nope", "P1")


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

        result = list_sessions()
        assert len(result) == 2

    def test_filter_by_terminal_id(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        create_session(terminal_id="A")
        create_session(terminal_id="B")

        result = list_sessions(terminal_id="A")
        assert len(result) == 1
        assert result[0]["terminal_id"] == "A"

    def test_filter_by_peer_terminal_id(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        create_session(terminal_id="A", peer_terminal_ids=["P1"])
        create_session(terminal_id="B", peer_terminal_ids=["P2"])
        create_session(terminal_id="C", peer_terminal_ids=[])

        result = list_sessions(peer_terminal_id="P1")
        assert len(result) == 1
        assert result[0]["terminal_id"] == "A"

    def test_filter_involves_matches_terminal_or_peer(self, patched_db):
        """`involves=X` returns sessions where X is the monitored terminal OR X
        is in the peer set. Design decision — this is the most common query."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        create_session(terminal_id="X", peer_terminal_ids=[])  # match as terminal
        create_session(terminal_id="A", peer_terminal_ids=["X"])  # match as peer
        create_session(terminal_id="A", peer_terminal_ids=["other"])  # no match

        result = list_sessions(involves="X")
        assert len(result) == 2

    def test_filter_status_active(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
            list_sessions,
        )

        active = create_session(terminal_id="A")
        ended = create_session(terminal_id="B")
        end_session(ended["id"])

        result = list_sessions(status="active")
        assert [s["id"] for s in result] == [active["id"]]

    def test_filter_status_ended(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
            list_sessions,
        )

        create_session(terminal_id="A")
        ended = create_session(terminal_id="B")
        end_session(ended["id"])

        result = list_sessions(status="ended")
        assert [s["id"] for s in result] == [ended["id"]]

    def test_filter_label_exact_match(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        a = create_session(terminal_id="A", label="hit")
        create_session(terminal_id="B", label="miss")

        result = list_sessions(label="hit")
        assert [s["id"] for s in result] == [a["id"]]

    def test_filter_time_range(self, patched_db):
        """started_after / started_before bound by started_at timestamp."""
        from cli_agent_orchestrator.clients.database import MonitoringSessionModel
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        old_time = datetime(2026, 1, 1, 12, 0, 0)
        new_time = datetime(2026, 6, 1, 12, 0, 0)

        # created_session defaults started_at to now; for time-range test we
        # need to pin timestamps, so we edit them directly after create.
        old = create_session(terminal_id="A")
        new = create_session(terminal_id="A")

        with patched_db() as s:
            s.query(MonitoringSessionModel).filter_by(id=old["id"]).update(
                {"started_at": old_time}
            )
            s.query(MonitoringSessionModel).filter_by(id=new["id"]).update(
                {"started_at": new_time}
            )
            s.commit()

        cutoff = datetime(2026, 3, 1)
        assert [s["id"] for s in list_sessions(started_after=cutoff)] == [new["id"]]
        assert [s["id"] for s in list_sessions(started_before=cutoff)] == [old["id"]]

    def test_multiple_filters_combined_are_ANDed(self, patched_db):
        """All filters should compose as AND. Each filter is tested in
        isolation elsewhere — this test covers the conjunction specifically,
        because that's the shape a real query from a procedure will use."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
            list_sessions,
        )

        # Target we expect to match (terminal=A, label=target, status=active)
        target = create_session(terminal_id="A", label="target")
        # Wrong terminal
        create_session(terminal_id="B", label="target")
        # Wrong label
        create_session(terminal_id="A", label="other")
        # Right terminal + label but ended
        wrong_status = create_session(terminal_id="A", label="target")
        end_session(wrong_status["id"])

        result = list_sessions(
            terminal_id="A", label="target", status="active"
        )
        assert [s["id"] for s in result] == [target["id"]]

    def test_pagination_limit_and_offset(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            list_sessions,
        )

        for _ in range(5):
            create_session(terminal_id="A")

        page1 = list_sessions(limit=2, offset=0)
        page2 = list_sessions(limit=2, offset=2)
        page3 = list_sessions(limit=2, offset=4)

        assert len(page1) == 2 and len(page2) == 2 and len(page3) == 1
        ids = {s["id"] for s in page1} | {s["id"] for s in page2} | {s["id"] for s in page3}
        assert len(ids) == 5  # no overlap


# ---------------------------------------------------------------------------
# get_session_messages
# ---------------------------------------------------------------------------


class TestGetSessionMessages:
    def test_empty_peer_set_captures_all_io_of_monitored_terminal(self, patched_db):
        """Design decision: no rows in peers = unscoped (capture everything
        touching the monitored terminal)."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        # Two messages involving IMP in different directions + different peers
        base = datetime.now()
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R1",
            message="ask",
            created_at=base + timedelta(seconds=1),
        )
        _seed_inbox(
            patched_db,
            sender_id="R2",
            receiver_id="IMP",
            message="reply",
            created_at=base + timedelta(seconds=2),
        )
        # Noise: message not involving IMP must be excluded
        _seed_inbox(
            patched_db,
            sender_id="R1",
            receiver_id="R2",
            message="side-chatter",
            created_at=base + timedelta(seconds=3),
        )

        result = get_session_messages(session["id"])
        messages = [m["message"] for m in result]
        assert messages == ["ask", "reply"]

    def test_peer_filter_excludes_messages_with_other_peers(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP", peer_terminal_ids=["R1"])
        base = datetime.now()
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R1",
            message="to-R1",
            created_at=base + timedelta(seconds=1),
        )
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R2",
            message="to-R2",
            created_at=base + timedelta(seconds=2),
        )

        result = get_session_messages(session["id"])
        assert [m["message"] for m in result] == ["to-R1"]

    def test_messages_ordered_by_created_at_ascending(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        base = datetime.now()
        # Insert out of order
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R",
            message="third",
            created_at=base + timedelta(seconds=3),
        )
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R",
            message="first",
            created_at=base + timedelta(seconds=1),
        )
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R",
            message="second",
            created_at=base + timedelta(seconds=2),
        )

        result = get_session_messages(session["id"])
        assert [m["message"] for m in result] == ["first", "second", "third"]

    def test_bounded_by_started_at_lower(self, patched_db):
        """Messages before session start are excluded even if they involve the
        monitored terminal."""
        from cli_agent_orchestrator.clients.database import MonitoringSessionModel
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        # Move session start to a fixed time
        session_start = datetime(2026, 4, 18, 10, 0, 0)
        with patched_db() as s:
            s.query(MonitoringSessionModel).filter_by(id=session["id"]).update(
                {"started_at": session_start}
            )
            s.commit()

        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R",
            message="before",
            created_at=session_start - timedelta(minutes=5),
        )
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R",
            message="after",
            created_at=session_start + timedelta(minutes=5),
        )

        result = get_session_messages(session["id"])
        assert [m["message"] for m in result] == ["after"]

    def test_bounded_by_ended_at_upper_for_ended_sessions(self, patched_db):
        from cli_agent_orchestrator.clients.database import MonitoringSessionModel
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            end_session,
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

        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R",
            message="in-window",
            created_at=start + timedelta(minutes=30),
        )
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R",
            message="after-end",
            created_at=end + timedelta(minutes=5),
        )

        result = get_session_messages(session["id"])
        assert [m["message"] for m in result] == ["in-window"]

    def test_ongoing_session_upper_bound_is_now(self, patched_db):
        """When ended_at is NULL, the upper bound is 'now' — so recent messages
        are included without the session needing to be ended first."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP")
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R",
            message="live",
            created_at=datetime.now() + timedelta(seconds=1),
        )

        result = get_session_messages(session["id"])
        assert [m["message"] for m in result] == ["live"]

    def test_peer_filter_matches_when_peer_is_sender(self, patched_db):
        """The peer filter uses OR across sender and receiver. Explicitly
        cover the direction where the peer is the SENDER of the message
        (earlier tests only covered peer-as-receiver). Asymmetry bugs in the
        filter SQL would break this case first."""
        from cli_agent_orchestrator.services.monitoring_service import (
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP", peer_terminal_ids=["R1"])
        base = datetime.now()
        # Peer sends to IMP
        _seed_inbox(
            patched_db,
            sender_id="R1",
            receiver_id="IMP",
            message="peer-as-sender",
            created_at=base + timedelta(seconds=1),
        )
        # Non-peer sends to IMP (should be excluded)
        _seed_inbox(
            patched_db,
            sender_id="R2",
            receiver_id="IMP",
            message="other-as-sender",
            created_at=base + timedelta(seconds=2),
        )

        result = get_session_messages(session["id"])
        assert [m["message"] for m in result] == ["peer-as-sender"]

    def test_retroactive_peer_filter_add_mid_window(self, patched_db):
        """Plan design decision #3: adding a peer mid-session exposes earlier
        in-window messages involving that peer. The peer list is evaluated at
        query time, not at peer-add time."""
        from cli_agent_orchestrator.services.monitoring_service import (
            add_peers,
            create_session,
            get_session_messages,
        )

        session = create_session(terminal_id="IMP", peer_terminal_ids=["R1"])
        base = datetime.now()
        # Early message with R2 — outside the initial peer set
        _seed_inbox(
            patched_db,
            sender_id="IMP",
            receiver_id="R2",
            message="early-to-R2",
            created_at=base + timedelta(seconds=1),
        )

        # With R2 not in the peer set, message is hidden
        initial = get_session_messages(session["id"])
        assert [m["message"] for m in initial] == []

        # Add R2 to the peer set
        add_peers(session["id"], ["R2"])

        # Message with R2 from BEFORE the add is now visible — retroactive
        updated = get_session_messages(session["id"])
        assert [m["message"] for m in updated] == ["early-to-R2"]

    def test_get_messages_on_missing_session_raises(self, patched_db):
        from cli_agent_orchestrator.services.monitoring_service import (
            SessionNotFound,
            get_session_messages,
        )

        with pytest.raises(SessionNotFound):
            get_session_messages("nope")

"""Tests for monitoring sessions schema.

Phase 1 of the monitoring sessions feature. See docs/plans/monitoring-sessions.md.

These tests use real in-memory SQLite (not mocks) because cascade-on-delete
behavior is exactly the kind of thing a mock cannot verify.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients.database import (
    Base,
    MonitoringSessionModel,
    MonitoringSessionPeerModel,
)


@pytest.fixture
def db_session():
    """In-memory SQLite session with FK enforcement enabled.

    SQLite does not enforce foreign keys by default; we turn it on per-connection
    so the CASCADE behavior on monitoring_session_peers actually fires.
    """
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionMaker = sessionmaker(bind=engine)
    session = SessionMaker()
    try:
        yield session
    finally:
        session.close()


class TestSchemaRegistration:
    """Both models must be registered on Base.metadata so init_db() picks them up."""

    def test_sessions_table_registered(self):
        assert "monitoring_sessions" in Base.metadata.tables

    def test_peers_table_registered(self):
        assert "monitoring_session_peers" in Base.metadata.tables

    def test_sessions_table_columns(self):
        cols = {c.name for c in Base.metadata.tables["monitoring_sessions"].columns}
        assert cols == {"id", "terminal_id", "label", "started_at", "ended_at"}

    def test_peers_table_columns(self):
        cols = {c.name for c in Base.metadata.tables["monitoring_session_peers"].columns}
        assert cols == {"session_id", "peer_terminal_id"}


class TestSessionInsert:
    def test_insert_session_with_all_fields(self, db_session):
        started = datetime(2026, 4, 18, 10, 0, 0)
        ended = datetime(2026, 4, 18, 11, 0, 0)
        s = MonitoringSessionModel(
            id="sess-1",
            terminal_id="term-A",
            label="review-v2",
            started_at=started,
            ended_at=ended,
        )
        db_session.add(s)
        db_session.commit()

        fetched = db_session.query(MonitoringSessionModel).filter_by(id="sess-1").one()
        assert fetched.terminal_id == "term-A"
        assert fetched.label == "review-v2"
        assert fetched.started_at == started
        assert fetched.ended_at == ended

    def test_insert_session_with_nullable_fields_unset(self, db_session):
        """label and ended_at are nullable — an active session has no end time and
        may have no label."""
        s = MonitoringSessionModel(
            id="sess-2",
            terminal_id="term-B",
            started_at=datetime.now(),
        )
        db_session.add(s)
        db_session.commit()

        fetched = db_session.query(MonitoringSessionModel).filter_by(id="sess-2").one()
        assert fetched.label is None
        assert fetched.ended_at is None

    def test_session_id_is_primary_key(self, db_session):
        """Duplicate ids must raise."""
        now = datetime.now()
        db_session.add(
            MonitoringSessionModel(id="dup", terminal_id="T", started_at=now)
        )
        db_session.commit()

        db_session.add(
            MonitoringSessionModel(id="dup", terminal_id="T2", started_at=now)
        )
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestPeerInsert:
    def test_insert_peer_referencing_session(self, db_session):
        db_session.add(
            MonitoringSessionModel(id="s1", terminal_id="T", started_at=datetime.now())
        )
        db_session.commit()

        db_session.add(
            MonitoringSessionPeerModel(session_id="s1", peer_terminal_id="P1")
        )
        db_session.commit()

        peers = (
            db_session.query(MonitoringSessionPeerModel)
            .filter_by(session_id="s1")
            .all()
        )
        assert len(peers) == 1
        assert peers[0].peer_terminal_id == "P1"

    def test_multiple_peers_per_session(self, db_session):
        db_session.add(
            MonitoringSessionModel(id="s1", terminal_id="T", started_at=datetime.now())
        )
        db_session.commit()

        for pid in ("P1", "P2", "P3"):
            db_session.add(
                MonitoringSessionPeerModel(session_id="s1", peer_terminal_id=pid)
            )
        db_session.commit()

        peers = (
            db_session.query(MonitoringSessionPeerModel)
            .filter_by(session_id="s1")
            .all()
        )
        assert {p.peer_terminal_id for p in peers} == {"P1", "P2", "P3"}

    def test_composite_primary_key_rejects_duplicates(self, db_session):
        """(session_id, peer_terminal_id) is the PK; can't add the same peer twice."""
        db_session.add(
            MonitoringSessionModel(id="s1", terminal_id="T", started_at=datetime.now())
        )
        db_session.commit()
        db_session.add(
            MonitoringSessionPeerModel(session_id="s1", peer_terminal_id="P1")
        )
        db_session.commit()

        db_session.add(
            MonitoringSessionPeerModel(session_id="s1", peer_terminal_id="P1")
        )
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_same_peer_across_different_sessions_allowed(self, db_session):
        """Composite PK includes session_id, so the same peer can appear in many
        sessions — each pair (session, peer) is independent."""
        for sid in ("s1", "s2"):
            db_session.add(
                MonitoringSessionModel(
                    id=sid, terminal_id="T", started_at=datetime.now()
                )
            )
        db_session.commit()

        for sid in ("s1", "s2"):
            db_session.add(
                MonitoringSessionPeerModel(session_id=sid, peer_terminal_id="P1")
            )
        db_session.commit()

        assert (
            db_session.query(MonitoringSessionPeerModel)
            .filter_by(peer_terminal_id="P1")
            .count()
            == 2
        )


class TestCascadeDelete:
    """Deleting a session must delete its peer rows. The plan specifies this
    explicitly so that `delete_session` doesn't leave orphaned peer rows."""

    def test_delete_session_cascades_to_peers(self, db_session):
        db_session.add(
            MonitoringSessionModel(id="s1", terminal_id="T", started_at=datetime.now())
        )
        db_session.commit()
        for pid in ("P1", "P2"):
            db_session.add(
                MonitoringSessionPeerModel(session_id="s1", peer_terminal_id=pid)
            )
        db_session.commit()
        assert (
            db_session.query(MonitoringSessionPeerModel)
            .filter_by(session_id="s1")
            .count()
            == 2
        )

        # Delete via raw SQL to exercise DB-level CASCADE, not ORM relationship cascade
        db_session.query(MonitoringSessionModel).filter_by(id="s1").delete(
            synchronize_session=False
        )
        db_session.commit()

        assert (
            db_session.query(MonitoringSessionPeerModel)
            .filter_by(session_id="s1")
            .count()
            == 0
        )

    def test_peers_for_one_session_unaffected_by_deleting_another(self, db_session):
        for sid in ("keep", "gone"):
            db_session.add(
                MonitoringSessionModel(
                    id=sid, terminal_id="T", started_at=datetime.now()
                )
            )
        db_session.commit()
        for sid in ("keep", "gone"):
            db_session.add(
                MonitoringSessionPeerModel(session_id=sid, peer_terminal_id="P1")
            )
        db_session.commit()

        db_session.query(MonitoringSessionModel).filter_by(id="gone").delete(
            synchronize_session=False
        )
        db_session.commit()

        remaining = db_session.query(MonitoringSessionPeerModel).all()
        assert len(remaining) == 1
        assert remaining[0].session_id == "keep"


class TestForeignKeyConstraint:
    def test_peer_with_unknown_session_id_rejected(self, db_session):
        """Must not be able to insert a peer row referencing a session that
        doesn't exist."""
        db_session.add(
            MonitoringSessionPeerModel(session_id="does-not-exist", peer_terminal_id="P1")
        )
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestProductionEngineForeignKeyEnforcement:
    """SQLite disables FK enforcement by default. The production engine must
    turn it on via a connect-event listener, otherwise CASCADE and FK constraint
    checks silently no-op in prod even though the test fixture (which enables
    the PRAGMA explicitly) passes.

    This test directly inspects the module-level engine so the pragma hook
    cannot regress silently.
    """

    def test_foreign_keys_pragma_enabled_on_production_engine(self):
        from cli_agent_orchestrator.clients.database import engine

        with engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
            assert result == 1, (
                "Production engine must have foreign_keys=ON; otherwise "
                "ON DELETE CASCADE on monitoring_session_peers will not fire."
            )

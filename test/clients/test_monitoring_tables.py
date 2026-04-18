"""Tests for monitoring sessions schema.

Revised for the single-session model: the ``monitoring_session_peers`` table
has been dropped along with all session-level peer scoping. Sessions now
record everything and peer filtering is a query-time concern.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients.database import Base, MonitoringSessionModel


@pytest.fixture
def db_session():
    """In-memory SQLite session with FK enforcement on."""
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
    def test_sessions_table_registered(self):
        assert "monitoring_sessions" in Base.metadata.tables

    def test_peers_table_no_longer_registered(self):
        # The peer-scoping concept was removed; a stale table registration
        # here would mean the ORM still thinks the column/table is live.
        assert "monitoring_session_peers" not in Base.metadata.tables

    def test_sessions_table_columns(self):
        cols = {c.name for c in Base.metadata.tables["monitoring_sessions"].columns}
        assert cols == {"id", "terminal_id", "label", "started_at", "ended_at"}


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


class TestProductionEngineForeignKeyEnforcement:
    """The FK pragma is kept even though monitoring no longer has an FK —
    other future schemas will benefit, and disabling it would be a silent
    regression if FK constraints are added back."""

    def test_foreign_keys_pragma_enabled_on_production_engine(self):
        from cli_agent_orchestrator.clients.database import engine

        with engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
            assert result == 1


class TestMigrationDropsObsoletePeerTable:
    """The peer table existed in earlier releases. The migration hook in
    ``init_db`` drops it if present; new DBs never had it."""

    def test_migration_drops_peer_table_when_present(self, tmp_path, monkeypatch):
        import sqlite3

        from cli_agent_orchestrator.clients import database as db_module

        db_path = tmp_path / "legacy.db"
        # Simulate an older DB that still has the peer table
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE monitoring_session_peers ("
            "session_id TEXT NOT NULL, "
            "peer_terminal_id TEXT NOT NULL, "
            "PRIMARY KEY (session_id, peer_terminal_id))"
        )
        conn.commit()
        conn.close()

        # Point the migration at the legacy file
        monkeypatch.setattr(
            "cli_agent_orchestrator.constants.DATABASE_FILE", db_path
        )
        db_module._migrate_drop_monitoring_session_peers()

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='monitoring_session_peers'"
        )
        assert cursor.fetchone() is None
        conn.close()

    def test_migration_is_noop_when_table_absent(self, tmp_path, monkeypatch):
        """Fresh DBs should not trip the migration path."""
        from cli_agent_orchestrator.clients import database as db_module

        db_path = tmp_path / "fresh.db"
        # Touch the file but no table in it
        import sqlite3

        sqlite3.connect(str(db_path)).close()

        monkeypatch.setattr(
            "cli_agent_orchestrator.constants.DATABASE_FILE", db_path
        )
        # Should not raise
        db_module._migrate_drop_monitoring_session_peers()

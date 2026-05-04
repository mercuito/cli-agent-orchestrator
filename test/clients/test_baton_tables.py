"""Tests for baton persistence schema."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.models.baton import BatonEventType, BatonStatus


class TestBatonSchemaRegistration:
    def test_baton_tables_registered(self):
        assert "batons" in Base.metadata.tables
        assert "baton_events" in Base.metadata.tables

    def test_baton_table_columns(self):
        cols = {c.name for c in Base.metadata.tables["batons"].columns}
        assert cols == {
            "id",
            "title",
            "status",
            "originator_id",
            "current_holder_id",
            "return_stack_json",
            "expected_next_action",
            "created_at",
            "updated_at",
            "last_nudged_at",
            "completed_at",
        }

    def test_baton_event_table_columns(self):
        cols = {c.name for c in Base.metadata.tables["baton_events"].columns}
        assert cols == {
            "id",
            "baton_id",
            "event_type",
            "actor_id",
            "from_holder_id",
            "to_holder_id",
            "message",
            "created_at",
        }

    def test_status_and_event_type_values_cover_mvp(self):
        assert {status.value for status in BatonStatus} == {
            "active",
            "completed",
            "blocked",
            "canceled",
            "orphaned",
        }
        assert {event_type.value for event_type in BatonEventType} >= {
            "create",
            "pass",
            "return",
            "complete",
            "block",
            "cancel",
            "reassign",
            "orphan",
            "nudge",
        }


class TestBatonMigration:
    def test_migration_creates_baton_tables_on_existing_database(self, tmp_path, monkeypatch):
        db_path = tmp_path / "existing.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)

        db_module._migrate_ensure_baton_tables()

        inspector = inspect(test_engine)
        assert "batons" in inspector.get_table_names()
        assert "baton_events" in inspector.get_table_names()

    def test_migration_is_idempotent(self, tmp_path, monkeypatch):
        db_path = tmp_path / "existing.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)

        db_module._migrate_ensure_baton_tables()
        db_module._migrate_ensure_baton_tables()

        inspector = inspect(test_engine)
        assert inspector.get_table_names().count("batons") == 1
        assert inspector.get_table_names().count("baton_events") == 1

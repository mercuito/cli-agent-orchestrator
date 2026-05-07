"""Tests for localized SQLite migration helpers."""

import pytest

from cli_agent_orchestrator.clients import sqlite_migrations


def test_migration_helpers_rebuild_table_with_quoted_identifier(tmp_path):
    db_path = tmp_path / "migration.db"

    with sqlite_migrations.migration_connection(db_path) as conn:
        conn.execute("CREATE TABLE sample_table (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample_table (id, value) VALUES (1, 'old')")

    with sqlite_migrations.migration_connection(db_path) as conn:
        sqlite_migrations.rebuild_table(
            conn,
            table_name="sample_table",
            create_sql="""
                CREATE TABLE sample_table (
                    id INTEGER PRIMARY KEY,
                    value TEXT NOT NULL,
                    migrated INTEGER NOT NULL
                )
            """,
            copy_sql="""
                INSERT INTO sample_table (id, value, migrated)
                SELECT old.id, old.value, 1
                FROM {old_table} AS old
            """,
        )

    with sqlite_migrations.migration_connection(db_path) as conn:
        row = conn.execute("SELECT id, value, migrated FROM sample_table").fetchone()

    assert row == (1, "old", 1)


def test_migration_helpers_reject_dynamic_identifiers(tmp_path):
    db_path = tmp_path / "migration.db"

    with sqlite_migrations.migration_connection(db_path) as conn:
        with pytest.raises(ValueError, match="invalid SQLite identifier"):
            sqlite_migrations.table_columns(conn, "sample; DROP TABLE sample")

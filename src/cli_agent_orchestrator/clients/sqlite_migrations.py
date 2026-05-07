"""Small SQLite schema-migration helpers.

This module owns raw ``sqlite3`` schema mechanics for CAO's lightweight local
database. Application reads and writes should stay in SQLAlchemy owner
surfaces; helpers here are intentionally limited to startup migrations.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Sequence

Connection = sqlite3.Connection
ColumnInfo = tuple[int, str, str, int, object, int]
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@contextmanager
def migration_connection(database_file: Path) -> Iterator[Connection]:
    """Open a migration connection and close it after commit/rollback."""

    conn = sqlite3.connect(str(database_file))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def table_exists(conn: Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    return row is not None


def table_column_info(conn: Connection, table_name: str) -> dict[str, ColumnInfo]:
    return {
        str(row[1]): row
        for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    }


def table_columns(conn: Connection, table_name: str) -> set[str]:
    return set(table_column_info(conn, table_name))


def add_column_if_missing(
    conn: Connection, table_name: str, column_name: str, column_definition: str
) -> bool:
    """Add one column when absent and return whether the schema changed."""

    if column_name in table_columns(conn, table_name):
        return False
    conn.execute(f"ALTER TABLE {_quote_identifier(table_name)} ADD COLUMN {column_definition}")
    return True


@contextmanager
def foreign_keys_disabled(conn: Connection) -> Iterator[None]:
    """Temporarily disable FK enforcement for SQLite table rebuild operations."""

    conn.commit()
    enabled = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if enabled:
            conn.execute("PRAGMA foreign_keys=ON")


def rebuild_table(
    conn: Connection,
    *,
    table_name: str,
    create_sql: str,
    copy_sql: Optional[str] = None,
    old_table_name: Optional[str] = None,
) -> None:
    """Rebuild a table with a new shape, optionally copying compatible rows."""

    old_name = old_table_name or f"{table_name}_old"
    table_identifier = _quote_identifier(table_name)
    old_identifier = _quote_identifier(old_name)
    with foreign_keys_disabled(conn):
        conn.execute(f"DROP TABLE IF EXISTS {old_identifier}")
        conn.execute(f"ALTER TABLE {table_identifier} RENAME TO {old_identifier}")
        conn.execute(create_sql)
        if copy_sql is not None:
            conn.execute(copy_sql.format(old_table=old_identifier))
        conn.execute(f"DROP TABLE {old_identifier}")


def drop_tables_if_exist(conn: Connection, table_names: Sequence[str]) -> int:
    """Drop migration-only tables and return the number that existed."""

    dropped = 0
    with foreign_keys_disabled(conn):
        for table_name in table_names:
            if table_exists(conn, table_name):
                conn.execute(f"DROP TABLE {_quote_identifier(table_name)}")
                dropped += 1
    return dropped


def _quote_identifier(value: str) -> str:
    """Quote a static migration identifier after validating its shape."""

    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"invalid SQLite identifier: {value!r}")
    return f'"{value}"'

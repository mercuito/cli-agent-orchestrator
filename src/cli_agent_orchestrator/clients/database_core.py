"""Shared SQLAlchemy primitives for CAO persistence."""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from cli_agent_orchestrator.constants import DATABASE_URL, DB_DIR

Base: Any = declarative_base()

DB_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_conn, _conn_record):
    """Enable SQLite FK checks per connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

"""Durable Linear monitor watermark persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, cast

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from cli_agent_orchestrator.clients.database_core import Base


class LinearMonitorWatermarkModel(Base):
    """Per-presence Linear monitor event-time watermark."""

    __tablename__ = "linear_monitor_watermarks"
    __table_args__ = (UniqueConstraint("presence_id", "app_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    presence_id = Column(String, nullable=False)
    app_key = Column(String, nullable=False)
    watermark_updated_at = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


@dataclass(frozen=True)
class LinearMonitorWatermark:
    """Stored event-time watermark for one Linear presence/app key."""

    id: int
    presence_id: str
    app_key: str
    watermark_updated_at: str
    created_at: datetime
    updated_at: datetime


def _from_row(row: LinearMonitorWatermarkModel) -> LinearMonitorWatermark:
    return LinearMonitorWatermark(
        id=cast(int, row.id),
        presence_id=cast(str, row.presence_id),
        app_key=cast(str, row.app_key),
        watermark_updated_at=cast(str, row.watermark_updated_at),
        created_at=cast(datetime, row.created_at),
        updated_at=cast(datetime, row.updated_at),
    )


def _require_key(presence_id: str, app_key: str) -> None:
    if not presence_id:
        raise ValueError("presence_id is required")
    if not app_key:
        raise ValueError("app_key is required")


def _session_local():
    from cli_agent_orchestrator.clients import database as db_module

    return db_module.SessionLocal


def get_watermark(
    *,
    presence_id: str,
    app_key: str,
    db: Optional[Session] = None,
) -> Optional[LinearMonitorWatermark]:
    """Read the Linear monitor watermark for one presence/app key."""

    def _get(session: Session) -> Optional[LinearMonitorWatermark]:
        _require_key(presence_id, app_key)
        row = (
            session.query(LinearMonitorWatermarkModel)
            .filter(
                LinearMonitorWatermarkModel.presence_id == presence_id,
                LinearMonitorWatermarkModel.app_key == app_key,
            )
            .first()
        )
        return _from_row(row) if row is not None else None

    if db is not None:
        return _get(db)

    with _session_local()() as session:
        return _get(session)


def upsert_watermark(
    *,
    presence_id: str,
    app_key: str,
    watermark_updated_at: str,
    db: Optional[Session] = None,
) -> LinearMonitorWatermark:
    """Create or update the Linear monitor watermark for one presence/app key."""

    def _upsert(session: Session) -> LinearMonitorWatermark:
        _require_key(presence_id, app_key)
        if not watermark_updated_at:
            raise ValueError("watermark_updated_at is required")
        now = datetime.now()
        session.execute(
            sqlite_insert(LinearMonitorWatermarkModel)
            .values(
                presence_id=presence_id,
                app_key=app_key,
                watermark_updated_at=watermark_updated_at,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["presence_id", "app_key"])
        )
        row = (
            session.query(LinearMonitorWatermarkModel)
            .filter(
                LinearMonitorWatermarkModel.presence_id == presence_id,
                LinearMonitorWatermarkModel.app_key == app_key,
            )
            .first()
        )
        if row is None:
            raise RuntimeError("Linear monitor watermark insert did not create or find a row")
        mutable_row = cast(Any, row)
        mutable_row.watermark_updated_at = watermark_updated_at
        mutable_row.updated_at = now
        session.flush()
        session.refresh(row)
        return _from_row(row)

    if db is not None:
        return _upsert(db)

    with _session_local()() as session:
        record = _upsert(session)
        session.commit()
        return record

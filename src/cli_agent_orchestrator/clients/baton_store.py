"""Baton persistence."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from cli_agent_orchestrator.clients.database_core import Base
from cli_agent_orchestrator.models.baton import Baton, BatonEvent, BatonEventType, BatonStatus


class BatonModel(Base):
    """SQLAlchemy model for baton state."""

    __tablename__ = "batons"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False)
    originator_id = Column(String, nullable=False)
    current_holder_id = Column(String, nullable=True)
    return_stack_json = Column(String, nullable=False, default="[]")
    expected_next_action = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
    last_nudged_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class BatonEventModel(Base):
    """SQLAlchemy model for baton audit events."""

    __tablename__ = "baton_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    baton_id = Column(String, ForeignKey("batons.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    from_holder_id = Column(String, nullable=True)
    to_holder_id = Column(String, nullable=True)
    message = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


def _session_local():
    from cli_agent_orchestrator.clients import database as db_module

    return db_module.SessionLocal


def baton_from_model(row: BatonModel) -> Baton:
    """Convert a SQLAlchemy baton row to its typed domain model."""
    return Baton(
        id=row.id,
        title=row.title,
        status=BatonStatus(row.status),
        originator_id=row.originator_id,
        current_holder_id=row.current_holder_id,
        return_stack=json.loads(row.return_stack_json or "[]"),
        expected_next_action=row.expected_next_action,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_nudged_at=row.last_nudged_at,
        completed_at=row.completed_at,
    )


def baton_event_from_model(row: BatonEventModel) -> BatonEvent:
    """Convert a SQLAlchemy baton event row to its typed domain model."""
    return BatonEvent(
        id=row.id,
        baton_id=row.baton_id,
        event_type=BatonEventType(row.event_type),
        actor_id=row.actor_id,
        from_holder_id=row.from_holder_id,
        to_holder_id=row.to_holder_id,
        message=row.message,
        created_at=row.created_at,
    )


def get_baton_record(baton_id: str) -> Optional[Baton]:
    """Get a baton by ID."""
    with _session_local()() as db:
        row = db.query(BatonModel).filter(BatonModel.id == baton_id).first()
        if row is None:
            return None
        return baton_from_model(row)


def list_batons(
    *,
    status: Optional[BatonStatus] = None,
    holder_id: Optional[str] = None,
    originator_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Baton]:
    """List batons with operator-facing filters, newest update first."""
    with _session_local()() as db:
        query = db.query(BatonModel)
        if status is not None:
            query = query.filter(BatonModel.status == status.value)
        if holder_id is not None:
            query = query.filter(BatonModel.current_holder_id == holder_id)
        if originator_id is not None:
            query = query.filter(BatonModel.originator_id == originator_id)

        rows = (
            query.order_by(BatonModel.updated_at.desc(), BatonModel.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [baton_from_model(row) for row in rows]


def list_batons_held_by(holder_id: str, status: Optional[BatonStatus] = None) -> List[Baton]:
    """List batons currently held by ``holder_id``, newest update first."""
    with _session_local()() as db:
        query = db.query(BatonModel).filter(BatonModel.current_holder_id == holder_id)
        if status is not None:
            query = query.filter(BatonModel.status == status.value)
        rows = query.order_by(BatonModel.updated_at.desc(), BatonModel.created_at.desc()).all()
        return [baton_from_model(row) for row in rows]


def list_baton_events(baton_id: str) -> List[BatonEvent]:
    """List baton audit events ordered oldest first."""
    with _session_local()() as db:
        rows = (
            db.query(BatonEventModel)
            .filter(BatonEventModel.baton_id == baton_id)
            .order_by(BatonEventModel.created_at.asc(), BatonEventModel.id.asc())
            .all()
        )
        return [baton_event_from_model(row) for row in rows]

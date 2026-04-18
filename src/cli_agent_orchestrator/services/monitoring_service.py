"""Monitoring sessions service.

A monitoring session is a recording window over the inbox table, scoped to
a terminal. See ``docs/plans/monitoring-sessions.md`` for the design.

Model (single-session, query-time filtering):
  - At most one active session per terminal at any time. ``create_session``
    is idempotent — if an active session exists for the target terminal, it
    is returned unchanged rather than a duplicate being created.
  - Sessions do not carry peer sets or time scopes. They capture all inbox
    activity involving the terminal for the session's lifetime.
  - Filtering (by peer, by time sub-window) happens at read time via
    ``get_session_messages`` kwargs.

This module is the single point that knows how to translate session
metadata into message queries. HTTP and CLI layers are thin wrappers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import (
    InboxModel,
    MonitoringSessionModel,
)


class MonitoringError(Exception):
    """Base class for monitoring-service errors."""


class SessionNotFound(MonitoringError):
    """Raised when a session_id does not exist."""


class SessionAlreadyEnded(MonitoringError):
    """Raised on attempts to end an already-ended session.

    ``create_session`` does NOT raise when the target terminal already has
    an active session — it returns the existing one (idempotent). This
    exception is specifically for the ``end_session`` double-close case,
    where the operator wants to know they raced themselves.
    """


def _session_to_dict(session: MonitoringSessionModel) -> Dict[str, Any]:
    return {
        "id": session.id,
        "terminal_id": session.terminal_id,
        "label": session.label,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "status": "ended" if session.ended_at is not None else "active",
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_session(
    terminal_id: str,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """Start monitoring a terminal. Idempotent w.r.t. the active state.

    If ``terminal_id`` already has an active session (``ended_at IS NULL``),
    the existing session is returned unchanged — the label argument is
    ignored in that case. This matches the "recording or not" mental
    model: clicking "Monitor" when already recording is a no-op, not an
    error.
    """
    with db_module.SessionLocal() as db:
        existing = (
            db.query(MonitoringSessionModel)
            .filter(
                MonitoringSessionModel.terminal_id == terminal_id,
                MonitoringSessionModel.ended_at.is_(None),
            )
            .first()
        )
        if existing is not None:
            return _session_to_dict(existing)

        session_row = MonitoringSessionModel(
            id=str(uuid.uuid4()),
            terminal_id=terminal_id,
            label=label,
            started_at=datetime.now(),
            ended_at=None,
        )
        db.add(session_row)
        db.commit()
        db.refresh(session_row)
        return _session_to_dict(session_row)


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with db_module.SessionLocal() as db:
        row = (
            db.query(MonitoringSessionModel)
            .filter(MonitoringSessionModel.id == session_id)
            .first()
        )
        if row is None:
            return None
        return _session_to_dict(row)


def end_session(session_id: str) -> Dict[str, Any]:
    """Stamp ``ended_at=now`` on an active session. Raises if already ended."""
    with db_module.SessionLocal() as db:
        row = (
            db.query(MonitoringSessionModel)
            .filter(MonitoringSessionModel.id == session_id)
            .first()
        )
        if row is None:
            raise SessionNotFound(session_id)
        if row.ended_at is not None:
            raise SessionAlreadyEnded(session_id)
        row.ended_at = datetime.now()
        db.commit()
        db.refresh(row)
        return _session_to_dict(row)


def delete_session(session_id: str) -> None:
    """Delete a session row. Does not delete any inbox messages — sessions
    are only recording windows, not owners of the captured data."""
    with db_module.SessionLocal() as db:
        row = (
            db.query(MonitoringSessionModel)
            .filter(MonitoringSessionModel.id == session_id)
            .first()
        )
        if row is None:
            raise SessionNotFound(session_id)
        db.delete(row)
        db.commit()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_sessions(
    terminal_id: Optional[str] = None,
    status: Optional[str] = None,
    label: Optional[str] = None,
    started_after: Optional[datetime] = None,
    started_before: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List sessions with optional filters. Ordered by started_at DESC."""
    with db_module.SessionLocal() as db:
        q = db.query(MonitoringSessionModel)

        if terminal_id is not None:
            q = q.filter(MonitoringSessionModel.terminal_id == terminal_id)

        if status == "active":
            q = q.filter(MonitoringSessionModel.ended_at.is_(None))
        elif status == "ended":
            q = q.filter(MonitoringSessionModel.ended_at.isnot(None))

        if label is not None:
            q = q.filter(MonitoringSessionModel.label == label)

        if started_after is not None:
            q = q.filter(MonitoringSessionModel.started_at >= started_after)
        if started_before is not None:
            q = q.filter(MonitoringSessionModel.started_at <= started_before)

        q = q.order_by(MonitoringSessionModel.started_at.desc())
        q = q.limit(limit).offset(offset)

        return [_session_to_dict(r) for r in q.all()]


# ---------------------------------------------------------------------------
# Messages query — filters apply at read time
# ---------------------------------------------------------------------------


def get_session_messages(
    session_id: str,
    peers: Optional[List[str]] = None,
    started_after: Optional[datetime] = None,
    started_before: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Return inbox messages captured by the session, with optional filters.

    Base filter (always applied):
      (sender = terminal OR receiver = terminal)
      AND created_at >= session.started_at
      AND (session.ended_at IS NULL OR created_at <= session.ended_at)

    Optional query-time filters:
      ``peers``: OR-semantics over both sides. A message matches if
        sender ∈ peers OR receiver ∈ peers. Empty list = no peer filter
        (capture all).
      ``started_after`` / ``started_before``: further narrow the time
        window inside the session's bounds. Useful for extracting a single
        step's log from a longer recording.
    """
    with db_module.SessionLocal() as db:
        session_row = (
            db.query(MonitoringSessionModel)
            .filter(MonitoringSessionModel.id == session_id)
            .first()
        )
        if session_row is None:
            raise SessionNotFound(session_id)

        q = db.query(InboxModel).filter(
            or_(
                InboxModel.sender_id == session_row.terminal_id,
                InboxModel.receiver_id == session_row.terminal_id,
            )
        )

        if peers:
            q = q.filter(
                or_(
                    InboxModel.sender_id.in_(peers),
                    InboxModel.receiver_id.in_(peers),
                )
            )

        q = q.filter(InboxModel.created_at >= session_row.started_at)
        if session_row.ended_at is not None:
            q = q.filter(InboxModel.created_at <= session_row.ended_at)

        # Apply caller-provided sub-window on top of the session window
        if started_after is not None:
            q = q.filter(InboxModel.created_at >= started_after)
        if started_before is not None:
            q = q.filter(InboxModel.created_at <= started_before)

        q = q.order_by(InboxModel.created_at.asc())

        return [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "receiver_id": m.receiver_id,
                "message": m.message,
                "status": m.status,
                "created_at": m.created_at,
            }
            for m in q.all()
        ]

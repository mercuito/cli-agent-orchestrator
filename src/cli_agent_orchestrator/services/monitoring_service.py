"""Monitoring sessions service.

A monitoring session is a recording window over the inbox table, scoped to
a durable CAO agent.

Model (single-session, query-time filtering):
  - At most one active session per agent at any time. ``create_session``
    is idempotent — if an active session exists for the target agent, it
    is returned unchanged rather than a duplicate being created.
  - Sessions do not carry peer sets or time scopes. They capture all inbox
    activity involving the agent for the session's lifetime.
  - Filtering (by peer, by time sub-window) happens at read time via
    ``get_session_messages`` kwargs.

This module is the single point that knows how to translate session
metadata into message queries. HTTP and CLI layers are thin wrappers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import MonitoringSessionModel
from cli_agent_orchestrator.inbox import list_notifications_involving_agent


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
        "agent_id": session.agent_id,
        "label": session.label,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "status": "ended" if session.ended_at is not None else "active",
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_session(
    agent_id: str,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """Start monitoring an agent. Idempotent w.r.t. the active state.

    If ``agent_id`` already has an active session (``ended_at IS NULL``),
    the existing session is returned unchanged — the label argument is
    ignored in that case. This matches the "recording or not" mental
    model: clicking "Monitor" when already recording is a no-op, not an
    error.
    """
    with db_module.SessionLocal() as db:
        existing = (
            db.query(MonitoringSessionModel)
            .filter(
                MonitoringSessionModel.agent_id == agent_id,
                MonitoringSessionModel.ended_at.is_(None),
            )
            .first()
        )
        if existing is not None:
            return _session_to_dict(existing)

        session_row = MonitoringSessionModel(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
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
            db.query(MonitoringSessionModel).filter(MonitoringSessionModel.id == session_id).first()
        )
        if row is None:
            return None
        return _session_to_dict(row)


def end_session(session_id: str) -> Dict[str, Any]:
    """Stamp ``ended_at=now`` on an active session. Raises if already ended."""
    with db_module.SessionLocal() as db:
        row = (
            db.query(MonitoringSessionModel).filter(MonitoringSessionModel.id == session_id).first()
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
            db.query(MonitoringSessionModel).filter(MonitoringSessionModel.id == session_id).first()
        )
        if row is None:
            raise SessionNotFound(session_id)
        db.delete(row)
        db.commit()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_sessions(
    agent_id: Optional[str] = None,
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

        if agent_id is not None:
            q = q.filter(MonitoringSessionModel.agent_id == agent_id)

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
      (sender = session agent OR receiver = session agent)
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
            db.query(MonitoringSessionModel).filter(MonitoringSessionModel.id == session_id).first()
        )
        if session_row is None:
            raise SessionNotFound(session_id)

        session_agent_id = str(session_row.agent_id)

        window_started_at = cast(datetime, session_row.started_at)
        window_ended_at = cast(Optional[datetime], session_row.ended_at)
        if started_after is not None and started_after > window_started_at:
            window_started_at = started_after
        if started_before is not None and (
            window_ended_at is None or started_before < window_ended_at
        ):
            window_ended_at = started_before

        return [
            {
                "id": notification.id,
                "notification_id": notification.id,
                "sender_agent_id": notification.sender_agent_id,
                "receiver_agent_id": notification.receiver_agent_id,
                "body": notification.body,
                "status": notification.status,
                "created_at": notification.created_at,
            }
            for notification in list_notifications_involving_agent(
                session_agent_id,
                db=db,
                peers=peers,
                started_at=window_started_at,
                ended_at=window_ended_at,
            )
        ]

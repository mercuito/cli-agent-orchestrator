"""Monitoring sessions service.

A monitoring session is a query window over the inbox table, scoped to a
monitored terminal and (optionally) a peer set. See
``docs/plans/monitoring-sessions.md`` for the design rationale.

This module is the single point that knows how to translate session metadata
into message queries. The HTTP and CLI layers are thin wrappers on top.
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
    MonitoringSessionPeerModel,
)


class MonitoringError(Exception):
    """Base class for monitoring-service errors."""


class SessionNotFound(MonitoringError):
    """Raised when a session_id does not exist."""


class SessionAlreadyEnded(MonitoringError):
    """Raised on mutation of an ended session (end/add_peers/remove_peer).

    Design decision: ended sessions are immutable windows. Procedures that want
    to change the peer set after a window closed should start a new session.
    """


def _session_to_dict(session: MonitoringSessionModel, peer_ids: List[str]) -> Dict[str, Any]:
    return {
        "id": session.id,
        "terminal_id": session.terminal_id,
        "label": session.label,
        "peer_terminal_ids": sorted(peer_ids),
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "status": "ended" if session.ended_at is not None else "active",
    }


def _peers_for(db, session_id: str) -> List[str]:
    rows = (
        db.query(MonitoringSessionPeerModel)
        .filter(MonitoringSessionPeerModel.session_id == session_id)
        .all()
    )
    return [r.peer_terminal_id for r in rows]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_session(
    terminal_id: str,
    peer_terminal_ids: Optional[List[str]] = None,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new monitoring session in the active state.

    ``peer_terminal_ids`` of None or [] means "capture all I/O of terminal_id"
    (unscoped). Duplicates in the input are deduplicated.
    """
    session_id = str(uuid.uuid4())
    now = datetime.now()
    unique_peers = sorted(set(peer_terminal_ids or []))

    with db_module.SessionLocal() as db:
        session_row = MonitoringSessionModel(
            id=session_id,
            terminal_id=terminal_id,
            label=label,
            started_at=now,
            ended_at=None,
        )
        db.add(session_row)
        for peer_id in unique_peers:
            db.add(
                MonitoringSessionPeerModel(
                    session_id=session_id, peer_terminal_id=peer_id
                )
            )
        db.commit()
        db.refresh(session_row)
        return _session_to_dict(session_row, unique_peers)


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with db_module.SessionLocal() as db:
        row = (
            db.query(MonitoringSessionModel)
            .filter(MonitoringSessionModel.id == session_id)
            .first()
        )
        if row is None:
            return None
        return _session_to_dict(row, _peers_for(db, session_id))


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
        return _session_to_dict(row, _peers_for(db, session_id))


def delete_session(session_id: str) -> None:
    """Delete a session and its peer rows (via FK CASCADE).

    Does not delete any messages — sessions are only query windows.
    """
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
# Peers
# ---------------------------------------------------------------------------


def add_peers(session_id: str, peer_terminal_ids: List[str]) -> None:
    """Add peers to an active session. Idempotent: existing peers are skipped."""
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

        existing = set(_peers_for(db, session_id))
        for peer_id in set(peer_terminal_ids):
            if peer_id in existing:
                continue
            db.add(
                MonitoringSessionPeerModel(
                    session_id=session_id, peer_terminal_id=peer_id
                )
            )
        db.commit()


def remove_peer(session_id: str, peer_terminal_id: str) -> None:
    """Remove a peer from an active session. No-op if the peer isn't present."""
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

        db.query(MonitoringSessionPeerModel).filter(
            MonitoringSessionPeerModel.session_id == session_id,
            MonitoringSessionPeerModel.peer_terminal_id == peer_terminal_id,
        ).delete(synchronize_session=False)
        db.commit()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_sessions(
    terminal_id: Optional[str] = None,
    peer_terminal_id: Optional[str] = None,
    involves: Optional[str] = None,
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

        if peer_terminal_id is not None:
            peer_subq = (
                db.query(MonitoringSessionPeerModel.session_id)
                .filter(MonitoringSessionPeerModel.peer_terminal_id == peer_terminal_id)
                .subquery()
            )
            q = q.filter(MonitoringSessionModel.id.in_(peer_subq))

        if involves is not None:
            peer_subq = (
                db.query(MonitoringSessionPeerModel.session_id)
                .filter(MonitoringSessionPeerModel.peer_terminal_id == involves)
                .subquery()
            )
            q = q.filter(
                or_(
                    MonitoringSessionModel.terminal_id == involves,
                    MonitoringSessionModel.id.in_(peer_subq),
                )
            )

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

        rows = q.all()
        return [_session_to_dict(r, _peers_for(db, r.id)) for r in rows]


# ---------------------------------------------------------------------------
# Messages query
# ---------------------------------------------------------------------------


def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """Return inbox messages in the session's window, ordered by created_at ASC.

    Filter: (sender=terminal_id OR receiver=terminal_id)
      AND (no peers configured OR sender in peers OR receiver in peers)
      AND created_at >= started_at
      AND (ended_at IS NULL OR created_at <= ended_at)

    Peer filter is retroactive: evaluated at query time against the current
    peer set, so adding/removing peers affects visibility of historical
    messages in the window.
    """
    with db_module.SessionLocal() as db:
        session_row = (
            db.query(MonitoringSessionModel)
            .filter(MonitoringSessionModel.id == session_id)
            .first()
        )
        if session_row is None:
            raise SessionNotFound(session_id)

        peers = _peers_for(db, session_id)

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

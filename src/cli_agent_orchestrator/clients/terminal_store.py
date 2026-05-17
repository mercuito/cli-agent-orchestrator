"""Terminal metadata persistence."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.exc import IntegrityError

from cli_agent_orchestrator.clients.database_core import Base

logger = logging.getLogger(__name__)


class TerminalModel(Base):
    """SQLAlchemy model for terminal metadata only."""

    __tablename__ = "terminals"
    __table_args__ = (Index("uq_terminals_agent_id", "agent_id", unique=True),)

    id = Column(String, primary_key=True)  # "abc123ef"
    tmux_session = Column(String, nullable=False)  # "cao-session-name"
    tmux_window = Column(String, nullable=False)  # "window-name"
    provider = Column(String, nullable=False)  # "q_cli", "claude_code"
    agent_id = Column(String, nullable=False)  # Durable CAO agent id
    workspace_context_id = Column(String, nullable=False)  # CAO workspace context
    allowed_tools = Column(String, nullable=True)  # JSON-encoded runtime capability list
    last_active = Column(DateTime, default=datetime.now)


class TerminalAgentAlreadyRunningError(RuntimeError):
    """Raised when a durable agent already has a terminal manifestation."""

    def __init__(self, agent_id: str, terminal_id: str) -> None:
        self.agent_id = agent_id
        self.terminal_id = terminal_id
        super().__init__(f"Agent {agent_id!r} already has a live terminal: {terminal_id}")


def _session_local():
    from cli_agent_orchestrator.clients import database as db_module

    return db_module.SessionLocal


def create_terminal(
    terminal_id: str,
    tmux_session: str,
    tmux_window: str,
    provider: str,
    agent_id: str,
    workspace_context_id: str,
    allowed_tools: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create terminal metadata record."""
    with _session_local()() as db:
        terminal = TerminalModel(
            id=terminal_id,
            tmux_session=tmux_session,
            tmux_window=tmux_window,
            provider=provider,
            agent_id=agent_id,
            workspace_context_id=workspace_context_id,
            allowed_tools=json.dumps(allowed_tools) if allowed_tools else None,
        )
        db.add(terminal)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.query(TerminalModel).filter(TerminalModel.agent_id == agent_id).first()
            if existing is not None:
                raise TerminalAgentAlreadyRunningError(agent_id, str(existing.id))
            raise
        return {
            "id": terminal.id,
            "tmux_session": terminal.tmux_session,
            "tmux_window": terminal.tmux_window,
            "provider": terminal.provider,
            "agent_id": terminal.agent_id,
            "workspace_context_id": terminal.workspace_context_id,
            "allowed_tools": allowed_tools,
        }


def get_terminal_metadata(terminal_id: str) -> Optional[Dict[str, Any]]:
    """Get terminal metadata by ID."""
    with _session_local()() as db:
        terminal = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).first()
        if not terminal:
            logger.warning(f"Terminal metadata not found for terminal_id: {terminal_id}")
            return None
        logger.debug(
            f"Retrieved terminal metadata for {terminal_id}: provider={terminal.provider}, session={terminal.tmux_session}"
        )
        allowed_tools = json.loads(terminal.allowed_tools) if terminal.allowed_tools else None
        return {
            "id": terminal.id,
            "tmux_session": terminal.tmux_session,
            "tmux_window": terminal.tmux_window,
            "provider": terminal.provider,
            "agent_id": terminal.agent_id,
            "workspace_context_id": terminal.workspace_context_id,
            "allowed_tools": allowed_tools,
            "last_active": terminal.last_active,
        }


def list_terminals_by_session(tmux_session: str) -> List[Dict[str, Any]]:
    """List all terminals in a tmux session."""
    with _session_local()() as db:
        terminals = db.query(TerminalModel).filter(TerminalModel.tmux_session == tmux_session).all()
        return [
            {
                "id": t.id,
                "tmux_session": t.tmux_session,
                "tmux_window": t.tmux_window,
                "provider": t.provider,
                "agent_id": t.agent_id,
                "workspace_context_id": t.workspace_context_id,
                "last_active": t.last_active,
            }
            for t in terminals
        ]


def list_terminals_by_agent(agent_id: str) -> List[Dict[str, Any]]:
    """List terminal manifestations mapped to a durable CAO agent."""
    with _session_local()() as db:
        terminals = db.query(TerminalModel).filter(TerminalModel.agent_id == agent_id).all()
        return [_terminal_model_to_metadata(t) for t in terminals]


def list_terminals_by_agent_and_context(
    agent_id: str,
    workspace_context_id: str,
) -> List[Dict[str, Any]]:
    """List terminal manifestations mapped to one agent/context pair."""
    with _session_local()() as db:
        terminals = (
            db.query(TerminalModel)
            .filter(
                TerminalModel.agent_id == agent_id,
                TerminalModel.workspace_context_id == workspace_context_id,
            )
            .all()
        )
        return [_terminal_model_to_metadata(t) for t in terminals]


def update_last_active(terminal_id: str) -> bool:
    """Update last active timestamp."""
    with _session_local()() as db:
        terminal = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).first()
        if terminal:
            terminal.last_active = datetime.now()
            db.commit()
            return True
        return False


def list_all_terminals() -> List[Dict[str, Any]]:
    """List all terminals."""
    with _session_local()() as db:
        terminals = db.query(TerminalModel).all()
        return [
            {
                "id": t.id,
                "tmux_session": t.tmux_session,
                "tmux_window": t.tmux_window,
                "provider": t.provider,
                "agent_id": t.agent_id,
                "workspace_context_id": t.workspace_context_id,
                "last_active": t.last_active,
            }
            for t in terminals
        ]


def delete_terminal(terminal_id: str) -> bool:
    """Delete terminal metadata."""
    with _session_local()() as db:
        deleted = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).delete()
        db.commit()
        return bool(deleted > 0)


def delete_terminals_by_session(tmux_session: str) -> int:
    """Delete all terminals in a session."""
    with _session_local()() as db:
        deleted = (
            db.query(TerminalModel).filter(TerminalModel.tmux_session == tmux_session).delete()
        )
        db.commit()
        return int(deleted)


def _terminal_model_to_metadata(terminal: TerminalModel) -> Dict[str, Any]:
    raw_allowed_tools = cast(Optional[str], terminal.allowed_tools)
    allowed_tools = json.loads(raw_allowed_tools) if raw_allowed_tools else None
    return {
        "id": terminal.id,
        "tmux_session": terminal.tmux_session,
        "tmux_window": terminal.tmux_window,
        "provider": terminal.provider,
        "agent_id": terminal.agent_id,
        "workspace_context_id": terminal.workspace_context_id,
        "allowed_tools": allowed_tools,
        "last_active": terminal.last_active,
    }

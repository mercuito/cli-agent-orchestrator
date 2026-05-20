"""Shared collaboration policy checks for terminal-owned service writes."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.orm import Session

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import TerminalModel
from cli_agent_orchestrator.workspaces import (
    WorkspaceConfigError,
    default_workspace_collaboration_manager,
)


def require_terminal_same_team_collaboration(
    sender_id: str,
    receiver_id: str,
    *,
    db: Session | None = None,
) -> None:
    """Require two terminal ids to belong to agents in the same workspace team."""

    sender_metadata = _terminal_metadata(sender_id, db=db)
    if sender_metadata is None:
        raise WorkspaceConfigError(f"Sender terminal not found: {sender_id}")
    receiver_metadata = _terminal_metadata(receiver_id, db=db)
    if receiver_metadata is None:
        raise WorkspaceConfigError(f"Receiver terminal not found: {receiver_id}")
    sender_agent_id = _metadata_agent_id(sender_metadata, terminal_id=sender_id, role="Sender")
    receiver_agent_id = _metadata_agent_id(
        receiver_metadata,
        terminal_id=receiver_id,
        role="Receiver",
    )
    manager = default_workspace_collaboration_manager()
    manager.require_same_team_collaboration(
        sender=manager.agent_registry.get(sender_agent_id),
        receiver=manager.agent_registry.get(receiver_agent_id),
    )


def require_terminal_workspace_team(
    terminal_id: str,
    *,
    db: Session | None = None,
    role: str = "Terminal",
) -> None:
    """Require one terminal to be attached to an agent in a valid workspace team."""

    metadata = _terminal_metadata(terminal_id, db=db)
    if metadata is None:
        raise WorkspaceConfigError(f"{role} terminal not found: {terminal_id}")
    agent_id = _metadata_agent_id(metadata, terminal_id=terminal_id, role=role)
    manager = default_workspace_collaboration_manager()
    agent = manager.agent_registry.get(agent_id)
    if manager.team_for_agent(agent) is None:
        raise WorkspaceConfigError(
            f"{role} terminal {terminal_id} agent {agent.id} has no workspace team"
        )
    manager.workspace_for_agent(agent)


def _terminal_metadata(
    terminal_id: str,
    *,
    db: Session | None,
) -> Mapping[str, object] | None:
    if db is None:
        return db_module.get_terminal_metadata(terminal_id)
    terminal = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).first()
    if terminal is None:
        return None
    return {"agent_id": terminal.agent_id}


def _metadata_agent_id(metadata: Mapping[str, object], *, terminal_id: str, role: str) -> str:
    agent_id = metadata.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise WorkspaceConfigError(f"{role} terminal {terminal_id} has no CAO agent")
    return agent_id.strip()

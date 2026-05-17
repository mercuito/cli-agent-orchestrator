"""Workspace context registry persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, cast

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from cli_agent_orchestrator.clients.database_core import Base

WORKSPACE_CONTEXT_STATUS_ACTIVE = "active"
WORKSPACE_CONTEXT_ROLE_BOUNDARY = "boundary"
WORKSPACE_CONTEXT_ROLE_ATTACHED = "attached"
WORKSPACE_CONTEXT_ROLE_INTERACTION = "interaction"
WORKSPACE_CONTEXT_ROLE_CHILD_WORK_ITEM = "child_work_item"


class WorkspaceContextModel(Base):
    """Logical work boundary shared across provider objects."""

    __tablename__ = "workspace_contexts"

    id = Column(String, primary_key=True)
    resolver_id = Column(String, nullable=False)
    boundary_provider_id = Column(String, nullable=False)
    boundary_object_type = Column(String, nullable=False)
    boundary_object_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default=WORKSPACE_CONTEXT_STATUS_ACTIVE)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


class WorkspaceContextObjectMappingModel(Base):
    """Provider object membership in a workspace context."""

    __tablename__ = "workspace_context_object_mappings"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "object_type",
            "object_id",
            name="uq_workspace_context_object_ref",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_context_id = Column(
        String,
        ForeignKey("workspace_contexts.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id = Column(String, nullable=False)
    object_type = Column(String, nullable=False)
    object_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class ContextWorkspaceModel(Base):
    """Agent-local workspace for one agent in one workspace context."""

    __tablename__ = "context_workspaces"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "workspace_context_id",
            name="uq_context_workspace_agent_context",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False)
    workspace_context_id = Column(
        String,
        ForeignKey("workspace_contexts.id", ondelete="CASCADE"),
        nullable=False,
    )
    root_path = Column(String, nullable=False)
    active_terminal_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


@dataclass(frozen=True)
class WorkspaceContextRecord:
    """Domain record for a logical workspace context."""

    id: str
    resolver_id: str
    boundary_provider_id: str
    boundary_object_type: str
    boundary_object_id: str
    status: str
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WorkspaceContextObjectMappingRecord:
    """Domain record for a provider object to context mapping."""

    id: int
    workspace_context_id: str
    provider_id: str
    object_type: str
    object_id: str
    role: str
    metadata: dict[str, Any] | None
    created_at: datetime


@dataclass(frozen=True)
class ContextWorkspaceRecord:
    """Domain record for an agent-local workspace context."""

    id: int
    agent_id: str
    workspace_context_id: str
    root_path: Path
    active_terminal_id: str | None
    created_at: datetime
    updated_at: datetime


class WorkspaceContextConflictError(ValueError):
    """Raised when provider objects imply conflicting workspace contexts."""


def _session_local():
    from cli_agent_orchestrator.clients import database as db_module

    return db_module.SessionLocal


def workspace_context_id_for_boundary(
    *,
    provider_id: str,
    object_type: str,
    object_id: str,
) -> str:
    """Return a deterministic opaque context id for one boundary object."""

    material = "\n".join(
        [
            _required_token(provider_id, "provider_id"),
            _required_token(object_type, "object_type"),
            _required_token(object_id, "object_id"),
        ]
    )
    return "wctx_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def default_workspace_context_id(agent_id: str) -> str:
    """Return the stable default context id for an agent without resolved work."""

    return workspace_context_id_for_boundary(
        provider_id="cao",
        object_type="agent_default",
        object_id=_required_token(agent_id, "agent_id"),
    )


def ensure_default_workspace_context(agent_id: str) -> WorkspaceContextRecord:
    """Ensure an agent has a default context for non-resolved runtime work."""

    return ensure_workspace_context_for_boundary(
        resolver_id="default",
        provider_id="cao",
        object_type="agent_default",
        object_id=_required_token(agent_id, "agent_id"),
    )


def ensure_workspace_context_for_boundary(
    *,
    resolver_id: str,
    provider_id: str,
    object_type: str,
    object_id: str,
    metadata: Mapping[str, Any] | None = None,
) -> WorkspaceContextRecord:
    """Create or return the context whose boundary is one provider object."""

    resolver_id = _required_token(resolver_id, "resolver_id")
    provider_id = _required_token(provider_id, "provider_id")
    object_type = _required_token(object_type, "object_type")
    object_id = _required_token(object_id, "object_id")
    context_id = workspace_context_id_for_boundary(
        provider_id=provider_id,
        object_type=object_type,
        object_id=object_id,
    )
    now = datetime.now()
    with _session_local()() as session:
        session.execute(
            sqlite_insert(WorkspaceContextModel)
            .values(
                id=context_id,
                resolver_id=resolver_id,
                boundary_provider_id=provider_id,
                boundary_object_type=object_type,
                boundary_object_id=object_id,
                status=WORKSPACE_CONTEXT_STATUS_ACTIVE,
                metadata_json=_dumps(metadata),
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        context_row = session.get(WorkspaceContextModel, context_id)
        if context_row is None:
            raise RuntimeError("workspace context insert did not create or find a row")
        if (
            context_row.boundary_provider_id != provider_id
            or context_row.boundary_object_type != object_type
            or context_row.boundary_object_id != object_id
        ):
            raise WorkspaceContextConflictError(
                f"workspace context {context_id!r} has a different boundary"
            )

        _insert_mapping_or_validate(
            session,
            workspace_context_id=context_id,
            provider_id=provider_id,
            object_type=object_type,
            object_id=object_id,
            role=WORKSPACE_CONTEXT_ROLE_BOUNDARY,
            metadata=metadata,
        )
        session.commit()
        return _context_from_row(context_row)


def attach_workspace_context_object(
    *,
    workspace_context_id: str,
    provider_id: str,
    object_type: str,
    object_id: str,
    role: str,
    metadata: Mapping[str, Any] | None = None,
) -> WorkspaceContextObjectMappingRecord:
    """Attach a provider object to an existing workspace context."""

    if role == WORKSPACE_CONTEXT_ROLE_BOUNDARY:
        raise ValueError(
            "boundary mappings must be created with ensure_workspace_context_for_boundary"
        )
    with _session_local()() as session:
        context_row = session.get(
            WorkspaceContextModel,
            _required_token(workspace_context_id, "workspace_context_id"),
        )
        if context_row is None:
            raise ValueError(f"workspace context not found: {workspace_context_id}")
        mapping_row = _insert_mapping_or_validate(
            session,
            workspace_context_id=context_row.id,
            provider_id=_required_token(provider_id, "provider_id"),
            object_type=_required_token(object_type, "object_type"),
            object_id=_required_token(object_id, "object_id"),
            role=_required_token(role, "role"),
            metadata=metadata,
        )
        session.commit()
        return _mapping_from_row(mapping_row)


def get_workspace_context_for_object(
    *,
    provider_id: str,
    object_type: str,
    object_id: str,
) -> WorkspaceContextRecord | None:
    """Return the mapped workspace context for one provider object."""

    with _session_local()() as session:
        mapping_row = (
            session.query(WorkspaceContextObjectMappingModel)
            .filter(
                WorkspaceContextObjectMappingModel.provider_id
                == _required_token(provider_id, "provider_id"),
                WorkspaceContextObjectMappingModel.object_type
                == _required_token(object_type, "object_type"),
                WorkspaceContextObjectMappingModel.object_id
                == _required_token(object_id, "object_id"),
            )
            .first()
        )
        if mapping_row is None:
            return None
        context_row = session.get(WorkspaceContextModel, mapping_row.workspace_context_id)
        return _context_from_row(context_row) if context_row is not None else None


def ensure_context_workspace(
    *,
    agent_id: str,
    workspace_context_id: str,
    root_path: Path,
) -> ContextWorkspaceRecord:
    """Create or return an agent-local workspace for one context."""

    agent_id = _required_token(agent_id, "agent_id")
    workspace_context_id = _required_token(workspace_context_id, "workspace_context_id")
    now = datetime.now()
    with _session_local()() as session:
        if session.get(WorkspaceContextModel, workspace_context_id) is None:
            raise ValueError(f"workspace context not found: {workspace_context_id}")
        session.execute(
            sqlite_insert(ContextWorkspaceModel)
            .values(
                agent_id=agent_id,
                workspace_context_id=workspace_context_id,
                root_path=str(root_path),
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["agent_id", "workspace_context_id"])
        )
        row = (
            session.query(ContextWorkspaceModel)
            .filter(
                ContextWorkspaceModel.agent_id == agent_id,
                ContextWorkspaceModel.workspace_context_id == workspace_context_id,
            )
            .first()
        )
        if row is None:
            raise RuntimeError("context workspace insert did not create or find a row")
        if row.root_path != str(root_path):
            raise WorkspaceContextConflictError(
                "context workspace root path differs for "
                f"{agent_id!r}/{workspace_context_id!r}"
            )
        session.commit()
        return _context_workspace_from_row(row)


def get_context_workspace(
    *,
    agent_id: str,
    workspace_context_id: str,
) -> ContextWorkspaceRecord | None:
    """Return one agent-local workspace context row."""

    with _session_local()() as session:
        row = (
            session.query(ContextWorkspaceModel)
            .filter(
                ContextWorkspaceModel.agent_id
                == _required_token(agent_id, "agent_id"),
                ContextWorkspaceModel.workspace_context_id
                == _required_token(workspace_context_id, "workspace_context_id"),
            )
            .first()
        )
        return _context_workspace_from_row(row) if row is not None else None


def set_context_workspace_active_terminal(
    *,
    agent_id: str,
    workspace_context_id: str,
    terminal_id: str | None,
) -> bool:
    """Update the cached active terminal for an agent/context workspace."""

    with _session_local()() as session:
        row = (
            session.query(ContextWorkspaceModel)
            .filter(
                ContextWorkspaceModel.agent_id
                == _required_token(agent_id, "agent_id"),
                ContextWorkspaceModel.workspace_context_id
                == _required_token(workspace_context_id, "workspace_context_id"),
            )
            .first()
        )
        if row is None:
            return False
        row.active_terminal_id = terminal_id
        row.updated_at = datetime.now()
        session.commit()
        return True


def _insert_mapping_or_validate(
    session,
    *,
    workspace_context_id: str,
    provider_id: str,
    object_type: str,
    object_id: str,
    role: str,
    metadata: Mapping[str, Any] | None,
) -> WorkspaceContextObjectMappingModel:
    now = datetime.now()
    if role == WORKSPACE_CONTEXT_ROLE_BOUNDARY:
        existing_boundary = (
            session.query(WorkspaceContextObjectMappingModel)
            .filter(
                WorkspaceContextObjectMappingModel.workspace_context_id == workspace_context_id,
                WorkspaceContextObjectMappingModel.role == WORKSPACE_CONTEXT_ROLE_BOUNDARY,
            )
            .first()
        )
        if existing_boundary is not None and (
            existing_boundary.provider_id != provider_id
            or existing_boundary.object_type != object_type
            or existing_boundary.object_id != object_id
        ):
            raise WorkspaceContextConflictError(
                f"workspace context {workspace_context_id!r} already has a boundary mapping"
            )
    session.execute(
        sqlite_insert(WorkspaceContextObjectMappingModel)
        .values(
            workspace_context_id=workspace_context_id,
            provider_id=provider_id,
            object_type=object_type,
            object_id=object_id,
            role=role,
            metadata_json=_dumps(metadata),
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["provider_id", "object_type", "object_id"])
    )
    row = (
        session.query(WorkspaceContextObjectMappingModel)
        .filter(
            WorkspaceContextObjectMappingModel.provider_id == provider_id,
            WorkspaceContextObjectMappingModel.object_type == object_type,
            WorkspaceContextObjectMappingModel.object_id == object_id,
        )
        .first()
    )
    if row is None:
        raise RuntimeError("workspace context mapping insert did not create or find a row")
    if row.workspace_context_id != workspace_context_id:
        raise WorkspaceContextConflictError(
            f"{provider_id}:{object_type}:{object_id} already maps to "
            f"{row.workspace_context_id}, not {workspace_context_id}"
        )
    if row.role != role:
        raise WorkspaceContextConflictError(
            f"{provider_id}:{object_type}:{object_id} already maps with role {row.role}"
        )
    return cast(WorkspaceContextObjectMappingModel, row)


def _context_from_row(row: WorkspaceContextModel) -> WorkspaceContextRecord:
    value = cast(Any, row)
    return WorkspaceContextRecord(
        id=value.id,
        resolver_id=value.resolver_id,
        boundary_provider_id=value.boundary_provider_id,
        boundary_object_type=value.boundary_object_type,
        boundary_object_id=value.boundary_object_id,
        status=value.status,
        metadata=_loads(value.metadata_json),
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _mapping_from_row(
    row: WorkspaceContextObjectMappingModel,
) -> WorkspaceContextObjectMappingRecord:
    value = cast(Any, row)
    return WorkspaceContextObjectMappingRecord(
        id=value.id,
        workspace_context_id=value.workspace_context_id,
        provider_id=value.provider_id,
        object_type=value.object_type,
        object_id=value.object_id,
        role=value.role,
        metadata=_loads(value.metadata_json),
        created_at=value.created_at,
    )


def _context_workspace_from_row(row: ContextWorkspaceModel) -> ContextWorkspaceRecord:
    value = cast(Any, row)
    return ContextWorkspaceRecord(
        id=value.id,
        agent_id=value.agent_id,
        workspace_context_id=value.workspace_context_id,
        root_path=Path(value.root_path),
        active_terminal_id=value.active_terminal_id,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _dumps(value: Mapping[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(dict(value), sort_keys=True)


def _loads(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    loaded = json.loads(value)
    return dict(loaded) if isinstance(loaded, Mapping) else None


def _required_token(value: str, label: str) -> str:
    token = str(value).strip()
    if not token:
        raise ValueError(f"{label} is required")
    return token

"""Tests for workspace context registry persistence."""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.workspace_context_store import (
    WORKSPACE_CONTEXT_ROLE_ATTACHED,
    WORKSPACE_CONTEXT_ROLE_BOUNDARY,
    WORKSPACE_CONTEXT_ROLE_INTERACTION,
    WorkspaceContextConflictError,
)


@pytest.fixture
def test_db(runtime_inbox_db_session):
    return runtime_inbox_db_session


def test_boundary_context_creation_is_idempotent_and_queryable(test_db):
    first = db_module.ensure_workspace_context_for_boundary(
        resolver_id="example_planning",
        provider_id="example",
        object_type="issue",
        object_id="CAO-79",
    )
    second = db_module.ensure_workspace_context_for_boundary(
        resolver_id="example_planning",
        provider_id="example",
        object_type="issue",
        object_id="CAO-79",
    )

    assert second.id == first.id
    assert second.boundary_provider_id == "example"
    assert second.boundary_object_type == "issue"
    assert (
        db_module.get_workspace_context_for_object(
            provider_id="example",
            object_type="issue",
            object_id="CAO-79",
        )
        == first
    )
    with db_module.SessionLocal() as session:
        mappings = session.query(db_module.WorkspaceContextObjectMappingModel).all()
    assert [(mapping.workspace_context_id, mapping.role) for mapping in mappings] == [
        (first.id, WORKSPACE_CONTEXT_ROLE_BOUNDARY)
    ]


def test_attached_object_cannot_be_remapped_to_another_context(test_db):
    context_a = db_module.ensure_workspace_context_for_boundary(
        resolver_id="example_planning",
        provider_id="example",
        object_type="issue",
        object_id="CAO-79",
    )
    context_b = db_module.ensure_workspace_context_for_boundary(
        resolver_id="example_planning",
        provider_id="example",
        object_type="issue",
        object_id="CAO-80",
    )
    db_module.attach_workspace_context_object(
        workspace_context_id=context_a.id,
        provider_id="example",
        object_type="agent_session",
        object_id="session-42",
        role=WORKSPACE_CONTEXT_ROLE_INTERACTION,
    )

    with pytest.raises(WorkspaceContextConflictError, match="already maps"):
        db_module.attach_workspace_context_object(
            workspace_context_id=context_b.id,
            provider_id="example",
            object_type="agent_session",
            object_id="session-42",
            role=WORKSPACE_CONTEXT_ROLE_INTERACTION,
        )


def test_context_workspace_is_unique_per_agent_and_context(test_db, tmp_path):
    context = db_module.ensure_workspace_context_for_boundary(
        resolver_id="example_planning",
        provider_id="example",
        object_type="issue",
        object_id="CAO-79",
    )
    root = tmp_path / "agents" / "implementation_partner" / "contexts" / context.id

    first = db_module.ensure_context_workspace(
        agent_id="implementation_partner",
        workspace_context_id=context.id,
        root_path=root,
    )
    second = db_module.ensure_context_workspace(
        agent_id="implementation_partner",
        workspace_context_id=context.id,
        root_path=root,
    )
    assert second.id == first.id

    assert db_module.set_context_workspace_active_terminal(
        agent_id="implementation_partner",
        workspace_context_id=context.id,
        terminal_id="terminal-1",
    )
    refreshed = db_module.get_context_workspace(
        agent_id="implementation_partner",
        workspace_context_id=context.id,
    )
    assert refreshed is not None
    assert refreshed.root_path == root
    assert refreshed.active_terminal_id == "terminal-1"


def test_context_workspace_rejects_root_path_conflicts(test_db, tmp_path):
    context = db_module.ensure_workspace_context_for_boundary(
        resolver_id="example_planning",
        provider_id="example",
        object_type="issue",
        object_id="CAO-79",
    )
    db_module.ensure_context_workspace(
        agent_id="implementation_partner",
        workspace_context_id=context.id,
        root_path=tmp_path / "first",
    )

    with pytest.raises(WorkspaceContextConflictError, match="root path differs"):
        db_module.ensure_context_workspace(
            agent_id="implementation_partner",
            workspace_context_id=context.id,
            root_path=tmp_path / "second",
        )


def test_non_boundary_roles_can_repeat_inside_one_context(test_db):
    context = db_module.ensure_workspace_context_for_boundary(
        resolver_id="example_planning",
        provider_id="example",
        object_type="issue",
        object_id="CAO-79",
    )

    for object_id in ("activity-1", "activity-2"):
        db_module.attach_workspace_context_object(
            workspace_context_id=context.id,
            provider_id="example",
            object_type="agent_activity",
            object_id=object_id,
            role=WORKSPACE_CONTEXT_ROLE_ATTACHED,
        )

    with db_module.SessionLocal() as session:
        attached = (
            session.query(db_module.WorkspaceContextObjectMappingModel)
            .filter(
                db_module.WorkspaceContextObjectMappingModel.role == WORKSPACE_CONTEXT_ROLE_ATTACHED
            )
            .count()
        )
    assert attached == 2

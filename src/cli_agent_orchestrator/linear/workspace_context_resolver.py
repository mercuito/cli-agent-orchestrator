"""Linear planning workspace context resolver."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.workspace_context_store import (
    WORKSPACE_CONTEXT_ROLE_CHILD_WORK_ITEM,
    WORKSPACE_CONTEXT_ROLE_INTERACTION,
)
from cli_agent_orchestrator.events import CaoEvent
from cli_agent_orchestrator.linear.workspace_events import (
    LinearIssueContextEvent,
    LinearIssueCreatedEvent,
)
from cli_agent_orchestrator.workspace_contexts import (
    WorkspaceContextResolution,
)

LINEAR_PLANNING_RESOLVER_ID = "linear_planning"
LINEAR_PROVIDER_ID = "linear"
LINEAR_ISSUE_OBJECT_TYPE = "issue"
LINEAR_AGENT_SESSION_OBJECT_TYPE = "agent_session"


def resolve_linear_workspace_event(
    event: CaoEvent,
) -> WorkspaceContextResolution | None:
    """Resolve workspace context from a CAO-published Linear event."""

    if isinstance(event, LinearIssueContextEvent):
        return resolve_issue_context_event(event)
    if isinstance(event, LinearIssueCreatedEvent):
        return resolve_issue_created_event(event)
    return None


def resolve_issue_context_event(
    event: LinearIssueContextEvent,
) -> WorkspaceContextResolution | None:
    """Resolve and persist the workspace context for a typed Linear issue event."""

    canonical_issue_id = event.canonical_issue_id
    boundary_issue_id = event.boundary_issue_id
    if canonical_issue_id is None or boundary_issue_id is None:
        return None
    existing_issue_context = db_module.get_workspace_context_for_object(
        provider_id=LINEAR_PROVIDER_ID,
        object_type=LINEAR_ISSUE_OBJECT_TYPE,
        object_id=canonical_issue_id,
        resolver_id=LINEAR_PLANNING_RESOLVER_ID,
    )
    if existing_issue_context is not None:
        if event.agent_session_id:
            db_module.attach_workspace_context_object(
                workspace_context_id=existing_issue_context.id,
                provider_id=LINEAR_PROVIDER_ID,
                object_type=LINEAR_AGENT_SESSION_OBJECT_TYPE,
                object_id=event.agent_session_id,
                role=WORKSPACE_CONTEXT_ROLE_INTERACTION,
            )
        return _resolution_from_context(existing_issue_context)

    context = db_module.ensure_workspace_context_for_boundary(
        resolver_id=LINEAR_PLANNING_RESOLVER_ID,
        provider_id=LINEAR_PROVIDER_ID,
        object_type=LINEAR_ISSUE_OBJECT_TYPE,
        object_id=boundary_issue_id,
    )
    if boundary_issue_id != canonical_issue_id:
        db_module.attach_workspace_context_object(
            workspace_context_id=context.id,
            provider_id=LINEAR_PROVIDER_ID,
            object_type=LINEAR_ISSUE_OBJECT_TYPE,
            object_id=canonical_issue_id,
            role=WORKSPACE_CONTEXT_ROLE_CHILD_WORK_ITEM,
        )
    if event.agent_session_id:
        db_module.attach_workspace_context_object(
            workspace_context_id=context.id,
            provider_id=LINEAR_PROVIDER_ID,
            object_type=LINEAR_AGENT_SESSION_OBJECT_TYPE,
            object_id=event.agent_session_id,
            role=WORKSPACE_CONTEXT_ROLE_INTERACTION,
        )
    return _resolution_from_context(context)


def resolve_issue_created_event(
    event: LinearIssueCreatedEvent,
) -> WorkspaceContextResolution | None:
    """Resolve context membership for a Linear issue-created provider event."""

    workspace_context_id = _workspace_context_id_for_terminal(event.terminal_id)
    if workspace_context_id is None:
        return None
    issue_id = _string_value(event.issue.get("identifier") or event.issue.get("id"))
    if issue_id is None:
        return None
    context = _created_issue_parent_context(event.issue)
    if context is None or context.id != workspace_context_id:
        return None
    db_module.attach_workspace_context_object(
        workspace_context_id=workspace_context_id,
        provider_id=LINEAR_PROVIDER_ID,
        object_type=LINEAR_ISSUE_OBJECT_TYPE,
        object_id=issue_id,
        role=WORKSPACE_CONTEXT_ROLE_CHILD_WORK_ITEM,
        metadata={
            "source": LinearIssueCreatedEvent.event_name,
            "tool_name": event.tool_name,
            "terminal_id": event.terminal_id,
        },
    )
    return _resolution_from_context(context)


def _string_value(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    text = str(value).strip()
    return text or None


def _created_issue_parent_context(issue: Mapping[str, Any]):
    parent = issue.get("parent")
    if not isinstance(parent, Mapping):
        return None
    parent_id = _string_value(parent.get("identifier") or parent.get("id"))
    if parent_id is None:
        return None
    return db_module.get_workspace_context_for_object(
        provider_id=LINEAR_PROVIDER_ID,
        object_type=LINEAR_ISSUE_OBJECT_TYPE,
        object_id=parent_id,
        resolver_id=LINEAR_PLANNING_RESOLVER_ID,
    )


def _workspace_context_id_for_terminal(terminal_id: str) -> str | None:
    metadata = db_module.get_terminal_metadata(terminal_id)
    if metadata is None:
        return None
    value = metadata.get("workspace_context_id")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _resolution_from_context(context) -> WorkspaceContextResolution:
    return WorkspaceContextResolution(
        workspace_context_id=context.id,
        resolver_id=context.resolver_id,
        boundary_provider_id=context.boundary_provider_id,
        boundary_object_type=context.boundary_object_type,
        boundary_object_id=context.boundary_object_id,
    )

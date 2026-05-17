"""Provider-neutral workspace context contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from cli_agent_orchestrator.agent import Agent
from cli_agent_orchestrator.events import CaoEvent


@dataclass(frozen=True)
class WorkspaceContextResolution:
    """Resolver output for a provider event."""

    workspace_context_id: str
    resolver_id: str
    boundary_provider_id: str
    boundary_object_type: str
    boundary_object_id: str


@dataclass(frozen=True)
class ContextAwareNotification:
    """Notification payload with its traced provider event and context resolution."""

    agent_id: str
    message: str
    event: CaoEvent
    resolution: WorkspaceContextResolution


WorkspaceContextResolver = Callable[[CaoEvent], WorkspaceContextResolution | None]


class WorkspaceContextResolverError(ValueError):
    """Raised when a workspace context resolver cannot be selected or resolve."""


_WORKSPACE_CONTEXT_RESOLVERS: dict[str, WorkspaceContextResolver] = {}


def register_workspace_context_resolver(
    resolver_id: str,
    resolver: WorkspaceContextResolver,
) -> None:
    """Register a workspace context resolver by durable agent config id."""

    normalized = _normalize_resolver_id(resolver_id)
    existing = _WORKSPACE_CONTEXT_RESOLVERS.get(normalized)
    if existing is not None and existing is not resolver:
        raise WorkspaceContextResolverError(
            f"Workspace context resolver already registered: {normalized}"
        )
    _WORKSPACE_CONTEXT_RESOLVERS[normalized] = resolver


def resolve_workspace_context_for_agent(
    agent: Agent,
    event: CaoEvent,
) -> WorkspaceContextResolution | None:
    """Resolve the active workspace context for an agent and traced event."""

    if not agent.workspace_context.enabled:
        return None
    resolver_id = agent.workspace_context.resolver_id
    if resolver_id is None:
        raise WorkspaceContextResolverError(
            f"Workspace context resolver is required for {agent.id}"
        )
    normalized = _normalize_resolver_id(resolver_id)
    try:
        resolver = _WORKSPACE_CONTEXT_RESOLVERS[normalized]
    except KeyError as exc:
        raise WorkspaceContextResolverError(
            f"Unknown workspace context resolver for {agent.id}: {normalized}"
        ) from exc
    return resolver(event)


def _normalize_resolver_id(resolver_id: str) -> str:
    normalized = resolver_id.strip()
    if not normalized:
        raise WorkspaceContextResolverError("workspace context resolver id must be non-empty")
    return normalized

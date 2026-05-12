"""Provider-neutral workspace context contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from cli_agent_orchestrator.agent_identity import AgentIdentity
from cli_agent_orchestrator.workspace_providers.events import WorkspaceProviderEvent


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

    agent_identity_id: str
    message: str
    event: WorkspaceProviderEvent
    resolution: WorkspaceContextResolution


WorkspaceContextResolver = Callable[[WorkspaceProviderEvent], WorkspaceContextResolution | None]


class WorkspaceContextResolverError(ValueError):
    """Raised when a workspace context resolver cannot be selected or resolve."""


_WORKSPACE_CONTEXT_RESOLVERS: dict[str, WorkspaceContextResolver] = {}


def register_workspace_context_resolver(
    resolver_id: str,
    resolver: WorkspaceContextResolver,
) -> None:
    """Register a workspace context resolver by durable identity config id."""

    normalized = _normalize_resolver_id(resolver_id)
    existing = _WORKSPACE_CONTEXT_RESOLVERS.get(normalized)
    if existing is not None and existing is not resolver:
        raise WorkspaceContextResolverError(
            f"Workspace context resolver already registered: {normalized}"
        )
    _WORKSPACE_CONTEXT_RESOLVERS[normalized] = resolver


def resolve_workspace_context_for_identity(
    identity: AgentIdentity,
    event: WorkspaceProviderEvent,
) -> WorkspaceContextResolution | None:
    """Resolve the active workspace context for an identity and traced event."""

    if not identity.workspace_context.enabled:
        return None
    resolver_id = identity.workspace_context.resolver_id
    if resolver_id is None:
        raise WorkspaceContextResolverError(
            f"Workspace context resolver is required for {identity.id}"
        )
    normalized = _normalize_resolver_id(resolver_id)
    try:
        resolver = _WORKSPACE_CONTEXT_RESOLVERS[normalized]
    except KeyError as exc:
        raise WorkspaceContextResolverError(
            f"Unknown workspace context resolver for {identity.id}: {normalized}"
        ) from exc
    return resolver(event)


def _normalize_resolver_id(resolver_id: str) -> str:
    normalized = resolver_id.strip()
    if not normalized:
        raise WorkspaceContextResolverError("workspace context resolver id must be non-empty")
    return normalized

"""Provider-neutral workspace context contracts."""

from __future__ import annotations

from dataclasses import dataclass

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

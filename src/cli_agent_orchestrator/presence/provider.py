"""Provider protocol for external presence integrations."""

from __future__ import annotations

from typing import Protocol

from cli_agent_orchestrator.presence.models import PresenceEvent


class PresenceProvider(Protocol):
    """Boundary implemented by systems that expose agent presence to CAO."""

    name: str

    def handle_event(self, event: PresenceEvent) -> None:
        """Handle a provider-normalized event."""


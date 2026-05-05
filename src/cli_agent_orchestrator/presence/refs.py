"""Helpers for creating provider-bound external references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cli_agent_orchestrator.presence.models import ExternalRef


@dataclass(frozen=True)
class ProviderRefFactory:
    """Create ExternalRef objects owned by one declared provider."""

    provider: str

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("presence provider name is required")

    def ref(self, id: str, url: Optional[str] = None) -> ExternalRef:
        """Create a provider-owned reference for ``id``."""

        if not id:
            raise ValueError("external ref id is required")
        return ExternalRef(provider=self.provider, id=id, url=url)

"""Compatibility wrappers for Linear presence translation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider
from cli_agent_orchestrator.presence.models import PresenceEvent


def presence_event_from_agent_session_payload(
    payload: Dict[str, Any],
    *,
    header_event: Optional[str] = None,
    delivery_id: Optional[str] = None,
) -> Optional[PresenceEvent]:
    """Translate a Linear AgentSessionEvent payload into a CAO presence event."""
    return LinearPresenceProvider().normalize_event(
        payload,
        header_event=header_event,
        delivery_id=delivery_id,
    )

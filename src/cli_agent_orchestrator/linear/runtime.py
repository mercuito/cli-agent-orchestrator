"""Smoke runtime bridge from Linear AgentSession events to CAO terminals."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from cli_agent_orchestrator.clients.database import list_terminals_by_session
from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.linear import app_client, translator
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearResolvedPresence,
    canonical_session_name,
    get_linear_workspace_provider,
    normalize_app_key,
)
from cli_agent_orchestrator.presence.models import PresenceEvent
from cli_agent_orchestrator.services import terminal_service

logger = logging.getLogger(__name__)

DEFAULT_TEAM_MEMBER_ID = "cao-discovery-partner"


def _event_app_key(event: PresenceEvent) -> Optional[str]:
    if not event.raw_payload:
        return None
    value = event.raw_payload.get("_cao_linear_app_key")
    return normalize_app_key(str(value)) if value else None


def _find_existing_terminal(session_name: str) -> Optional[Dict[str, Any]]:
    if not tmux_client.session_exists(session_name):
        return None
    terminals = list_terminals_by_session(session_name)
    return terminals[0] if terminals else None


def _resolve_linear_event(event: PresenceEvent) -> LinearResolvedPresence:
    payload = dict(event.raw_payload or {})
    app_key = _event_app_key(event)
    if app_key:
        payload["_cao_linear_app_key"] = app_key
    return get_linear_workspace_provider().resolve_event(payload)


def _terminal_for_resolved_presence(resolved: LinearResolvedPresence) -> Dict[str, Any]:
    identity = resolved.identity
    session_name = canonical_session_name(identity.session_name)
    existing = _find_existing_terminal(session_name)
    if existing is not None:
        return existing

    terminal = terminal_service.create_terminal(
        provider=identity.cli_provider,
        agent_profile=identity.agent_profile,
        session_name=session_name,
        new_session=not tmux_client.session_exists(session_name),
        working_directory=identity.workdir,
    )
    return {
        "id": terminal.id,
        "tmux_session": terminal.session_name,
        "tmux_window": terminal.name,
        "provider": terminal.provider.value,
        "agent_profile": terminal.agent_profile,
    }


def ensure_discovery_terminal(*, app_key: Optional[str] = None) -> Dict[str, Any]:
    """Start or reuse the Linear-mapped CAO terminal for compatibility callers."""
    raw_payload: dict[str, str] = {}
    if app_key:
        raw_payload["_cao_linear_app_key"] = app_key
    event = PresenceEvent(
        provider="linear",
        event_type="AgentSessionEvent",
        action=None,
        raw_payload=raw_payload,
    )
    return _terminal_for_resolved_presence(_resolve_linear_event(event))


def build_terminal_message(
    event: PresenceEvent,
    *,
    resolved: Optional[LinearResolvedPresence] = None,
) -> str:
    """Build the prompt sent into the CAO terminal for this smoke bridge."""
    thread_id = event.thread.ref.id if event.thread else None
    prompt_context = event.thread.prompt_context if event.thread else None
    prompt_body = event.message.body if event.message else None
    app_key = resolved.presence.app_key if resolved is not None else _event_app_key(event)
    actor_name = (
        resolved.presence.app_user_name
        if resolved is not None and resolved.presence.app_user_name
        else resolved.identity.display_name if resolved is not None else "Linear agent"
    )

    parts = [
        f"[Linear {actor_name} smoke event]",
        "",
        f"You are acting as {actor_name} for a Linear Agent Session.",
        "This is a smoke integration path: read the Linear context, acknowledge what you received,",
        "and do not modify repository files unless explicitly asked by the user.",
        "",
        f"Linear app key: {app_key or 'legacy'}",
        f"Action: {event.action or 'unknown'}",
        f"Conversation thread ID: {thread_id or 'unknown'}",
    ]
    if prompt_body:
        parts.extend(["", "User prompt:", prompt_body])
    if prompt_context:
        parts.extend(["", "Linear prompt context:", prompt_context])
    elif event.raw_payload:
        parts.extend(["", "Raw provider payload:", str(event.raw_payload)])
    return "\n".join(parts)


def handle_presence_event(event: PresenceEvent) -> Optional[str]:
    """Handle a provider-normalized presence event by waking a CAO terminal."""
    thread_id = event.thread.ref.id if event.thread else None
    resolved = _resolve_linear_event(event)
    app_key = resolved.presence.app_key
    terminal = _terminal_for_resolved_presence(resolved)
    terminal_id = terminal["id"]
    message = build_terminal_message(event, resolved=resolved)
    terminal_service.send_input(terminal_id, message)

    if thread_id:
        try:
            app_client.update_agent_session_external_url(thread_id, terminal_id, app_key=app_key)
        except Exception as exc:
            logger.warning("Failed to update Linear AgentSession external URL: %s", exc)
        try:
            app_client.create_agent_activity(
                thread_id,
                {
                    "type": "thought",
                    "body": "CAO has started the mapped terminal and is reading the Linear context.",
                },
                app_key=app_key,
            )
        except Exception as exc:
            logger.warning("Failed to create Linear Agent Activity: %s", exc)

    logger.info("Routed Linear AgentSessionEvent to CAO terminal %s", terminal_id)
    return terminal_id


def handle_agent_session_event(payload: Dict[str, Any]) -> Optional[str]:
    """Handle a Linear AgentSessionEvent payload by normalizing it first."""
    event = translator.presence_event_from_agent_session_payload(payload)
    if event is None:
        logger.info("Ignoring non-AgentSession Linear payload")
        return None
    return handle_presence_event(event)

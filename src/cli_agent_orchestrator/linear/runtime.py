"""Smoke runtime bridge from Linear AgentSession events to CAO terminals."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from cli_agent_orchestrator.clients.database import list_terminals_by_session
from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.constants import DEFAULT_PROVIDER, SESSION_PREFIX
from cli_agent_orchestrator.linear import app_client, translator
from cli_agent_orchestrator.presence.models import PresenceEvent
from cli_agent_orchestrator.services import terminal_service

logger = logging.getLogger(__name__)

DEFAULT_TEAM_MEMBER_ID = "cao-discovery-partner"
DEFAULT_AGENT_PROFILE = "developer"
DEFAULT_SESSION_SLUG = "linear-discovery-partner"


def _linear_env(name: str) -> Optional[str]:
    return os.environ.get(name) or app_client.linear_env(name)


def _session_name() -> str:
    slug = _linear_env("LINEAR_DISCOVERY_SESSION_NAME") or DEFAULT_SESSION_SLUG
    return slug if slug.startswith(SESSION_PREFIX) else f"{SESSION_PREFIX}{slug}"


def _agent_profile() -> str:
    return _linear_env("LINEAR_DISCOVERY_AGENT_PROFILE") or DEFAULT_AGENT_PROFILE


def _provider() -> str:
    return _linear_env("LINEAR_DISCOVERY_PROVIDER") or DEFAULT_PROVIDER


def _working_directory() -> str:
    return _linear_env("LINEAR_DISCOVERY_WORKDIR") or os.getcwd()


def _find_existing_terminal(session_name: str) -> Optional[Dict[str, Any]]:
    if not tmux_client.session_exists(session_name):
        return None
    terminals = list_terminals_by_session(session_name)
    return terminals[0] if terminals else None


def ensure_discovery_terminal() -> Dict[str, Any]:
    """Start or reuse the smoke Discovery Partner terminal."""
    session_name = _session_name()
    existing = _find_existing_terminal(session_name)
    if existing is not None:
        return existing

    terminal = terminal_service.create_terminal(
        provider=_provider(),
        agent_profile=_agent_profile(),
        session_name=session_name,
        new_session=not tmux_client.session_exists(session_name),
        working_directory=_working_directory(),
    )
    return {
        "id": terminal.id,
        "tmux_session": terminal.session_name,
        "tmux_window": terminal.name,
        "provider": terminal.provider.value,
        "agent_profile": terminal.agent_profile,
    }


def build_terminal_message(event: PresenceEvent) -> str:
    """Build the prompt sent into the CAO terminal for this smoke bridge."""
    thread_id = event.thread.ref.id if event.thread else None
    prompt_context = event.thread.prompt_context if event.thread else None
    prompt_body = event.message.body if event.message else None

    parts = [
        "[Linear Discovery Partner smoke event]",
        "",
        "You are acting as Discovery Partner for a Linear Agent Session.",
        "This is a smoke integration path: read the Linear context, acknowledge what you received,",
        "and do not modify repository files unless explicitly asked by the user.",
        "",
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
    terminal = ensure_discovery_terminal()
    terminal_id = terminal["id"]
    message = build_terminal_message(event)
    terminal_service.send_input(terminal_id, message)

    if thread_id:
        try:
            app_client.update_agent_session_external_url(thread_id, terminal_id)
        except Exception as exc:
            logger.warning("Failed to update Linear AgentSession external URL: %s", exc)
        try:
            app_client.create_agent_activity(
                thread_id,
                {
                    "type": "thought",
                    "body": "Discovery Partner has started in CAO and is reading the Linear context.",
                },
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

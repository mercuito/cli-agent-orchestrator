"""Linear event interpretation for CAO agent runtime notifications."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Optional

from cli_agent_orchestrator.linear import app_client, translator
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearResolvedPresence,
    LinearWorkspaceProviderConfigError,
    get_linear_workspace_provider,
    normalize_app_key,
)
from cli_agent_orchestrator.presence.inbox_bridge import create_notification_for_persisted_event
from cli_agent_orchestrator.presence.models import PresenceEvent
from cli_agent_orchestrator.presence.models import PersistedPresenceEvent
from cli_agent_orchestrator.runtime.agent import (
    AgentRuntimeHandle,
    AgentRuntimeNotification,
    AgentRuntimeNotifyResult,
)

logger = logging.getLogger(__name__)

DEFAULT_TEAM_MEMBER_ID = "cao-discovery-partner"
LINEAR_RUNTIME_SOURCE_KIND = "linear_agent_session_event"
LIFECYCLE_ACTIVITY_BODY_CHARS = 220


def _compact(value: str) -> str:
    return " ".join(value.split())


def _bounded_activity_body(value: str) -> str:
    compact = _compact(value)
    if len(compact) <= LIFECYCLE_ACTIVITY_BODY_CHARS:
        return compact
    suffix = "..."
    return compact[: LIFECYCLE_ACTIVITY_BODY_CHARS - len(suffix)].rstrip() + suffix


def _post_lifecycle_activity(
    thread_id: Optional[str],
    content: Dict[str, Any],
    *,
    app_key: Optional[str],
    description: str,
) -> None:
    if not thread_id:
        return
    try:
        app_client.create_agent_activity(thread_id, content, app_key=app_key)
    except Exception as exc:
        logger.warning("Failed to create Linear %s AgentActivity: %s", description, exc)


def _post_accepted_activity(
    *,
    thread_id: Optional[str],
    resolved: LinearResolvedPresence,
) -> None:
    actor_name = resolved.identity.display_name or resolved.identity.id
    _post_lifecycle_activity(
        thread_id,
        {
            "type": "thought",
            "body": _bounded_activity_body(
                f"CAO accepted this Linear session and is starting or notifying {actor_name}."
            ),
        },
        app_key=resolved.presence.app_key,
        description="accepted",
    )


def _post_startup_failed_activity(
    *,
    thread_id: Optional[str],
    app_key: Optional[str],
) -> None:
    _post_lifecycle_activity(
        thread_id,
        {
            "type": "error",
            "body": _bounded_activity_body(
                "CAO could not start or reuse the mapped runtime. "
                "The inbox notification was saved for retry."
            ),
        },
        app_key=app_key,
        description="startup failure",
    )


def _update_external_url_once(
    *,
    thread_id: Optional[str],
    terminal_id: Optional[str],
    agent_id: Optional[str],
    app_key: Optional[str],
) -> None:
    if not thread_id or not terminal_id:
        return
    try:
        app_client.update_agent_session_external_url(
            thread_id, terminal_id, agent_id=agent_id, app_key=app_key
        )
    except Exception as exc:
        logger.warning("Failed to update Linear AgentSession external URL: %s", exc)


def _event_app_key(event: PresenceEvent) -> Optional[str]:
    if not event.raw_payload:
        return None
    value = event.raw_payload.get("_cao_linear_app_key")
    return normalize_app_key(str(value)) if value else None


def _resolve_linear_event(event: PresenceEvent) -> LinearResolvedPresence:
    payload = dict(event.raw_payload or {})
    app_key = _event_app_key(event)
    if app_key:
        payload["_cao_linear_app_key"] = app_key
    return get_linear_workspace_provider().resolve_event(payload)


def _runtime_handle_for_resolved_presence(resolved: LinearResolvedPresence) -> AgentRuntimeHandle:
    return AgentRuntimeHandle(resolved.identity)


def _terminal_for_resolved_presence(resolved: LinearResolvedPresence) -> Dict[str, Any]:
    return _runtime_handle_for_resolved_presence(resolved).ensure_started().as_terminal_metadata()


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


def _runtime_source_id(event: PresenceEvent) -> str:
    if event.message is not None and event.message.ref is not None:
        return f"message:{event.message.ref.id}"
    if event.delivery_id:
        return f"delivery:{event.delivery_id}"

    thread_id = event.thread.ref.id if event.thread else ""
    message_body = event.message.body if event.message else ""
    digest = hashlib.sha256(
        "\n".join(
            [
                event.provider,
                event.event_type,
                event.action or "",
                thread_id,
                message_body or "",
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"derived:{digest}"


def handle_presence_event(event: PresenceEvent) -> Optional[str]:
    """Handle a provider-normalized Linear event through the CAO runtime handle."""
    thread_id = event.thread.ref.id if event.thread else None
    resolved = _resolve_linear_event(event)
    app_key = resolved.presence.app_key
    handle = _runtime_handle_for_resolved_presence(resolved)
    message = build_terminal_message(event, resolved=resolved)
    result = handle.notify(
        message,
        sender_id=f"linear:{app_key or 'legacy'}",
        source_kind=LINEAR_RUNTIME_SOURCE_KIND,
        source_id=_runtime_source_id(event),
    )
    terminal_id = result.terminal_id

    if thread_id and terminal_id:
        _update_external_url_once(
            thread_id=thread_id,
            terminal_id=terminal_id,
            agent_id=resolved.identity.id,
            app_key=app_key,
        )
        _post_lifecycle_activity(
            thread_id,
            {
                "type": "thought",
                "body": _bounded_activity_body(
                    "CAO has started the mapped terminal and is reading the Linear context."
                ),
            },
            app_key=app_key,
            description="ready",
        )

    logger.info(
        "Accepted Linear AgentSessionEvent for CAO agent %s (terminal=%s status=%s created=%s)",
        resolved.identity.id,
        terminal_id,
        result.status.value,
        result.notification.created,
    )
    return terminal_id


def notify_agent_for_persisted_event(
    persisted_event: Optional[PersistedPresenceEvent],
    event: Optional[PresenceEvent],
) -> Optional[AgentRuntimeNotifyResult]:
    """Deliver a compact replyable Linear AgentSession notification to its mapped agent."""
    if persisted_event is None or event is None:
        return None
    if persisted_event.thread is None or persisted_event.message is None:
        return None
    if not persisted_event.message.body:
        return None

    try:
        resolved = _resolve_linear_event(event)
    except LinearWorkspaceProviderConfigError as exc:
        logger.warning("Linear AgentSession notification was not routed: %s", exc)
        return None

    handle = _runtime_handle_for_resolved_presence(resolved)
    notification = create_notification_for_persisted_event(
        persisted_event,
        receiver_id=handle.inbox_receiver_id,
    )
    thread_id = persisted_event.thread.external_id
    if notification.created:
        _post_accepted_activity(thread_id=thread_id, resolved=resolved)

    runtime_notification = AgentRuntimeNotification(
        inbox_message=notification.inbox_message,
        created=notification.created,
        receiver_id=notification.inbox_message.receiver_id,
    )
    result = handle.accept_notification(runtime_notification)
    if notification.created:
        _update_external_url_once(
            thread_id=thread_id,
            terminal_id=result.terminal_id,
            agent_id=resolved.identity.id,
            app_key=resolved.presence.app_key,
        )
        if result.error and result.terminal_id is None:
            _post_startup_failed_activity(
                thread_id=thread_id,
                app_key=resolved.presence.app_key,
            )

    logger.info(
        "Accepted Linear AgentSession inbox notification for CAO agent %s "
        "(inbox=%s terminal=%s status=%s created=%s)",
        resolved.identity.id,
        result.notification.inbox_message.id,
        result.terminal_id,
        result.status.value,
        result.notification.created,
    )
    return result


def handle_agent_session_event(payload: Dict[str, Any]) -> Optional[str]:
    """Handle a Linear AgentSessionEvent payload by normalizing it first."""
    event = translator.presence_event_from_agent_session_payload(payload)
    if event is None:
        logger.info("Ignoring non-AgentSession Linear payload")
        return None
    return handle_presence_event(event)

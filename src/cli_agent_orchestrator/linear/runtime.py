"""Linear event interpretation for CAO agent runtime notifications."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, Optional, cast

from cli_agent_orchestrator.agent import AgentRegistry
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.events import CaoEvent
from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear.agent_policies import (
    LinearPolicyAction,
    LinearPolicyDecision,
    LinearPolicyRequest,
    build_default_linear_agent_policy_evaluator,
)
from cli_agent_orchestrator.linear.workspace_events import (
    LinearIssueContextEvent,
    publish_linear_provider_event,
)
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearResolvedPresence,
    LinearWorkspaceProviderConfigError,
    get_linear_workspace_provider,
    normalize_app_key,
    should_enable_linear_agent_policies,
)
from cli_agent_orchestrator.provider_conversations.inbox_bridge import (
    create_notification_for_persisted_event,
)
from cli_agent_orchestrator.provider_conversations.models import (
    PersistedProviderEventRecords,
    ProcessedProviderEventRecord,
)
from cli_agent_orchestrator.provider_conversations.persistence import (
    get_processed_event,
    get_message,
    get_thread,
    mark_processed_event,
    upsert_message,
    upsert_thread,
    upsert_work_item,
)
from cli_agent_orchestrator.runtime.agent import (
    AgentRuntimeHandle,
    AgentRuntimeNotification,
    AgentRuntimeNotifyResult,
    AgentRuntimeTerminal,
)
from cli_agent_orchestrator.services.agent_manager import AgentManager
from cli_agent_orchestrator.workspace_contexts import (
    WorkspaceContextResolution,
)
from cli_agent_orchestrator.workspace_setups import (
    WorkspaceSetupConfigError,
    default_workspace_collaboration_manager,
)

logger = logging.getLogger(__name__)

DEFAULT_TEAM_MEMBER_ID = "cao-discovery-partner"
LINEAR_RUNTIME_SOURCE_KIND = "linear_agent_session_event"
LIFECYCLE_ACTIVITY_BODY_CHARS = 220
LIFECYCLE_ERROR_CHARS = 240
POLICY_NOTICE_REASON_CHARS = 320
LINEAR_EXTERNAL_URL_PUBLISHED_METADATA_KEY = "linear_external_url_published"
LINEAR_EXTERNAL_URL_METADATA_KEY = "linear_external_url"

_STACK_TRACE_RE = re.compile(r"Traceback \(most recent call last\):|\n\s*File \"")
_BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SENSITIVE_QUOTED_VALUE_RE = re.compile(
    r"(?i)\b(access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization|"
    r"api[_-]?key|password|secret|token)\b([\"']?\s*[:=]\s*)([\"']).*?\3"
)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)\b(access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization|"
    r"api[_-]?key|password|secret|token)\b([\"']?\s*[:=]\s*)[^,\s'\"}]+"
)


def _compact(value: str) -> str:
    return " ".join(value.split())


def _bounded_activity_body(value: str) -> str:
    compact = _compact(value)
    if len(compact) <= LIFECYCLE_ACTIVITY_BODY_CHARS:
        return compact
    suffix = "..."
    return compact[: LIFECYCLE_ACTIVITY_BODY_CHARS - len(suffix)].rstrip() + suffix


def _safe_lifecycle_error(error: Exception) -> str:
    """Return a concise lifecycle/API failure safe for logs."""
    raw_message = str(error) or type(error).__name__
    message = _STACK_TRACE_RE.split(raw_message, maxsplit=1)[0].strip()
    if not message:
        message = type(error).__name__
    message = _BEARER_TOKEN_RE.sub("Bearer [redacted]", message)
    message = _SENSITIVE_QUOTED_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[redacted]{match.group(3)}",
        message,
    )
    message = _SENSITIVE_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[redacted]",
        message,
    )
    message = _compact(message)
    if len(message) <= LIFECYCLE_ERROR_CHARS:
        return message
    suffix = "..."
    return message[: LIFECYCLE_ERROR_CHARS - len(suffix)].rstrip() + suffix


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
        logger.warning(
            "Failed to create Linear %s AgentActivity: %s",
            description,
            _safe_lifecycle_error(exc),
        )


def _post_accepted_activity(
    *,
    thread_id: Optional[str],
    resolved: LinearResolvedPresence,
) -> None:
    actor_name = resolved.agent.display_name or resolved.agent.id
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


def _post_policy_denial_comment(
    *,
    event: LinearIssueContextEvent,
    resolved: LinearResolvedPresence,
    decision: LinearPolicyDecision,
) -> None:
    issue_id = _issue_id_for_policy(event)
    if not issue_id:
        return
    reason = _bounded_policy_reason(decision.reason)
    actor_name = resolved.agent.display_name or resolved.agent.id
    body = "\n\n".join(
        [
            "**CAO policy notice**",
            f"CAO rejected this invocation of {actor_name}.",
            reason,
            f"CAO did not notify or start {actor_name}.",
        ]
    )
    try:
        app_client.create_comment_on_issue(
            issue_id,
            body,
            app_key=resolved.presence.app_key,
        )
    except Exception as exc:
        logger.warning(
            "Failed to create Linear policy denial comment: %s",
            _safe_lifecycle_error(exc),
        )


def _bounded_policy_reason(reason: str) -> str:
    compact = _compact(reason or "The requested agent invocation is not allowed by policy.")
    if len(compact) <= POLICY_NOTICE_REASON_CHARS:
        return compact
    suffix = "..."
    return compact[: POLICY_NOTICE_REASON_CHARS - len(suffix)].rstrip() + suffix


def _update_external_url_once(
    *,
    thread_id: Optional[str],
    terminal_id: Optional[str],
    agent_id: Optional[str],
    app_key: Optional[str],
) -> bool:
    if not thread_id or not terminal_id:
        return False
    try:
        return app_client.update_agent_session_external_url(
            thread_id, terminal_id, agent_id=agent_id, app_key=app_key
        )
    except Exception as exc:
        logger.warning(
            "Failed to update Linear AgentSession external URL: %s",
            _safe_lifecycle_error(exc),
        )
        return False


def _json_object(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except Exception:
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def _publish_persisted_external_url_once(
    *,
    thread_id: Optional[str],
    terminal_id: Optional[str],
    agent_id: Optional[str],
    app_key: Optional[str],
) -> bool:
    """Publish Linear's Open CAO URL unless the current URL is already published."""
    if not thread_id or not terminal_id:
        return False

    desired_url = app_client.public_cao_runtime_url(terminal_id, agent_id=agent_id)
    if not desired_url:
        return False

    with db_module.SessionLocal() as session:
        thread_row = (
            session.query(db_module.ProviderConversationThreadModel)
            .filter(
                db_module.ProviderConversationThreadModel.provider == "linear",
                db_module.ProviderConversationThreadModel.external_id == thread_id,
            )
            .first()
        )
        if thread_row is not None:
            metadata = _json_object(cast(Optional[str], thread_row.metadata_json))
            if metadata.get(LINEAR_EXTERNAL_URL_PUBLISHED_METADATA_KEY):
                if metadata.get(LINEAR_EXTERNAL_URL_METADATA_KEY) == desired_url:
                    return False
                if metadata.get("linear_external_url_terminal_id") == terminal_id and (
                    not agent_id or metadata.get("linear_external_url_agent_id") == agent_id
                ):
                    return False

    if not _update_external_url_once(
        thread_id=thread_id,
        terminal_id=terminal_id,
        agent_id=agent_id,
        app_key=app_key,
    ):
        return False

    with db_module.SessionLocal() as session:
        thread_row = (
            session.query(db_module.ProviderConversationThreadModel)
            .filter(
                db_module.ProviderConversationThreadModel.provider == "linear",
                db_module.ProviderConversationThreadModel.external_id == thread_id,
            )
            .first()
        )
        if thread_row is None:
            return True
        metadata = _json_object(cast(Optional[str], thread_row.metadata_json))
        metadata[LINEAR_EXTERNAL_URL_PUBLISHED_METADATA_KEY] = True
        metadata[LINEAR_EXTERNAL_URL_METADATA_KEY] = desired_url
        metadata["linear_external_url_terminal_id"] = terminal_id
        if agent_id:
            metadata["linear_external_url_agent_id"] = agent_id
        setattr(thread_row, "metadata_json", json.dumps(metadata, sort_keys=True))
        session.commit()
    return True


def _persisted_external_url_was_published(thread_id: str) -> bool:
    with db_module.SessionLocal() as session:
        thread_row = (
            session.query(db_module.ProviderConversationThreadModel)
            .filter(
                db_module.ProviderConversationThreadModel.provider == "linear",
                db_module.ProviderConversationThreadModel.external_id == thread_id,
            )
            .first()
        )
        if thread_row is None:
            return False
        metadata = _json_object(cast(Optional[str], thread_row.metadata_json))
        return bool(metadata.get(LINEAR_EXTERNAL_URL_PUBLISHED_METADATA_KEY))


def _resolve_linear_event(event: LinearIssueContextEvent) -> LinearResolvedPresence:
    provider = get_linear_workspace_provider()
    manager = default_workspace_collaboration_manager(agent_registry=provider.agent_registry)
    try:
        resolution = manager.resolve_provider_event("linear", event)
    except WorkspaceSetupConfigError as exc:
        raise LinearWorkspaceProviderConfigError(str(exc)) from exc
    presence = resolution.provider_payload
    if not hasattr(presence, "agent_id"):
        raise LinearWorkspaceProviderConfigError("Linear workspace setup resolved invalid presence")
    return LinearResolvedPresence(
        presence=presence,
        agent=resolution.agent,
    )


def _policy_action_for_event(event: LinearIssueContextEvent) -> Optional[LinearPolicyAction]:
    if event.event_name == "issue_delegated_to_agent":
        return "delegate"
    if event.event_name == "agent_mentioned":
        return "mention"
    return None


def _issue_id_for_policy(event: LinearIssueContextEvent) -> Optional[str]:
    return event.issue_id or event.issue_identifier


def _incoming_policy_decision(
    *,
    event: LinearIssueContextEvent,
    resolved: LinearResolvedPresence,
) -> LinearPolicyDecision:
    # WIP guardrail layer: default off while the Linear workflow shape is still being explored.
    if not should_enable_linear_agent_policies():
        return LinearPolicyDecision.allow()
    action = _policy_action_for_event(event)
    if action is None:
        return LinearPolicyDecision.allow()
    request = LinearPolicyRequest(
        agent_id=resolved.agent.id,
        direction="incoming",
        action=action,
        origin="webhook",
        actor_kind="human",
        issue_id=_issue_id_for_policy(event),
    )
    evaluator = build_default_linear_agent_policy_evaluator(resolved.presence)
    return evaluator.evaluate(request)


def _runtime_handle_for_resolved_presence(
    resolved: LinearResolvedPresence,
    workspace_context_resolution: WorkspaceContextResolution | None = None,
) -> AgentRuntimeHandle:
    agent_manager = AgentManager(
        configured_agents=AgentRegistry({resolved.agent.id: resolved.agent})
    )
    agent = agent_manager.register_agent(resolved.agent)
    if resolved.agent.workspace.team is None:
        return AgentRuntimeHandle(agent, agent_manager=agent_manager)
    if workspace_context_resolution is None:
        raise LinearWorkspaceProviderConfigError(
            "Linear event did not contain an issue that can resolve workspace context"
        )
    return AgentRuntimeHandle(
        agent,
        workspace_context_id=workspace_context_resolution.workspace_context_id,
        agent_manager=agent_manager,
    )


def _runtime_handle_for_resolved_event(
    resolved: LinearResolvedPresence,
    event: CaoEvent,
) -> AgentRuntimeHandle:
    resolution = _resolve_workspace_context_for_event(resolved, event)
    if resolved.agent.workspace.team is None:
        return _runtime_handle_for_resolved_presence(resolved)
    return _runtime_handle_for_resolved_presence(
        resolved,
        workspace_context_resolution=resolution,
    )


def _resolve_workspace_context_for_event(
    resolved: LinearResolvedPresence,
    event: CaoEvent,
) -> WorkspaceContextResolution | None:
    manager = default_workspace_collaboration_manager(
        agent_registry=AgentRegistry({resolved.agent.id: resolved.agent})
    )
    try:
        return manager.resolve_event_context(resolved.agent, event)
    except WorkspaceSetupConfigError as exc:
        raise LinearWorkspaceProviderConfigError(str(exc)) from exc


def _require_linear_issue_context_event(
    provider_event: CaoEvent,
) -> LinearIssueContextEvent:
    if getattr(provider_event, "provider_name", None) != "linear":
        raise LinearWorkspaceProviderConfigError(
            "Linear notification received non-Linear CAO event: "
            f"{getattr(provider_event, 'provider_name', 'unknown')}"
        )
    if not isinstance(provider_event, LinearIssueContextEvent):
        raise LinearWorkspaceProviderConfigError(
            "Linear notification provider event must be a Linear issue context event"
        )
    return provider_event


def _terminal_for_resolved_presence(resolved: LinearResolvedPresence) -> AgentRuntimeTerminal:
    return _runtime_handle_for_resolved_presence(resolved).ensure_started()


def ensure_discovery_terminal(*, app_key: Optional[str] = None) -> AgentRuntimeTerminal:
    """Start or reuse the Linear-mapped CAO agent terminal."""
    provider = get_linear_workspace_provider()
    presence = provider.resolve_presence(app_key=normalize_app_key(app_key) if app_key else None)
    return _terminal_for_resolved_presence(
        LinearResolvedPresence(
            presence=presence,
            agent=provider.resolve_agent_for_presence(presence),
        )
    )


def build_terminal_message(
    event: LinearIssueContextEvent,
    *,
    resolved: Optional[LinearResolvedPresence] = None,
) -> str:
    """Build the prompt sent into the CAO terminal for a Linear provider event."""
    thread_id = event.thread_id
    prompt_body = event.message_body
    app_key = resolved.presence.app_key if resolved is not None else event.app_key
    actor_name = (
        resolved.presence.app_user_name
        if resolved is not None and resolved.presence.app_user_name
        else resolved.agent.display_name if resolved is not None else "Linear agent"
    )

    parts = [
        f"[Linear {actor_name} provider event]",
        "",
        f"You are acting as {actor_name} for a Linear Agent Session.",
        "Read the Linear context, acknowledge what you received,",
        "and do not modify repository files unless explicitly asked by the user.",
        "",
        f"Linear app key: {app_key or 'unknown'}",
        f"Action: {event.action or 'unknown'}",
        f"Conversation thread ID: {thread_id or 'unknown'}",
    ]
    if prompt_body:
        parts.extend(["", "User prompt:", prompt_body])
    return "\n".join(parts)


def _runtime_source_id(event: LinearIssueContextEvent) -> str:
    if event.message_id is not None:
        return f"message:{event.message_id}"
    if event.delivery_id:
        return f"delivery:{event.delivery_id}"

    digest = hashlib.sha256(
        "\n".join(
            [
                event.provider_name,
                event.event_type or "",
                event.action or "",
                event.thread_id or "",
                event.message_body or "",
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"derived:{digest}"


def handle_provider_event(event: LinearIssueContextEvent) -> Optional[str]:
    """Handle a typed Linear provider event through the CAO runtime handle."""
    thread_id = event.thread_id
    resolved = _resolve_linear_event(event)
    app_key = resolved.presence.app_key
    handle = _runtime_handle_for_resolved_event(resolved, event)
    message = build_terminal_message(event, resolved=resolved)
    result = handle.notify(
        message,
        sender_id=f"linear:{app_key or 'unknown'}",
        source_kind=LINEAR_RUNTIME_SOURCE_KIND,
        source_id=_runtime_source_id(event),
        causing_event=event,
    )
    terminal_id = result.terminal_id

    if thread_id and terminal_id:
        _update_external_url_once(
            thread_id=thread_id,
            terminal_id=terminal_id,
            agent_id=resolved.agent.id,
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
        resolved.agent.id,
        terminal_id,
        result.status.value,
        result.notification.created,
    )
    return terminal_id


def persist_linear_provider_event(event: LinearIssueContextEvent) -> PersistedProviderEventRecords:
    """Persist the durable inbox records touched by a Linear provider event."""

    raw_snapshot = dict(event.raw_payload or {})
    with db_module.SessionLocal() as session:
        processed_event = None
        if event.delivery_id:
            processed_event = get_processed_event(
                provider=event.provider_name,
                external_event_id=event.delivery_id,
                db=session,
            )
            if processed_event is not None:
                session.commit()
                return PersistedProviderEventRecords(
                    processed_event=processed_event,
                    work_item=None,
                    thread=None,
                    message=None,
                )

        work_item = None
        if event.issue_id:
            work_item = upsert_work_item(
                provider=event.provider_name,
                external_id=event.issue_id,
                external_url=event.issue_url,
                identifier=event.issue_identifier,
                title=event.issue_title,
                state=event.issue_state,
                raw_snapshot=raw_snapshot,
                db=session,
            )

        thread = None
        if event.thread_id:
            thread = upsert_thread(
                provider=event.provider_name,
                external_id=event.thread_id,
                external_url=event.thread_url,
                work_item_id=work_item.id if work_item is not None else None,
                kind="conversation",
                state="active",
                prompt_context=event.prompt_context,
                raw_snapshot=raw_snapshot,
                metadata=_linear_thread_metadata(event),
                db=session,
            )

        message = None
        if thread is not None and event.message_body:
            message = upsert_message(
                thread_id=thread.id,
                provider=event.provider_name,
                external_id=event.message_id,
                direction="inbound",
                kind=event.message_kind or "unknown",
                body=event.message_body,
                state="received",
                raw_snapshot=raw_snapshot,
                metadata=dict(event.message_metadata or {}),
                db=session,
            )

        session.commit()
        return PersistedProviderEventRecords(
            processed_event=processed_event,
            work_item=work_item,
            thread=thread,
            message=message,
        )


def mark_linear_provider_event_processed(
    event: LinearIssueContextEvent,
) -> Optional[ProcessedProviderEventRecord]:
    """Mark a Linear provider delivery processed after successful team routing."""

    if not event.delivery_id:
        return None
    processed_event, _created = mark_processed_event(
        provider=event.provider_name,
        external_event_id=event.delivery_id,
        event_type=event.event_name,
        metadata=dict(event.metadata or {}),
    )
    return processed_event


def resolve_linear_event_for_notification(
    provider_event: CaoEvent,
) -> Optional[LinearResolvedPresence]:
    """Resolve and authorize the Linear team recipient before durable side effects."""

    event = _require_linear_issue_context_event(provider_event)
    try:
        resolved = _resolve_linear_event(event)
    except LinearWorkspaceProviderConfigError as exc:
        logger.warning("Linear AgentSession notification was not routed: %s", exc)
        return None
    if resolved.agent.workspace.team is None:
        logger.warning(
            "Linear AgentSession notification was not routed: agent %s has no workspace team",
            resolved.agent.id,
        )
        return None

    decision = _incoming_policy_decision(event=event, resolved=resolved)
    if not decision.allowed:
        logger.info(
            "Suppressed Linear AgentSession notification for CAO agent %s by policy %s: %s",
            resolved.agent.id,
            decision.policy_name or "unknown",
            decision.reason,
        )
        _post_policy_denial_comment(event=event, resolved=resolved, decision=decision)
        return None
    return resolved


def notify_agent_for_persisted_event(
    persisted_event: Optional[PersistedProviderEventRecords],
    provider_event: CaoEvent,
    *,
    resolved: Optional[LinearResolvedPresence] = None,
) -> Optional[AgentRuntimeNotifyResult]:
    """Deliver a compact replyable Linear AgentSession notification to its mapped agent."""
    event = _require_linear_issue_context_event(provider_event)
    if persisted_event is None:
        return None
    if persisted_event.thread is None or persisted_event.message is None:
        return None
    if not persisted_event.message.body:
        return None
    if not event.should_notify_agent:
        return None

    if resolved is None:
        resolved = resolve_linear_event_for_notification(provider_event)
        if resolved is None:
            return None

    try:
        handle = _runtime_handle_for_resolved_event(resolved, provider_event)
    except LinearWorkspaceProviderConfigError as exc:
        logger.warning("Linear AgentSession notification was not routed: %s", exc)
        return None
    notification = create_notification_for_persisted_event(
        persisted_event,
        receiver_id=handle.inbox_receiver_id,
        authorized_agent_id=resolved.agent.id,
    )
    thread_id = persisted_event.thread.external_id
    if notification.created:
        _post_accepted_activity(thread_id=thread_id, resolved=resolved)

    runtime_notification = AgentRuntimeNotification(
        delivery=notification.delivery,
        created=notification.created,
    )
    result = handle.accept_notification(runtime_notification, causing_event=provider_event)
    if result.terminal_id:
        _publish_persisted_external_url_once(
            thread_id=thread_id,
            terminal_id=result.terminal_id,
            agent_id=resolved.agent.id,
            app_key=resolved.presence.app_key,
        )
    if notification.created:
        if result.error and result.terminal_id is None:
            _post_startup_failed_activity(
                thread_id=thread_id,
                app_key=resolved.presence.app_key,
            )

    logger.info(
        "Accepted Linear AgentSession inbox notification for CAO agent %s "
        "(inbox=%s terminal=%s status=%s created=%s)",
        resolved.agent.id,
        result.notification.delivery.notification.id,
        result.terminal_id,
        result.status.value,
        result.notification.created,
    )
    return result


def notify_or_retry_agent_for_persisted_event(
    persisted_event: Optional[PersistedProviderEventRecords],
    provider_event: CaoEvent | None,
    *,
    resolved: Optional[LinearResolvedPresence] = None,
) -> Optional[AgentRuntimeNotifyResult]:
    """Deliver a persisted Linear event, retrying when idempotency found local state."""

    if provider_event is None:
        return None
    notification_result = notify_agent_for_persisted_event(
        persisted_event,
        provider_event,
        resolved=resolved,
    )
    if notification_result is not None:
        return notification_result
    duplicate_delivery = (
        persisted_event is not None
        and persisted_event.processed_event is not None
        and isinstance(provider_event, LinearIssueContextEvent)
        and provider_event.thread_id is not None
        and persisted_event.thread is None
        and persisted_event.message is None
    )
    if not duplicate_delivery:
        return None
    if not isinstance(provider_event, LinearIssueContextEvent):
        return None
    return retry_agent_for_provider_event(provider_event, resolved=resolved)


def retry_agent_for_provider_event(
    event: LinearIssueContextEvent,
    *,
    resolved: Optional[LinearResolvedPresence] = None,
) -> Optional[AgentRuntimeNotifyResult]:
    """Retry delivery/lifecycle for an already persisted Linear AgentSession event."""
    if event.thread_id is None or event.message_id is None:
        return None
    if _persisted_external_url_was_published(event.thread_id):
        return None

    thread = get_thread("linear", event.thread_id)
    message = get_message("linear", event.message_id)
    if thread is None or message is None:
        return None
    return notify_agent_for_persisted_event(
        PersistedProviderEventRecords(
            processed_event=None,
            work_item=None,
            thread=thread,
            message=message,
        ),
        event,
        resolved=resolved,
    )


def _linear_thread_metadata(event: LinearIssueContextEvent) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    for key, value in (
        ("linear_app_key", event.app_key),
        ("linear_agent_id", event.agent_id),
        ("linear_app_user_id", event.app_user_id),
        ("linear_app_user_name", event.app_user_name),
        ("linear_issue_id", event.issue_id),
        ("linear_issue_identifier", event.issue_identifier),
    ):
        if value:
            metadata[key] = value
    return metadata


def handle_agent_session_event(payload: Dict[str, Any]) -> Optional[str]:
    """Handle a Linear AgentSessionEvent payload by publishing its provider event first."""
    publication = publish_linear_provider_event(payload)
    if publication is None or not isinstance(publication.event, LinearIssueContextEvent):
        logger.info("Ignoring non-AgentSession Linear payload")
        return None
    return handle_provider_event(publication.event)

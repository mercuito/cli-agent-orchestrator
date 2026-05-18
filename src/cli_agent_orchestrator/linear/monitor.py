"""Linear-owned monitor/reconciliation safety net.

The monitor uses Linear ``updatedAt`` as its durable event-time watermark.
Default first-run behavior is bootstrap-only: initialize the watermark to the
current time and do not process historical workspace data. Callers may opt into
an explicit bounded backfill window, still constrained by page and session
limits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from cli_agent_orchestrator.agent import AgentConfigError
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.linear import app_client, monitor_store
from cli_agent_orchestrator.linear import runtime as linear_runtime
from cli_agent_orchestrator.linear import workspace_provider as linear_workspace_provider
from cli_agent_orchestrator.linear.workspace_events import (
    LinearIssueContextEvent,
    publish_linear_provider_event,
)
from cli_agent_orchestrator.runtime.agent import AgentRuntimeHandle
from cli_agent_orchestrator.services.agent_manager import AgentManager
from cli_agent_orchestrator.workspace_setups import (
    WorkspaceSetupConfigError,
    default_workspace_collaboration_manager,
)

DEFAULT_PAGE_SIZE = 25
DEFAULT_MAX_PAGES = 2
DEFAULT_ACTIVITIES_PAGE_SIZE = 25
DEFAULT_WATERMARK_OVERLAP = timedelta(seconds=2)
MAX_BACKFILL_LOOKBACK = timedelta(hours=24)
PROVIDER = "linear"
MONITOR_DELIVERY_PREFIX = "linear-monitor"

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


@dataclass(frozen=True)
class LinearMonitorDiagnostic:
    """Bounded structured diagnostic emitted by a Linear monitor pass."""

    code: str
    severity: str
    message: str
    presence_id: Optional[str] = None
    app_key: Optional[str] = None
    session_id: Optional[str] = None
    object_id: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LinearMonitorResult:
    """Summary of one bounded Linear monitor pass."""

    started_at: datetime
    completed_at: datetime
    presences_checked: int
    sessions_seen: int
    sessions_processed: int
    events_recovered: int
    notifications_retried: int
    watermarks_advanced: int
    diagnostics: tuple[LinearMonitorDiagnostic, ...]


def run_linear_monitor(
    *,
    backfill_lookback: Optional[timedelta] = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
    activities_page_size: int = DEFAULT_ACTIVITIES_PAGE_SIZE,
    watermark_overlap: timedelta = DEFAULT_WATERMARK_OVERLAP,
    now: Optional[datetime] = None,
) -> LinearMonitorResult:
    """Run one bounded Linear reconciliation pass for configured presences."""

    started_at = _utc(now)
    diagnostics: list[LinearMonitorDiagnostic] = []
    if backfill_lookback is not None and (
        backfill_lookback <= timedelta(0) or backfill_lookback > MAX_BACKFILL_LOOKBACK
    ):
        completed_at = _utc()
        return LinearMonitorResult(
            started_at=started_at,
            completed_at=completed_at,
            presences_checked=0,
            sessions_seen=0,
            sessions_processed=0,
            events_recovered=0,
            notifications_retried=0,
            watermarks_advanced=0,
            diagnostics=(
                _diagnostic(
                    "invalid_backfill_lookback",
                    "error",
                    "Linear monitor backfill_lookback must be > 0 and <= 24 hours",
                ),
            ),
        )

    try:
        provider = _monitor_workspace_provider()
        config = provider.config
        if config is None:
            raise linear_workspace_provider.LinearWorkspaceProviderConfigError(
                "Linear workspace provider is not configured"
            )
    except Exception as exc:
        completed_at = _utc()
        return LinearMonitorResult(
            started_at=started_at,
            completed_at=completed_at,
            presences_checked=0,
            sessions_seen=0,
            sessions_processed=0,
            events_recovered=0,
            notifications_retried=0,
            watermarks_advanced=0,
            diagnostics=(
                _diagnostic(
                    _failure_code(exc),
                    "error",
                    _safe_error_message(exc),
                ),
            ),
        )

    stats = {
        "sessions_seen": 0,
        "sessions_processed": 0,
        "events_recovered": 0,
        "notifications_retried": 0,
        "watermarks_advanced": 0,
    }
    presences = _team_authorized_monitor_presences(provider, diagnostics)
    for presence in presences:
        _run_presence_monitor(
            provider,
            presence,
            started_at=started_at,
            diagnostics=diagnostics,
            stats=stats,
            backfill_lookback=backfill_lookback,
            page_size=page_size,
            max_pages=max_pages,
            activities_page_size=activities_page_size,
            watermark_overlap=watermark_overlap,
        )

    return LinearMonitorResult(
        started_at=started_at,
        completed_at=_utc(),
        presences_checked=len(presences),
        sessions_seen=stats["sessions_seen"],
        sessions_processed=stats["sessions_processed"],
        events_recovered=stats["events_recovered"],
        notifications_retried=stats["notifications_retried"],
        watermarks_advanced=stats["watermarks_advanced"],
        diagnostics=tuple(diagnostics),
    )


def _monitor_workspace_provider() -> linear_workspace_provider.LinearWorkspaceProvider:
    configured = linear_workspace_provider.get_linear_workspace_provider()
    if configured.config is not None:
        return configured
    provider = linear_workspace_provider.LinearWorkspaceProvider(preflight_credentials=False)
    provider.initialize()
    return provider


def _team_authorized_monitor_presences(
    provider: linear_workspace_provider.LinearWorkspaceProvider,
    diagnostics: list[LinearMonitorDiagnostic],
) -> list[linear_workspace_provider.LinearPresence]:
    manager = default_workspace_collaboration_manager(agent_registry=provider.agent_registry)
    presences: dict[str, linear_workspace_provider.LinearPresence] = {}
    seen_teams: set[str] = set()
    for agent in sorted(provider.agent_registry.all().values(), key=lambda item: item.id):
        try:
            team = manager.team_for_agent(agent)
            if team is None or team.id in seen_teams:
                continue
            seen_teams.add(team.id)
            view = manager.provider_view(team.id, PROVIDER)
        except WorkspaceSetupConfigError as exc:
            diagnostics.append(
                _diagnostic(
                    "monitor_presence_not_team_authorized",
                    "warning",
                    _safe_error_message(exc),
                )
            )
            continue
        config = view.value
        if not isinstance(config, linear_workspace_provider.LinearProviderConfig):
            diagnostics.append(
                _diagnostic(
                    "monitor_presence_not_team_authorized",
                    "warning",
                    "Linear provider view has invalid config",
                )
            )
            continue
        for presence in config.presences.values():
            presences[presence.presence_id] = presence
    return sorted(presences.values(), key=lambda presence: presence.presence_id)


def _run_presence_monitor(
    provider: linear_workspace_provider.LinearWorkspaceProvider,
    presence: linear_workspace_provider.LinearPresence,
    *,
    started_at: datetime,
    diagnostics: list[LinearMonitorDiagnostic],
    stats: dict[str, int],
    backfill_lookback: Optional[timedelta],
    page_size: int,
    max_pages: int,
    activities_page_size: int,
    watermark_overlap: timedelta,
) -> None:
    stats["notifications_retried"] += _retry_pending_delivery(provider, presence, diagnostics)

    stored = monitor_store.get_watermark(
        presence_id=presence.presence_id,
        app_key=presence.app_key,
    )
    try:
        stored_watermark = (
            _parse_linear_datetime(stored.watermark_updated_at) if stored is not None else None
        )
    except ValueError as exc:
        diagnostics.append(
            _diagnostic(
                "invalid_watermark",
                "error",
                _safe_error_message(exc),
                presence=presence,
            )
        )
        return
    if stored is None and backfill_lookback is None:
        monitor_store.upsert_watermark(
            presence_id=presence.presence_id,
            app_key=presence.app_key,
            watermark_updated_at=_isoformat_utc(started_at),
        )
        diagnostics.append(
            _diagnostic(
                "bootstrap_initialized",
                "info",
                "Linear monitor watermark initialized without processing historical sessions",
                presence=presence,
            )
        )
        return

    if backfill_lookback is not None:
        lower_bound = started_at - backfill_lookback
    elif stored_watermark is not None:
        lower_bound = stored_watermark - watermark_overlap
    else:
        diagnostics.append(
            _diagnostic(
                "invalid_watermark",
                "error",
                "Linear monitor has no stored watermark and no backfill window",
                presence=presence,
            )
        )
        return
    try:
        recent = app_client.list_recent_agent_sessions(
            app_key=presence.app_key,
            page_size=page_size,
            max_pages=max_pages,
            activities_page_size=activities_page_size,
        )
    except Exception as exc:
        diagnostics.append(
            _diagnostic(
                _failure_code(exc),
                "error",
                _safe_error_message(exc),
                presence=presence,
            )
        )
        return

    pass_complete = not recent.has_more
    high_water: Optional[datetime] = None
    if recent.has_more:
        diagnostics.append(
            _diagnostic(
                "page_limit_reached",
                "warning",
                "Linear monitor reached its page limit; watermark was not advanced",
                presence=presence,
                details={"page_count": recent.page_count, "max_pages": recent.max_pages},
            )
        )

    for session in recent.sessions:
        stats["sessions_seen"] += 1
        session_id = _string_value(session.get("id"))
        updated_at = _parse_optional_linear_datetime(session.get("updatedAt"))
        if not session_id or updated_at is None:
            pass_complete = False
            diagnostics.append(
                _diagnostic(
                    "invalid_agent_session_shape",
                    "error",
                    "Linear AgentSession is missing id or updatedAt",
                    presence=presence,
                    session_id=session_id,
                )
            )
            continue
        high_water = _max_datetime(high_water, updated_at)
        if updated_at < lower_bound:
            continue
        if not _session_belongs_to_presence(session, presence, diagnostics):
            continue

        stats["sessions_processed"] += 1
        recovered, session_complete = _recover_session_events(
            presence,
            session,
            lower_bound=lower_bound,
            diagnostics=diagnostics,
        )
        stats["events_recovered"] += recovered
        pass_complete = pass_complete and session_complete
        _diagnose_session_state(presence, session, diagnostics)

    if not pass_complete:
        return
    next_watermark = _max_datetime(stored_watermark, high_water or started_at)
    monitor_store.upsert_watermark(
        presence_id=presence.presence_id,
        app_key=presence.app_key,
        watermark_updated_at=_isoformat_utc(next_watermark),
    )
    stats["watermarks_advanced"] += 1


def _recover_session_events(
    presence: linear_workspace_provider.LinearPresence,
    session: Mapping[str, Any],
    *,
    lower_bound: datetime,
    diagnostics: list[LinearMonitorDiagnostic],
) -> tuple[int, bool]:
    recovered = 0
    complete = True
    session_id = _string_value(session.get("id"))

    comment = _mapping_value(session.get("comment"))
    if _recoverable_comment(comment):
        comment_event_time = _comment_event_time(comment)
        if comment_event_time is None:
            diagnostics.append(
                _diagnostic(
                    "invalid_created_comment_shape",
                    "error",
                    "Linear AgentSession comment is missing createdAt or updatedAt",
                    presence=presence,
                    session_id=session_id,
                    object_id=_string_value(comment.get("id")),
                )
            )
            complete = False
        elif comment_event_time < lower_bound:
            pass
        else:
            delivered, delivered_complete = _synthesize_and_deliver(
                presence,
                session,
                action="created",
                object_id=str(comment["id"]),
                diagnostics=diagnostics,
            )
            recovered += delivered
            complete = complete and delivered_complete

    activities = _mapping_value(session.get("activities"))
    nodes = activities.get("nodes")
    if nodes is not None and not isinstance(nodes, list):
        diagnostics.append(
            _diagnostic(
                "invalid_agent_activities_shape",
                "error",
                "Linear AgentSession activities.nodes is not a list",
                presence=presence,
                session_id=session_id,
            )
        )
        return recovered, False
    for activity in nodes or []:
        if not isinstance(activity, Mapping):
            diagnostics.append(
                _diagnostic(
                    "invalid_agent_activity_shape",
                    "error",
                    "Linear AgentActivity node is not an object",
                    presence=presence,
                    session_id=session_id,
                )
            )
            complete = False
            continue
        if not _activity_is_prompt(activity):
            continue
        activity_id = _string_value(activity.get("id"))
        activity_updated_at = _parse_optional_linear_datetime(activity.get("updatedAt"))
        if not activity_id or activity_updated_at is None:
            diagnostics.append(
                _diagnostic(
                    "invalid_prompt_activity_shape",
                    "error",
                    "Linear prompt AgentActivity is missing id or updatedAt",
                    presence=presence,
                    session_id=session_id,
                    object_id=activity_id,
                )
            )
            complete = False
            continue
        if activity_updated_at < lower_bound:
            continue
        delivered, delivered_complete = _synthesize_and_deliver(
            presence,
            session,
            action="prompted",
            object_id=activity_id,
            activity=activity,
            diagnostics=diagnostics,
        )
        recovered += delivered
        complete = complete and delivered_complete

    page_info = _mapping_value(activities.get("pageInfo"))
    if page_info.get("hasNextPage"):
        diagnostics.append(
            _diagnostic(
                "activity_page_limit_reached",
                "warning",
                "Linear monitor reached the activity page limit; watermark was not advanced",
                presence=presence,
                session_id=session_id,
            )
        )
        complete = False
    return recovered, complete


def _synthesize_and_deliver(
    presence: linear_workspace_provider.LinearPresence,
    session: Mapping[str, Any],
    *,
    action: str,
    object_id: str,
    diagnostics: list[LinearMonitorDiagnostic],
    activity: Optional[Mapping[str, Any]] = None,
) -> tuple[int, bool]:
    payload = _synthetic_agent_session_event(
        presence,
        session,
        action=action,
        activity=activity,
    )
    delivery_id = f"{MONITOR_DELIVERY_PREFIX}:{presence.presence_id}:{object_id}"
    try:
        publication = publish_linear_provider_event(payload, delivery_id=delivery_id)
        provider_event = publication.event if publication is not None else None
        resolved = (
            linear_runtime.resolve_linear_event_for_notification(provider_event)
            if isinstance(provider_event, LinearIssueContextEvent)
            else None
        )
        if resolved is None:
            diagnostics.append(
                _diagnostic(
                    "delivery_not_routed",
                    "warning",
                    "Linear monitor recovered an event but team policy or runtime routing did not accept it",
                    presence=presence,
                    session_id=_string_value(session.get("id")),
                    object_id=object_id,
                )
            )
            return 0, False
        persisted = (
            linear_runtime.persist_linear_provider_event(provider_event)
            if isinstance(provider_event, LinearIssueContextEvent)
            else None
        )
        notification_result = linear_runtime.notify_or_retry_agent_for_persisted_event(
            persisted,
            provider_event,
            resolved=resolved,
        )
        if notification_result is None:
            diagnostics.append(
                _diagnostic(
                    "delivery_not_routed",
                    "warning",
                    "Linear monitor recovered an event but team policy or runtime routing did not accept it",
                    presence=presence,
                    session_id=_string_value(session.get("id")),
                    object_id=object_id,
                )
            )
            return 0, False
        if notification_result is not None and isinstance(provider_event, LinearIssueContextEvent):
            linear_runtime.mark_linear_provider_event_processed(provider_event)
    except Exception as exc:
        diagnostics.append(
            _diagnostic(
                _failure_code(exc),
                "error",
                _safe_error_message(exc),
                presence=presence,
                session_id=_string_value(session.get("id")),
                object_id=object_id,
            )
        )
        return 0, False
    return 1, True


def _synthetic_agent_session_event(
    presence: linear_workspace_provider.LinearPresence,
    session: Mapping[str, Any],
    *,
    action: str,
    activity: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    app_user = _mapping_value(session.get("appUser"))
    app_user_id = presence.app_user_id or _string_value(app_user.get("id"))
    app_user_name = presence.app_user_name or _string_value(app_user.get("name"))
    payload: dict[str, Any] = {
        "type": "AgentSessionEvent",
        "action": action,
        "_cao_linear_app_key": presence.app_key,
        "_cao_linear_agent_id": presence.agent_id,
        "data": {
            "action": action,
            "agentSession": dict(session),
        },
    }
    if app_user_id:
        payload["_cao_linear_app_user_id"] = app_user_id
    if app_user_name:
        payload["_cao_linear_app_user_name"] = app_user_name
    if activity is not None:
        payload["data"]["agentActivity"] = dict(activity)
    return payload


def _retry_pending_delivery(
    provider: linear_workspace_provider.LinearWorkspaceProvider,
    presence: linear_workspace_provider.LinearPresence,
    diagnostics: list[LinearMonitorDiagnostic],
) -> int:
    try:
        agent_manager = AgentManager(configured_agents=provider.agent_registry)
        agent = agent_manager.register_agent(provider.resolve_agent_for_presence(presence))
    except Exception as exc:
        diagnostics.append(
            _diagnostic(
                _failure_code(exc),
                "warning",
                _safe_error_message(exc),
                presence=presence,
            )
        )
        return 0

    retried = 0
    for receiver_id in db_module.list_pending_agent_inbox_receiver_ids(agent.id):
        workspace_context_id = _workspace_context_id_from_receiver_id(agent.id, receiver_id)
        if workspace_context_id is None:
            continue
        try:
            handle = AgentRuntimeHandle(
                agent,
                workspace_context_id=workspace_context_id,
                agent_manager=agent_manager,
            )
            if db_module.get_oldest_pending_inbox_delivery(handle.inbox_receiver_id) is None:
                continue
            result = handle.try_deliver_pending()
        except Exception as exc:
            diagnostics.append(
                _diagnostic(
                    _failure_code(exc),
                    "warning",
                    _safe_error_message(exc),
                    presence=presence,
                )
            )
            continue
        if result.error:
            diagnostics.append(
                _diagnostic(
                    "pending_delivery_retry_deferred",
                    "warning",
                    result.error,
                    presence=presence,
                    details={
                        "status": result.status.value,
                        "attempted": result.attempted,
                        "delivered": result.delivered,
                    },
                )
            )
        if result.attempted or result.delivered:
            retried += 1
    return retried


def _workspace_context_id_from_receiver_id(agent_id: str, receiver_id: str) -> str | None:
    prefix = f"agent:{agent_id}:context:"
    if not receiver_id.startswith(prefix):
        return None
    workspace_context_id = receiver_id[len(prefix) :].strip()
    return workspace_context_id or None


def _diagnose_session_state(
    presence: linear_workspace_provider.LinearPresence,
    session: Mapping[str, Any],
    diagnostics: list[LinearMonitorDiagnostic],
) -> None:
    status = _string_value(session.get("status"))
    if status in (None, "", "complete"):
        return
    severity = "warning" if status in {"stale", "error"} else "info"
    code = "unsupported_agent_session_state"
    if status not in {"pending", "active", "awaitingInput", "stale", "error"}:
        code = "unknown_agent_session_state"
        severity = "warning"
    diagnostics.append(
        _diagnostic(
            code,
            severity,
            "Linear AgentSession state has no destructive monitor recovery action",
            presence=presence,
            session_id=_string_value(session.get("id")),
            details={"status": status},
        )
    )


def _session_belongs_to_presence(
    session: Mapping[str, Any],
    presence: linear_workspace_provider.LinearPresence,
    diagnostics: list[LinearMonitorDiagnostic],
) -> bool:
    if not presence.app_user_id:
        return True
    app_user = _mapping_value(session.get("appUser"))
    app_user_id = _string_value(app_user.get("id"))
    if app_user_id == presence.app_user_id:
        return True
    if not app_user_id:
        diagnostics.append(
            _diagnostic(
                "missing_app_user_id",
                "warning",
                "Linear AgentSession is missing appUser.id and cannot be matched to presence",
                presence=presence,
                session_id=_string_value(session.get("id")),
            )
        )
    return False


def _recoverable_comment(comment: Mapping[str, Any]) -> bool:
    return bool(_string_value(comment.get("id")) and _string_value(comment.get("body")))


def _comment_event_time(comment: Mapping[str, Any]) -> Optional[datetime]:
    return _parse_optional_linear_datetime(comment.get("updatedAt")) or (
        _parse_optional_linear_datetime(comment.get("createdAt"))
    )


def _activity_is_prompt(activity: Mapping[str, Any]) -> bool:
    content = _mapping_value(activity.get("content"))
    return _string_value(activity.get("type") or content.get("type")) == "prompt" and bool(
        _string_value(activity.get("body") or content.get("body"))
    )


def _mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_value(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)


def _utc(value: Optional[datetime] = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_optional_linear_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _parse_linear_datetime(value)
    except ValueError:
        return None


def _parse_linear_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    return _utc(parsed)


def _isoformat_utc(value: datetime) -> str:
    return _utc(value).isoformat()


def _max_datetime(left: Optional[datetime], right: datetime) -> datetime:
    return right if left is None or right > left else left


def _failure_code(exc: Exception) -> str:
    if (
        isinstance(exc, app_client.LinearConfigError)
        or isinstance(exc, linear_workspace_provider.LinearWorkspaceProviderConfigError)
        or isinstance(exc, AgentConfigError)
    ):
        message = str(exc).lower()
        if "access_token" in message or "refresh_token" in message or "credential" in message:
            return "credential_failure"
        return "invalid_config"
    if isinstance(exc, app_client.LinearOAuthError):
        return "oauth_failure"
    message = str(exc).lower()
    if "429" in message or "rate limit" in message or "too many requests" in message:
        return "rate_limit"
    if "401" in message or "unauthorized" in message or "authentication" in message:
        return "credential_failure"
    return "linear_api_failure"


def _diagnostic(
    code: str,
    severity: str,
    message: str,
    *,
    presence: Optional[linear_workspace_provider.LinearPresence] = None,
    session_id: Optional[str] = None,
    object_id: Optional[str] = None,
    details: Optional[Mapping[str, Any]] = None,
) -> LinearMonitorDiagnostic:
    return LinearMonitorDiagnostic(
        code=code,
        severity=severity,
        message=_bounded_text(_redact_sensitive(message), 240),
        presence_id=presence.presence_id if presence is not None else None,
        app_key=presence.app_key if presence is not None else None,
        session_id=_bounded_text(session_id, 120) if session_id else None,
        object_id=_bounded_text(object_id, 120) if object_id else None,
        details=_bounded_details(details or {}),
    )


def _safe_error_message(exc: Exception) -> str:
    raw = str(exc) or type(exc).__name__
    message = _STACK_TRACE_RE.split(raw, maxsplit=1)[0].strip() or type(exc).__name__
    return _redact_sensitive(message)


def _redact_sensitive(value: str) -> str:
    redacted = _BEARER_TOKEN_RE.sub("Bearer [redacted]", value)
    redacted = _SENSITIVE_QUOTED_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[redacted]{match.group(3)}",
        redacted,
    )
    return _SENSITIVE_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[redacted]",
        redacted,
    )


def _bounded_details(details: Mapping[str, Any]) -> Mapping[str, Any]:
    bounded: dict[str, Any] = {}
    for index, (key, value) in enumerate(details.items()):
        if index >= 8:
            break
        if isinstance(value, (bool, int, float)) or value is None:
            bounded[str(key)] = value
        else:
            bounded[str(key)] = _bounded_text(_redact_sensitive(str(value)), 160)
    return bounded


def _bounded_text(value: str, max_chars: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    suffix = "..."
    return compact[: max_chars - len(suffix)].rstrip() + suffix

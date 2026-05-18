"""Tests for Linear-owned monitor/reconciliation behavior."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import pytest
from fastapi.testclient import TestClient

from cli_agent_orchestrator.agent import AgentRegistry, AgentWorkspaceConfig, LinearConfig
from cli_agent_orchestrator.api.main import app
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import create_inbox_delivery
from cli_agent_orchestrator.events import CaoEventDispatcher
from cli_agent_orchestrator.linear import app_client, monitor, monitor_store, runtime
from cli_agent_orchestrator.linear import workspace_provider as linear_workspace_provider
from cli_agent_orchestrator.linear.app_client import LinearWebhookVerification
from cli_agent_orchestrator.linear.workspace_events import (
    LinearIssueContextEvent,
    publish_linear_provider_event,
    register_linear_cao_events,
)
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearWorkspaceProvider,
)
from cli_agent_orchestrator.provider_conversations.persistence import (
    get_message,
    get_processed_event,
    get_thread,
)

NOW = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)

# The mocked Linear AgentSession/AgentActivity responses mirror the published
# GraphQL schema selections used by app_client.list_recent_agent_sessions:
# Query.agentSessions(first/after/orderBy: updatedAt), AgentSession id/url/status/
# createdAt/updatedAt/appUser/issue/comment/sourceComment/activities, and
# AgentActivity id/createdAt/updatedAt/signal/content. AgentActivity.sourceComment
# is intentionally not selected because it was removed from the official SDK schema.


@dataclass
class RecordedNotification:
    created: bool
    source_id: str


class RecordingRuntimeHandle:
    """Small stand-in for AgentRuntimeHandle at the terminal/runtime boundary."""

    notifications: list[RecordedNotification] = []

    def __init__(self, _agent: Any, **kwargs: Any) -> None:
        resolution = kwargs.get("workspace_context_resolution")
        workspace_context_id = kwargs.get("workspace_context_id")
        if workspace_context_id is None and resolution is not None:
            workspace_context_id = getattr(resolution, "workspace_context_id", None)
        self.inbox_receiver_id = f"agent:implementation_partner:context:{workspace_context_id}"

    def accept_notification(self, notification: Any, *, causing_event: Any = None):
        delivery = notification.delivery
        RecordingRuntimeHandle.notifications.append(
            RecordedNotification(
                created=notification.created,
                source_id=delivery.notification.source_id,
            )
        )
        return _notify_result(notification)


class RetryRecordingHandle:
    calls = 0
    receiver_ids: list[str] = []

    def __init__(self, _agent: Any, **kwargs: Any) -> None:
        workspace_context_id = kwargs.get("workspace_context_id")
        self.inbox_receiver_id = f"agent:implementation_partner:context:{workspace_context_id}"
        RetryRecordingHandle.receiver_ids.append(self.inbox_receiver_id)

    def try_deliver_pending(self, **_kwargs: Any):
        RetryRecordingHandle.calls += 1
        return type(
            "DeliveryResult",
            (),
            {
                "error": None,
                "attempted": True,
                "delivered": True,
                "status": type("Status", (), {"value": "idle"})(),
            },
        )()


def _notify_result(notification: Any):
    return type(
        "NotifyResult",
        (),
        {
            "notification": notification,
            "terminal_id": None,
            "status": type("Status", (), {"value": "idle"})(),
            "delivery": None,
            "error": None,
        },
    )()


@pytest.fixture
def linear_monitor_world(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runtime_inbox_db_session,
    implementation_partner_agent_factory,
):
    agent = replace(
        implementation_partner_agent_factory(),
        linear=LinearConfig(
            app_key="implementation_partner",
            access_token="test-token",
            app_user_id="app-user-1",
            app_user_name="Implementation Partner",
        ),
        workspace=AgentWorkspaceConfig(team="cao_delivery"),
    )
    registry = AgentRegistry({agent.id: agent})
    provider = LinearWorkspaceProvider(
        agent_registry=registry,
        preflight_credentials=False,
    )
    provider.initialize()
    monkeypatch.setattr(linear_workspace_provider, "_default_linear_workspace_provider", provider)
    RecordingRuntimeHandle.notifications = []
    monkeypatch.setattr(
        runtime,
        "_runtime_handle_for_resolved_presence",
        lambda _resolved, **kwargs: RecordingRuntimeHandle(agent, **kwargs),
    )
    yield provider


def _recent_result(*sessions: Mapping[str, Any], has_more: bool = False):
    return app_client.RecentAgentSessionsResult(
        sessions=[dict(session) for session in sessions],
        page_count=1,
        max_pages=2,
        page_size=25,
        has_more=has_more,
    )


def _session(
    session_id: str = "session-1",
    *,
    updated_at: str = "2026-05-09T11:59:59Z",
    status: str = "complete",
    activity_id: str = "activity-1",
    activity_body: str = "Can you recover this?",
    activity_updated_at: Optional[str] = None,
    comment: Optional[Mapping[str, Any]] = None,
    app_user_id: Optional[str] = "app-user-1",
    activities_has_more: bool = False,
) -> dict[str, Any]:
    activity_updated_at = activity_updated_at or updated_at
    return {
        "id": session_id,
        "url": f"https://linear.app/agent-session/{session_id}",
        "status": status,
        "createdAt": "2026-05-09T11:58:00Z",
        "updatedAt": updated_at,
        "appUser": {"id": app_user_id, "name": "Implementation Partner"},
        "issue": {
            "id": "issue-1",
            "identifier": "CAO-30",
            "title": "Linear monitor",
            "url": "https://linear.app/issue/CAO-30",
            "state": {"name": "In Progress"},
        },
        "comment": dict(comment) if comment is not None else None,
        "activities": {
            "nodes": [
                {
                    "id": activity_id,
                    "createdAt": activity_updated_at,
                    "updatedAt": activity_updated_at,
                    "content": {"type": "prompt", "body": activity_body},
                }
            ],
            "pageInfo": {"hasNextPage": activities_has_more, "endCursor": "activity-cursor"},
        },
    }


def _store_watermark(value: str = "2026-05-09T11:59:59Z") -> None:
    monitor_store.upsert_watermark(
        presence_id="implementation_partner",
        app_key="implementation_partner",
        watermark_updated_at=value,
    )


def _watermark_value() -> str:
    row = monitor_store.get_watermark(
        presence_id="implementation_partner",
        app_key="implementation_partner",
    )
    assert row is not None
    return row.watermark_updated_at


def test_linear_monitor_duplicate_webhook_and_monitor_overlap_does_not_duplicate_delivery(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark()
    monkeypatch.setattr(
        linear_workspace_provider,
        "should_enable_linear_routes",
        lambda: True,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(
            True,
            app_key="implementation_partner",
            app_user_id="app-user-1",
            app_user_name="Implementation Partner",
        ),
    )
    payload = {
        "type": "AgentSessionEvent",
        "action": "prompted",
        "data": {
            "agentSession": _session(),
            "agentActivity": _session()["activities"]["nodes"][0],
        },
    }
    client = TestClient(app)
    webhook_response = client.post(
        "/linear/webhooks/agent",
        json=payload,
        headers={
            "Host": "localhost",
            "Linear-Signature": "signature",
            "Linear-Delivery": "webhook-1",
            "Linear-Event": "AgentSessionEvent",
        },
    )
    assert webhook_response.status_code == 200
    assert webhook_response.json()["routed"] is True
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: _recent_result(_session()),
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert result.events_recovered == 1
    assert [item.created for item in RecordingRuntimeHandle.notifications] == [True, False]
    assert get_message("linear", "activity-1") is not None
    assert get_processed_event(
        "linear",
        "linear-monitor:implementation_partner:activity-1",
    )


def test_linear_monitor_recovers_missed_prompted_activity_inside_bounded_lookback(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T11:59:58Z")
    dispatcher = CaoEventDispatcher()
    register_linear_cao_events(dispatcher)
    published = []
    dispatcher.subscribe_all(
        handler=lambda event: published.append(event),
        subscription_id="test-linear-monitor",
    )

    def publish_once(payload, *, delivery_id=None, header_event=None):
        return publish_linear_provider_event(
            payload,
            delivery_id=delivery_id,
            header_event=header_event,
            dispatcher=dispatcher,
        )

    monkeypatch.setattr(monitor, "publish_linear_provider_event", publish_once)
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: _recent_result(_session(activity_id="activity-recovered")),
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert result.events_recovered == 1
    assert get_thread("linear", "session-1") is not None
    message = get_message("linear", "activity-recovered")
    assert message is not None
    assert message.body == "Can you recover this?"
    assert RecordingRuntimeHandle.notifications[0].created is True
    assert len(published) == 1
    assert isinstance(published[0], LinearIssueContextEvent)


def test_linear_monitor_recovers_missed_created_session_comment_inside_bounded_lookback(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T11:59:58Z")
    session = _session(
        activity_id="activity-later",
        comment={
            "id": "comment-1",
            "body": "@CAO Please start from this comment",
            "createdAt": "2026-05-09T11:59:59Z",
            "updatedAt": "2026-05-09T11:59:59Z",
        },
    )
    session["activities"]["nodes"] = []
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: _recent_result(session),
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert result.events_recovered == 1
    message = get_message("linear", "comment-1")
    assert message is not None
    assert message.body == "Please start from this comment"


def test_linear_monitor_does_not_recover_created_comment_outside_bounded_lookback(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T11:59:58Z")
    session = _session(
        activity_id="activity-current",
        comment={
            "id": "old-comment-1",
            "body": "@CAO This old comment should stay quiet",
            "createdAt": "2026-05-09T11:55:00Z",
            "updatedAt": "2026-05-09T11:55:00Z",
        },
    )
    session["activities"]["nodes"] = []
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: _recent_result(session),
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert result.events_recovered == 0
    assert get_message("linear", "old-comment-1") is None


def test_linear_monitor_first_run_bootstrap_initializes_without_historical_processing(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    def _unexpected_query(**_kwargs):
        raise AssertionError("bootstrap must not query Linear sessions")

    monkeypatch.setattr(app_client, "list_recent_agent_sessions", _unexpected_query)

    result = monitor.run_linear_monitor(now=NOW)

    assert result.sessions_seen == 0
    assert result.events_recovered == 0
    assert _watermark_value() == "2026-05-09T12:00:00+00:00"
    assert [diag.code for diag in result.diagnostics] == ["bootstrap_initialized"]


def test_linear_monitor_explicit_bounded_backfill_processes_recent_sessions(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict[str, Any]] = []

    def _bounded_query(**kwargs):
        calls.append(kwargs)
        return _recent_result(_session(activity_id="activity-backfill"))

    monkeypatch.setattr(app_client, "list_recent_agent_sessions", _bounded_query)

    result = monitor.run_linear_monitor(
        now=NOW,
        backfill_lookback=timedelta(minutes=5),
        page_size=7,
        max_pages=1,
        activities_page_size=3,
    )

    assert result.events_recovered == 1
    assert calls == [
        {
            "app_key": "implementation_partner",
            "page_size": 7,
            "max_pages": 1,
            "activities_page_size": 3,
        }
    ]
    assert get_message("linear", "activity-backfill") is not None


def test_linear_monitor_equal_updated_at_edge_is_reprocessed_safely(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T11:59:59Z")
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: _recent_result(_session(updated_at="2026-05-09T11:59:59Z")),
    )

    result = monitor.run_linear_monitor(now=NOW, watermark_overlap=timedelta(0))

    assert result.sessions_processed == 1
    assert result.events_recovered == 1
    assert get_message("linear", "activity-1") is not None


def test_linear_monitor_does_not_move_watermark_backward_on_quiet_pass(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T12:00:00Z")
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: _recent_result(
            _session(updated_at="2026-05-09T11:55:00Z", activity_updated_at="2026-05-09T11:55:00Z")
        ),
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert result.sessions_processed == 0
    assert _watermark_value() == "2026-05-09T12:00:00+00:00"


def test_linear_monitor_partial_page_failure_does_not_advance_watermark(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T11:59:58Z")

    def _failing_query(**_kwargs):
        raise app_client.LinearAppError("429 rate limit Bearer secret-token")

    monkeypatch.setattr(app_client, "list_recent_agent_sessions", _failing_query)

    result = monitor.run_linear_monitor(now=NOW)

    assert _watermark_value() == "2026-05-09T11:59:58Z"
    assert [diag.code for diag in result.diagnostics] == ["rate_limit"]
    assert "secret-token" not in result.diagnostics[0].message


def test_linear_monitor_page_limit_recovery_does_not_advance_watermark(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T11:59:58Z")
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: _recent_result(
            _session(activity_id="activity-page-limited"), has_more=True
        ),
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert result.events_recovered == 1
    assert _watermark_value() == "2026-05-09T11:59:58Z"
    assert "page_limit_reached" in {diag.code for diag in result.diagnostics}


def test_linear_monitor_policy_denial_does_not_advance_watermark(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T11:59:58Z")
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: _recent_result(_session(activity_id="activity-denied")),
    )
    monkeypatch.setattr(
        runtime,
        "notify_or_retry_agent_for_persisted_event",
        lambda _persisted, _provider_event, **_kwargs: None,
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert result.events_recovered == 0
    assert _watermark_value() == "2026-05-09T11:59:58Z"
    assert "delivery_not_routed" in {diag.code for diag in result.diagnostics}
    assert get_processed_event(
        "linear",
        "linear-monitor:implementation_partner:activity-denied",
    ) is None


def test_linear_monitor_skips_no_team_presences_before_query(
    runtime_inbox_db_session,
    implementation_partner_agent_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    agent = replace(
        implementation_partner_agent_factory(),
        linear=LinearConfig(app_key="implementation_partner", access_token="test-token"),
    )
    provider = LinearWorkspaceProvider(
        agent_registry=AgentRegistry({agent.id: agent}),
        preflight_credentials=False,
    )
    provider.initialize()
    monkeypatch.setattr(linear_workspace_provider, "_default_linear_workspace_provider", provider)
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("no-team presence queried")),
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert result.presences_checked == 0
    assert monitor_store.get_watermark(
        presence_id="implementation_partner",
        app_key="implementation_partner",
    ) is None


def test_linear_monitor_credential_failure_is_bounded_and_sanitized(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T11:59:58Z")

    def _failing_query(**_kwargs):
        raise app_client.LinearAppError("401 unauthorized access_token=secret-token")

    monkeypatch.setattr(app_client, "list_recent_agent_sessions", _failing_query)

    result = monitor.run_linear_monitor(now=NOW)

    assert _watermark_value() == "2026-05-09T11:59:58Z"
    assert [diag.code for diag in result.diagnostics] == ["credential_failure"]
    assert "secret-token" not in result.diagnostics[0].message


def test_linear_monitor_api_failure_is_diagnosed_without_advancing_watermark(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark("2026-05-09T11:59:58Z")
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: (_ for _ in ()).throw(app_client.LinearAppError("Linear unavailable")),
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert _watermark_value() == "2026-05-09T11:59:58Z"
    assert [diag.code for diag in result.diagnostics] == ["linear_api_failure"]


def test_linear_monitor_retries_pending_local_delivery_through_runtime_handle(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    context_id = db_module.ensure_default_workspace_context("implementation_partner").id
    create_inbox_delivery(
        "provider_conversation",
        f"agent:implementation_partner:context:{context_id}",
        "Pending Linear prompt",
    )
    monkeypatch.setattr(monitor, "AgentRuntimeHandle", RetryRecordingHandle)
    RetryRecordingHandle.calls = 0
    RetryRecordingHandle.receiver_ids = []
    monkeypatch.setattr(
        app_client, "list_recent_agent_sessions", lambda **_kwargs: _recent_result()
    )

    result = monitor.run_linear_monitor(
        now=NOW,
        backfill_lookback=timedelta(minutes=5),
    )

    assert result.notifications_retried == 1
    assert RetryRecordingHandle.calls == 1
    assert RetryRecordingHandle.receiver_ids == [
        f"agent:implementation_partner:context:{context_id}"
    ]


def test_linear_monitor_unsupported_states_and_shapes_are_diagnosed(
    linear_monitor_world,
    monkeypatch: pytest.MonkeyPatch,
):
    _store_watermark()
    session = _session(status="awaitingInput", activities_has_more=True)
    session["activities"]["nodes"].append({"content": {"type": "prompt", "body": "No id"}})
    monkeypatch.setattr(
        app_client,
        "list_recent_agent_sessions",
        lambda **_kwargs: _recent_result(session),
    )

    result = monitor.run_linear_monitor(now=NOW)

    codes = {diag.code for diag in result.diagnostics}
    assert "unsupported_agent_session_state" in codes
    assert "invalid_prompt_activity_shape" in codes
    assert "activity_page_limit_reached" in codes


def test_linear_monitor_missing_config_is_bounded_and_diagnosable(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(linear_workspace_provider, "_default_linear_workspace_provider", None)
    monkeypatch.setattr(
        linear_workspace_provider,
        "load_linear_provider_config",
        lambda **_kwargs: None,
    )

    result = monitor.run_linear_monitor(now=NOW)

    assert result.presences_checked == 0
    assert [diag.code for diag in result.diagnostics] == ["invalid_config"]


def test_recent_agent_session_query_is_bounded_and_uses_official_agent_fields(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict[str, Any]] = []

    def _graphql(query, variables, *, app_key=None, access_token=None):
        calls.append({"query": query, "variables": variables, "app_key": app_key})
        return {
            "data": {
                "agentSessions": {
                    "nodes": [
                        _session(
                            session_id=f"session-{len(calls)}",
                            activity_id=f"activity-{len(calls)}",
                            comment={
                                "id": f"comment-{len(calls)}",
                                "body": "Please recover this comment",
                                "createdAt": "2026-05-09T11:59:59Z",
                                "updatedAt": "2026-05-09T11:59:59Z",
                            },
                        )
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": f"cursor-{len(calls)}"},
                }
            }
        }

    monkeypatch.setattr(app_client, "linear_graphql", _graphql)

    result = app_client.list_recent_agent_sessions(
        app_key="implementation_partner",
        page_size=2,
        max_pages=2,
        activities_page_size=3,
    )

    assert result.has_more is True
    assert result.page_count == 2
    assert [call["variables"]["after"] for call in calls] == [None, "cursor-1"]
    query = calls[0]["query"]
    assert "agentSessions(first: $first, after: $after, orderBy: updatedAt)" in query
    for field in ("id", "status", "createdAt", "updatedAt", "appUser", "issue", "comment"):
        assert field in query
    assert "parent" in query
    assert query.count("sourceComment") == 1
    assert calls[0]["variables"] == {"first": 2, "after": None, "activitiesFirst": 3}

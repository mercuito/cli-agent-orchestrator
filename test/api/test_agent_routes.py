from __future__ import annotations

from dataclasses import dataclass as std_dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import ClassVar, Literal

from pydantic.dataclasses import dataclass

from cli_agent_orchestrator.agent import (
    Agent,
    AgentConfigError,
    LinearConfig,
    LinearToolAccessConfig,
)
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.events import (
    AgentParticipant,
    CaoCausationId,
    CaoCorrelationId,
    CaoEventDispatcher,
    CaoEventId,
    CaoEventOccurredAt,
    CaoEventSourceId,
    CaoEventSourceRef,
    CaoEventSourceType,
)
from cli_agent_orchestrator.linear.workspace_events import LinearAgentMentionedEvent
from cli_agent_orchestrator.runtime.events import (
    AgentRuntimeNotificationDeliveryEvent,
    RuntimeWorkspaceEvent,
    notification_delivery_event,
    workspace_runtime_event,
)
from cli_agent_orchestrator.services.agent_manager import AgentStatus

OCCURRED_AT = CaoEventOccurredAt(datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc))


@dataclass(frozen=True, kw_only=True)
class _ExperimentalAuditEvent:
    event_name: ClassVar[str] = "experimental_audit_event"
    kind: Literal["experimental.audit_event"] = "experimental.audit_event"

    event_id: CaoEventId
    source: CaoEventSourceRef
    occurred_at: CaoEventOccurredAt
    correlation_id: CaoCorrelationId | None
    causation_id: CaoCausationId | None
    audit_kind: str
    confidence: float
    agent_participants: tuple[AgentParticipant, ...]


@std_dataclass
class _FakeAgentManager:
    statuses: tuple[AgentStatus, ...]
    status_calls: tuple[str, ...] = ()

    def list_statuses(self, *, active=None):
        if active is None:
            return self.statuses
        return tuple(status for status in self.statuses if status.active is active)

    def status_for_agent(self, agent_id: str):
        self.status_calls = (*self.status_calls, agent_id)
        for status in self.statuses:
            if status.agent_id == agent_id:
                return status
        raise AgentConfigError(f"Unknown CAO agent: {agent_id}")


def _agent(agent_id: str = "implementation_partner") -> Agent:
    return Agent(
        id=agent_id,
        display_name="Implementation Partner",
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id.replace("_", "-"),
        prompt="# Agent\n",
        description="Developer Agent in a multi-agent system",
        model="gpt-5.2",
        reasoning_effort="medium",
        mcp_servers={"cao-mcp-server": {"command": "cao-mcp-server"}},
        tools=("bash",),
        tool_aliases={"shell": "bash"},
        tools_settings={"bash": {"timeout": 120}},
        cao_tools=("send_message",),
        skills=("coding-discipline",),
        tags=("implementation",),
        resources=("file:///repo/README.md",),
        hooks={"pre": {"command": "true"}},
        use_legacy_mcp_json=False,
        runtime_capabilities=("@builtin",),
        codex_config={"model": "gpt-5.2"},
        linear=LinearConfig(
            app_key=agent_id,
            client_id="client-1",
            client_secret="secret-1",
            oauth_redirect_uri="https://example.test/linear/oauth/callback",
            access_token="access-1",
            tool_access=(
                LinearToolAccessConfig(
                    access_id="workflow",
                    tools=("cao_linear.get_issue",),
                    issues=("CAO-1",),
                    update_fields=("title",),
                ),
            ),
        ),
    )


def _status(
    agent_id: str = "implementation_partner",
    *,
    active: bool = False,
) -> AgentStatus:
    agent = _agent(agent_id)
    return AgentStatus(
        agent_id=agent_id,
        display_name=agent.display_name,
        cli_provider=agent.cli_provider,
        workdir=agent.workdir,
        session_name=agent.session_name,
        agent=agent,
        active=active,
        active_terminal_id="abcd1234" if active else None,
        active_workspace_context_id="wctx_abc" if active else None,
        last_active_at=datetime(2026, 5, 13, 12, 0, 0) if active else None,
    )


def test_list_agents_returns_stable_status_shape(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _FakeAgentManager((_status(active=True), _status("reviewer"))),
    )

    response = client.get("/agents")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["agent_id"] == "implementation_partner"
    assert body[0]["config"]["workdir"] == "/repo"
    assert body[0]["config"]["session_name"] == "implementation-partner"
    assert body[0]["config"]["mcp_servers"] == {"cao-mcp-server": {"command": "cao-mcp-server"}}
    assert body[0]["config"]["reasoning_effort"] == "medium"
    assert body[0]["config"]["tool_aliases"] == {"shell": "bash"}
    assert body[0]["config"]["tools_settings"] == {"bash": {"timeout": 120}}
    assert body[0]["config"]["cao_tools"] == ["send_message"]
    assert body[0]["config"]["runtime_capabilities"] == ["@builtin"]
    assert body[0]["config"]["codex_config"] == {"model": "gpt-5.2"}
    assert body[0]["config"]["linear"]["app_key"] == "implementation_partner"
    assert body[0]["config"]["linear"]["client_secret_configured"] is True
    assert body[0]["config"]["linear"]["access_token_configured"] is True
    assert body[0]["config"]["linear"]["tool_access"][0]["tools"] == ["cao_linear.get_issue"]
    assert body[0]["active_terminal_id"] == "abcd1234"
    assert body[1]["agent_id"] == "reviewer"


def test_list_agents_active_filter(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _FakeAgentManager((_status(active=True), _status("reviewer"))),
    )

    response = client.get("/agents?active=true")

    assert response.status_code == 200
    assert [row["agent_id"] for row in response.json()] == ["implementation_partner"]


def test_get_agent_unknown_returns_404(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _FakeAgentManager((_status(active=True),)),
    )

    response = client.get("/agents/missing")

    assert response.status_code == 404
    assert "Unknown CAO agent" in response.json()["detail"]


def test_update_agent_allows_empty_mcp_tools_and_skills(client, monkeypatch):
    existing_agent = _agent()
    patched_agent = None
    patched_fields = None

    def _patch_agent_config(agent, *, changed_fields):
        nonlocal patched_agent, patched_fields
        patched_agent = agent
        patched_fields = changed_fields

    class _WriteThroughAgentManager:
        def status_for_agent(self, agent_id: str):
            assert patched_agent is not None
            return AgentStatus(
                agent_id=agent_id,
                display_name=patched_agent.display_name,
                cli_provider=patched_agent.cli_provider,
                workdir=patched_agent.workdir,
                session_name=patched_agent.session_name,
                agent=patched_agent,
                active=False,
            )

    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.load_agent",
        lambda agent_id: existing_agent,
    )
    monkeypatch.setattr("cli_agent_orchestrator.api.main.patch_agent_config", _patch_agent_config)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _WriteThroughAgentManager(),
    )

    response = client.put(
        "/agents/implementation_partner",
        json={
            "mcp_servers": {},
            "tools": [],
            "skills": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["config"]["mcp_servers"] == {}
    assert response.json()["config"]["tools"] == []
    assert response.json()["config"]["skills"] == []
    assert patched_fields == {"mcp_servers", "tools", "skills"}


def test_runtime_terminal_endpoint_uses_agent_manager_status(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _FakeAgentManager((_status(active=True),)),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.terminal_service.get_terminal",
        lambda terminal_id: {
            "id": terminal_id,
            "name": "developer-0000",
            "provider": "codex",
            "session_name": "cao-implementation-partner",
            "agent_id": "implementation_partner",
            "workspace_context_id": "wctx_abc",
            "status": "idle",
            "last_active": datetime(2026, 5, 13, 12, 0, 0),
        },
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.create_terminal_dashboard_token",
        lambda terminal_id: f"token-{terminal_id}",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main._agent_dashboard_request_authorized",
        lambda request, agent_id, agent_token: True,
    )

    response = client.get("/agents/runtime/implementation_partner/terminal")

    assert response.status_code == 200
    assert response.json()["terminal"]["id"] == "abcd1234"
    assert response.json()["terminal_token"] == "token-abcd1234"


def _linear_mentioned_event(
    *,
    event_id: str = "linear:agent_mentioned:event-1",
    occurred_at: CaoEventOccurredAt = OCCURRED_AT,
    source_id: str = "msg-1",
    correlation_id: str | None = "thread-1",
    causation_id: str | None = None,
    participants: tuple[AgentParticipant, ...] | None = None,
) -> LinearAgentMentionedEvent:
    return LinearAgentMentionedEvent(
        event_id=CaoEventId(event_id),
        source=CaoEventSourceRef(
            source_type=CaoEventSourceType("linear"),
            source_id=CaoEventSourceId(source_id),
        ),
        occurred_at=occurred_at,
        correlation_id=CaoCorrelationId(correlation_id) if correlation_id is not None else None,
        causation_id=CaoCausationId(causation_id) if causation_id is not None else None,
        event_type="AgentSession",
        app_key="linear-app",
        agent_id="implementation_partner",
        app_user_id="user-1",
        app_user_name="RJ Wilson",
        issue_id="issue-id-1",
        issue_identifier="CAO-96",
        issue_url="https://linear.app/yards-framework/issue/CAO-96/example",
        issue_title="Persist events",
        issue_state="Backlog",
        parent_issue_id="parent-id-1",
        parent_issue_identifier="CAO-89",
        agent_session_id="session-1",
        thread_id="thread-1",
        thread_url="https://linear.app/session/1",
        prompt_context="Please implement this.",
        message_id=source_id,
        message_body="Please implement CAO-96.",
        message_kind="comment",
        message_metadata={"visibility": "public"},
        action="create",
        should_notify_agent=True,
        suppression_reason=None,
        raw_payload={"typed_contract_field": True},
        delivery_id="delivery-1",
        metadata={"classification": "human_mention_or_prompt"},
        agent_participants=(
            participants
            if participants is not None
            else (
                AgentParticipant(
                    agent_id="implementation_partner",
                    role="mentioned",
                ),
            )
        ),
    )


def _manager_with_timeline_agents():
    return _FakeAgentManager((_status(), _status("reviewer")))


def _patch_default_agent_manager(monkeypatch, manager):
    status_calls = []
    original_status_for_agent = manager.status_for_agent

    def _status_for_agent(agent_id: str):
        status_calls.append(agent_id)
        return original_status_for_agent(agent_id)

    monkeypatch.setattr(manager, "status_for_agent", _status_for_agent)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: manager,
    )
    return status_calls


def _publish_agent_timeline_scenario(
    *,
    mention_correlation_id: str,
    broadcast_correlation_id: str,
    broadcast_partner_role: str,
    broadcast_reviewer_role: str,
    workspace_correlation_id: str,
) -> tuple[
    LinearAgentMentionedEvent,
    AgentRuntimeNotificationDeliveryEvent,
    LinearAgentMentionedEvent,
    RuntimeWorkspaceEvent,
]:
    mention = _linear_mentioned_event(
        event_id="linear:agent_mentioned:mention",
        occurred_at=OCCURRED_AT,
        correlation_id=mention_correlation_id,
    )
    delivery = notification_delivery_event(
        agent_id="implementation_partner",
        workspace_context_id="wctx-1",
        inbox_notification_id=42,
        inbox_receiver_id="implementation_partner",
        terminal_id="terminal-1",
        runtime_status="ready",
        outcome="delivered",
        attempted=True,
        delivered=True,
        error=None,
        source_kind="linear_event",
        message_body="Please implement CAO-96.",
        causing_event=mention,
    )
    delivery = replace(
        delivery,
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=1)),
    )
    broadcast = _linear_mentioned_event(
        event_id="linear:agent_mentioned:broadcast",
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=2)),
        source_id="msg-broadcast",
        correlation_id=broadcast_correlation_id,
        participants=(
            AgentParticipant(
                agent_id="implementation_partner",
                role=broadcast_partner_role,
            ),
            AgentParticipant(agent_id="reviewer", role=broadcast_reviewer_role),
        ),
    )
    workspace = workspace_runtime_event(
        workspace_context_id="wctx-1",
        action="refresh",
        runtime_status="ready",
        correlation_id=CaoCorrelationId(workspace_correlation_id),
    )
    workspace = replace(
        workspace,
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=3)),
    )
    dispatcher = CaoEventDispatcher(
        (
            LinearAgentMentionedEvent,
            AgentRuntimeNotificationDeliveryEvent,
            RuntimeWorkspaceEvent,
        ),
        persist_events=True,
    )
    for event in (mention, delivery, broadcast, workspace):
        dispatcher.publish(event)
    return mention, delivery, broadcast, workspace


def _event_ids(response_events):
    return [event["event_id"] for event in response_events]


def test_agent_timeline_openapi_preserves_public_event_envelope(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    timeline_event_schema = schemas["AgentTimelineEventResponse"]
    timeline_response_schema = schemas["AgentTimelineResponse"]
    related_response_schema = schemas["AgentRelatedEventsResponse"]
    causation_response_schema = schemas["AgentCausationRelatedEventsResponse"]
    event_data_schema = timeline_event_schema["properties"]["event_data"]

    assert timeline_event_schema["properties"]["event_type_key"] == {
        "type": "string",
        "title": "Event Type Key",
    }
    assert "event_type_key" in timeline_event_schema["required"]
    assert event_data_schema["type"] == "object"
    assert event_data_schema["additionalProperties"] is True
    assert "event_data" in timeline_event_schema["required"]
    assert timeline_response_schema["properties"]["events"]["items"] == {
        "$ref": "#/components/schemas/AgentTimelineEventResponse"
    }
    assert related_response_schema["properties"]["event"] == {
        "$ref": "#/components/schemas/AgentTimelineEventResponse"
    }
    assert related_response_schema["properties"]["correlation_events"]["items"] == {
        "$ref": "#/components/schemas/AgentTimelineEventResponse"
    }
    assert related_response_schema["properties"]["causation_events"] == {
        "$ref": "#/components/schemas/AgentCausationRelatedEventsResponse"
    }
    assert causation_response_schema["properties"]["direct_cause"]["anyOf"] == [
        {"$ref": "#/components/schemas/AgentTimelineEventResponse"},
        {"type": "null"},
    ]
    assert causation_response_schema["properties"]["direct_effects"]["items"] == {
        "$ref": "#/components/schemas/AgentTimelineEventResponse"
    }


def test_agent_timeline_route_returns_participant_index_rows(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _manager_with_timeline_agents()
    status_calls = _patch_default_agent_manager(monkeypatch, manager)
    mention, delivery, broadcast, workspace = _publish_agent_timeline_scenario(
        mention_correlation_id="thread-1",
        broadcast_correlation_id="thread-broadcast",
        broadcast_partner_role="mentioned",
        broadcast_reviewer_role="observer",
        workspace_correlation_id="workspace-refresh",
    )

    response = client.get("/agents/implementation_partner/timeline")

    assert response.status_code == 200
    body = response.json()
    assert status_calls == ["implementation_partner"]
    assert body["agent"]["agent_id"] == "implementation_partner"
    assert _event_ids(body["events"]) == [
        str(mention.event_id),
        str(delivery.event_id),
        str(broadcast.event_id),
    ]
    assert str(workspace.event_id) not in _event_ids(body["events"])
    assert db_module.get_cao_event(str(workspace.event_id)) is not None
    assert [(event["event_name"], event["participant_role"]) for event in body["events"]] == [
        ("agent_mentioned", "mentioned"),
        ("agent_runtime_notification_delivery", "delivery_target"),
        ("agent_mentioned", "mentioned"),
    ]
    assert body["events"][0]["correlation_id"] == "thread-1"
    assert body["events"][0]["event_data"]["issue_title"] == "Persist events"
    assert body["events"][0]["event_data"]["message_body"] == "Please implement CAO-96."
    assert body["events"][0]["event_data"]["raw_payload"] == {"typed_contract_field": True}
    assert body["events"][1]["event_data"]["terminal_id"] == "terminal-1"
    assert body["events"][1]["event_data"]["source_kind"] == "linear_event"
    assert body["events"][1]["event_data"]["message_body"] == "Please implement CAO-96."
    assert body["events"][1]["causation_id"] == str(mention.event_id)


def test_agent_timeline_route_preserves_broadcast_viewpoint(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _manager_with_timeline_agents()
    _patch_default_agent_manager(monkeypatch, manager)
    _, _, broadcast, _ = _publish_agent_timeline_scenario(
        mention_correlation_id="thread-1",
        broadcast_correlation_id="thread-broadcast",
        broadcast_partner_role="mentioned",
        broadcast_reviewer_role="observer",
        workspace_correlation_id="workspace-refresh",
    )

    partner_response = client.get("/agents/implementation_partner/timeline")
    reviewer_response = client.get("/agents/reviewer/timeline")

    assert partner_response.status_code == 200
    assert reviewer_response.status_code == 200
    partner_broadcast_events = [
        event
        for event in partner_response.json()["events"]
        if event["event_id"] == str(broadcast.event_id)
    ]
    assert partner_broadcast_events[0]["participant_role"] == "mentioned"
    reviewer_events = reviewer_response.json()["events"]
    assert len(reviewer_events) == 1
    reviewer_event = reviewer_events[0]
    assert {key: value for key, value in reviewer_event.items() if key != "event_data"} == {
        "event_id": str(broadcast.event_id),
        "event_name": "agent_mentioned",
        "event_type_key": (
            "cli_agent_orchestrator.linear.workspace_events.LinearAgentMentionedEvent"
        ),
        "source_type": "linear",
        "source_id": "msg-broadcast",
        "occurred_at": "2026-05-13T12:02:00",
        "correlation_id": "thread-broadcast",
        "causation_id": None,
        "participant_role": "observer",
    }
    assert reviewer_event["event_data"]["message_id"] == "msg-broadcast"
    assert reviewer_event["event_data"]["agent_participants"] == [
        {"agent_id": "implementation_partner", "role": "mentioned"},
        {"agent_id": "reviewer", "role": "observer"},
    ]


def test_agent_timeline_route_unknown_agent_returns_404(
    client,
    monkeypatch,
):
    manager = _FakeAgentManager((_status(),))
    _patch_default_agent_manager(monkeypatch, manager)

    response = client.get("/agents/missing/timeline")

    assert response.status_code == 404
    assert "Unknown CAO agent" in response.json()["detail"]


def test_agent_related_events_route_uses_envelope_threads(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _manager_with_timeline_agents()
    _patch_default_agent_manager(monkeypatch, manager)
    mention, delivery, _, _ = _publish_agent_timeline_scenario(
        mention_correlation_id="thread-1",
        broadcast_correlation_id="thread-broadcast",
        broadcast_partner_role="mentioned",
        broadcast_reviewer_role="observer",
        workspace_correlation_id="workspace-refresh",
    )

    mention_response = client.get(
        f"/agents/implementation_partner/events/{mention.event_id}/related"
    )
    delivery_response = client.get(
        f"/agents/implementation_partner/events/{delivery.event_id}/related"
    )

    assert mention_response.status_code == 200
    assert _event_ids(mention_response.json()["correlation_events"]) == [
        str(mention.event_id),
        str(delivery.event_id),
    ]
    assert mention_response.json()["event"]["event_data"]["issue_identifier"] == "CAO-96"
    assert mention_response.json()["correlation_events"][0]["event_data"]["message_body"] == (
        "Please implement CAO-96."
    )
    assert mention_response.json()["correlation_events"][1]["event_data"]["terminal_id"] == (
        "terminal-1"
    )
    assert mention_response.json()["causation_events"]["direct_cause"] is None
    assert _event_ids(mention_response.json()["causation_events"]["direct_effects"]) == [
        str(delivery.event_id)
    ]
    assert (
        mention_response.json()["causation_events"]["direct_effects"][0]["event_data"]["outcome"]
        == "delivered"
    )
    assert delivery_response.status_code == 200
    assert delivery_response.json()["causation_events"]["direct_cause"]["event_id"] == str(
        mention.event_id
    )
    assert (
        delivery_response.json()["causation_events"]["direct_cause"]["event_data"]["message_body"]
        == "Please implement CAO-96."
    )


def test_agent_related_events_route_keeps_untaught_events_related_and_roleful(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _manager_with_timeline_agents()
    _patch_default_agent_manager(monkeypatch, manager)
    root = _ExperimentalAuditEvent(
        event_id=CaoEventId("experimental:audit:event-1"),
        source=CaoEventSourceRef(
            source_type=CaoEventSourceType("audit"),
            source_id=CaoEventSourceId("audit-1"),
        ),
        occurred_at=OCCURRED_AT,
        correlation_id=CaoCorrelationId("thread-audit"),
        causation_id=None,
        audit_kind="workspace_scan",
        confidence=0.92,
        agent_participants=(
            AgentParticipant(agent_id="implementation_partner", role="participant"),
        ),
    )
    effect = replace(
        root,
        event_id=CaoEventId("experimental:audit:event-2"),
        source=CaoEventSourceRef(
            source_type=CaoEventSourceType("audit"),
            source_id=CaoEventSourceId("audit-2"),
        ),
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=1)),
        causation_id=CaoCausationId(str(root.event_id)),
        audit_kind="related_probe",
        confidence=0.73,
        agent_participants=(
            AgentParticipant(agent_id="implementation_partner", role="effect_target"),
        ),
    )
    dispatcher = CaoEventDispatcher((_ExperimentalAuditEvent,), persist_events=True)
    dispatcher.publish(effect)
    dispatcher.publish(root)

    response = client.get(f"/agents/implementation_partner/events/{root.event_id}/related")

    assert response.status_code == 200
    body = response.json()
    assert body["event"]["event_name"] == "experimental_audit_event"
    assert body["event"]["participant_role"] == "participant"
    assert body["event"]["event_data"]["audit_kind"] == "workspace_scan"
    assert _event_ids(body["correlation_events"]) == [
        str(root.event_id),
        str(effect.event_id),
    ]
    assert _event_ids(body["causation_events"]["direct_effects"]) == [str(effect.event_id)]
    assert body["causation_events"]["direct_effects"][0]["participant_role"] == ("effect_target")
    assert (
        body["causation_events"]["direct_effects"][0]["event_data"]["audit_kind"] == "related_probe"
    )


def test_agent_related_events_route_handles_missing_relatedness_and_unknown_event(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _FakeAgentManager((_status(),))
    _patch_default_agent_manager(monkeypatch, manager)
    isolated = _linear_mentioned_event(
        event_id="linear:agent_mentioned:isolated",
        correlation_id=None,
        causation_id=None,
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)
    dispatcher.publish(isolated)

    response = client.get(f"/agents/implementation_partner/events/{isolated.event_id}/related")
    missing_response = client.get("/agents/implementation_partner/events/missing-event/related")

    assert response.status_code == 200
    assert response.json()["correlation_events"] == []
    assert response.json()["causation_events"] == {
        "direct_cause": None,
        "direct_effects": [],
    }
    assert missing_response.status_code == 404
    assert "Unknown CAO event" in missing_response.json()["detail"]

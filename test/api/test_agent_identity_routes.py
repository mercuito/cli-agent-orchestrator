from __future__ import annotations

from dataclasses import dataclass as std_dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import ClassVar, Literal

from pydantic.dataclasses import dataclass

from cli_agent_orchestrator.agent_identity import AgentIdentityConfigError
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
from cli_agent_orchestrator.services.agent_identity_manager import AgentIdentityStatus

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
class _FakeIdentityManager:
    statuses: tuple[AgentIdentityStatus, ...]
    status_calls: tuple[str, ...] = ()

    def list_statuses(self, *, active=None):
        if active is None:
            return self.statuses
        return tuple(status for status in self.statuses if status.active is active)

    def status_for_identity(self, agent_id: str):
        self.status_calls = (*self.status_calls, agent_id)
        for status in self.statuses:
            if status.agent_identity_id == agent_id:
                return status
        raise AgentIdentityConfigError(f"Unknown CAO agent identity: {agent_id}")


def _status(
    agent_id: str = "implementation_partner",
    *,
    active: bool = False,
) -> AgentIdentityStatus:
    return AgentIdentityStatus(
        agent_identity_id=agent_id,
        display_name="Implementation Partner",
        agent_profile="developer",
        cli_provider="codex",
        active=active,
        active_terminal_id="abcd1234" if active else None,
        active_workspace_context_id="wctx_abc" if active else None,
        last_active_at=datetime(2026, 5, 13, 12, 0, 0) if active else None,
    )


def test_list_agent_identities_returns_stable_status_shape(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_identity_manager",
        lambda: _FakeIdentityManager((_status(active=True), _status("reviewer"))),
    )

    response = client.get("/agents/identities")

    assert response.status_code == 200
    assert response.json() == [
        {
            "agent_identity_id": "implementation_partner",
            "display_name": "Implementation Partner",
            "agent_profile": "developer",
            "cli_provider": "codex",
            "active": True,
            "active_terminal_id": "abcd1234",
            "active_workspace_context_id": "wctx_abc",
            "last_active_at": "2026-05-13T12:00:00",
        },
        {
            "agent_identity_id": "reviewer",
            "display_name": "Implementation Partner",
            "agent_profile": "developer",
            "cli_provider": "codex",
            "active": False,
            "active_terminal_id": None,
            "active_workspace_context_id": None,
            "last_active_at": None,
        },
    ]


def test_list_agent_identities_active_filter(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_identity_manager",
        lambda: _FakeIdentityManager((_status(active=True), _status("reviewer"))),
    )

    response = client.get("/agents/identities?active=true")

    assert response.status_code == 200
    assert [row["agent_identity_id"] for row in response.json()] == ["implementation_partner"]


def test_get_agent_identity_unknown_returns_404(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_identity_manager",
        lambda: _FakeIdentityManager((_status(active=True),)),
    )

    response = client.get("/agents/identities/missing")

    assert response.status_code == 404
    assert "Unknown CAO agent identity" in response.json()["detail"]


def test_runtime_terminal_endpoint_uses_identity_manager_status(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_identity_manager",
        lambda: _FakeIdentityManager((_status(active=True),)),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.terminal_service.get_terminal",
        lambda terminal_id: {
            "id": terminal_id,
            "name": "developer-0000",
            "provider": "codex",
            "session_name": "cao-implementation-partner",
            "agent_profile": "developer",
            "agent_identity_id": "implementation_partner",
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
                    agent_identity_id="implementation_partner",
                    role="mentioned",
                ),
            )
        ),
    )


def _manager_with_timeline_identities(
    agent_identity_manager_factory,
    implementation_partner_identity_factory,
):
    return agent_identity_manager_factory(
        implementation_partner_identity_factory(),
        implementation_partner_identity_factory(
            id="reviewer",
            display_name="Reviewer",
            session_name="reviewer",
        ),
    )


def _patch_default_identity_manager(monkeypatch, manager):
    status_calls = []
    original_status_for_identity = manager.status_for_identity

    def _status_for_identity(agent_id: str):
        status_calls.append(agent_id)
        return original_status_for_identity(agent_id)

    monkeypatch.setattr(manager, "status_for_identity", _status_for_identity)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_identity_manager",
        lambda: manager,
    )
    return status_calls


def _publish_identity_timeline_scenario(
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
        agent_identity_id="implementation_partner",
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
                agent_identity_id="implementation_partner",
                role=broadcast_partner_role,
            ),
            AgentParticipant(agent_identity_id="reviewer", role=broadcast_reviewer_role),
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


def test_agent_identity_timeline_openapi_preserves_public_event_envelope(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    timeline_event_schema = schemas["AgentIdentityTimelineEventResponse"]
    timeline_response_schema = schemas["AgentIdentityTimelineResponse"]
    related_response_schema = schemas["AgentIdentityRelatedEventsResponse"]
    causation_response_schema = schemas["AgentIdentityCausationRelatedEventsResponse"]
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
        "$ref": "#/components/schemas/AgentIdentityTimelineEventResponse"
    }
    assert related_response_schema["properties"]["event"] == {
        "$ref": "#/components/schemas/AgentIdentityTimelineEventResponse"
    }
    assert related_response_schema["properties"]["correlation_events"]["items"] == {
        "$ref": "#/components/schemas/AgentIdentityTimelineEventResponse"
    }
    assert related_response_schema["properties"]["causation_events"] == {
        "$ref": "#/components/schemas/AgentIdentityCausationRelatedEventsResponse"
    }
    assert causation_response_schema["properties"]["direct_cause"]["anyOf"] == [
        {"$ref": "#/components/schemas/AgentIdentityTimelineEventResponse"},
        {"type": "null"},
    ]
    assert causation_response_schema["properties"]["direct_effects"]["items"] == {
        "$ref": "#/components/schemas/AgentIdentityTimelineEventResponse"
    }


def test_agent_identity_timeline_route_returns_participant_index_rows(
    client,
    monkeypatch,
    runtime_inbox_db_session,
    agent_identity_manager_factory,
    implementation_partner_identity_factory,
):
    manager = _manager_with_timeline_identities(
        agent_identity_manager_factory,
        implementation_partner_identity_factory,
    )
    status_calls = _patch_default_identity_manager(monkeypatch, manager)
    mention, delivery, broadcast, workspace = _publish_identity_timeline_scenario(
        mention_correlation_id="thread-1",
        broadcast_correlation_id="thread-broadcast",
        broadcast_partner_role="mentioned",
        broadcast_reviewer_role="observer",
        workspace_correlation_id="workspace-refresh",
    )

    response = client.get("/agents/identities/implementation_partner/timeline")

    assert response.status_code == 200
    body = response.json()
    assert status_calls == ["implementation_partner"]
    assert body["identity"]["agent_identity_id"] == "implementation_partner"
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


def test_agent_identity_timeline_route_preserves_broadcast_viewpoint(
    client,
    monkeypatch,
    runtime_inbox_db_session,
    agent_identity_manager_factory,
    implementation_partner_identity_factory,
):
    manager = _manager_with_timeline_identities(
        agent_identity_manager_factory,
        implementation_partner_identity_factory,
    )
    _patch_default_identity_manager(monkeypatch, manager)
    _, _, broadcast, _ = _publish_identity_timeline_scenario(
        mention_correlation_id="thread-1",
        broadcast_correlation_id="thread-broadcast",
        broadcast_partner_role="mentioned",
        broadcast_reviewer_role="observer",
        workspace_correlation_id="workspace-refresh",
    )

    partner_response = client.get("/agents/identities/implementation_partner/timeline")
    reviewer_response = client.get("/agents/identities/reviewer/timeline")

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
        {"agent_identity_id": "implementation_partner", "role": "mentioned"},
        {"agent_identity_id": "reviewer", "role": "observer"},
    ]


def test_agent_identity_timeline_route_unknown_identity_returns_404(
    client,
    monkeypatch,
    agent_identity_manager_factory,
    implementation_partner_identity_factory,
):
    manager = agent_identity_manager_factory(implementation_partner_identity_factory())
    _patch_default_identity_manager(monkeypatch, manager)

    response = client.get("/agents/identities/missing/timeline")

    assert response.status_code == 404
    assert "Unknown CAO agent identity" in response.json()["detail"]


def test_agent_identity_related_events_route_uses_envelope_threads(
    client,
    monkeypatch,
    runtime_inbox_db_session,
    agent_identity_manager_factory,
    implementation_partner_identity_factory,
):
    manager = _manager_with_timeline_identities(
        agent_identity_manager_factory,
        implementation_partner_identity_factory,
    )
    _patch_default_identity_manager(monkeypatch, manager)
    mention, delivery, _, _ = _publish_identity_timeline_scenario(
        mention_correlation_id="thread-1",
        broadcast_correlation_id="thread-broadcast",
        broadcast_partner_role="mentioned",
        broadcast_reviewer_role="observer",
        workspace_correlation_id="workspace-refresh",
    )

    mention_response = client.get(
        f"/agents/identities/implementation_partner/events/{mention.event_id}/related"
    )
    delivery_response = client.get(
        f"/agents/identities/implementation_partner/events/{delivery.event_id}/related"
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


def test_agent_identity_related_events_route_keeps_untaught_events_related_and_roleful(
    client,
    monkeypatch,
    runtime_inbox_db_session,
    agent_identity_manager_factory,
    implementation_partner_identity_factory,
):
    manager = _manager_with_timeline_identities(
        agent_identity_manager_factory,
        implementation_partner_identity_factory,
    )
    _patch_default_identity_manager(monkeypatch, manager)
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
            AgentParticipant(agent_identity_id="implementation_partner", role="participant"),
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
            AgentParticipant(agent_identity_id="implementation_partner", role="effect_target"),
        ),
    )
    dispatcher = CaoEventDispatcher((_ExperimentalAuditEvent,), persist_events=True)
    dispatcher.publish(effect)
    dispatcher.publish(root)

    response = client.get(
        f"/agents/identities/implementation_partner/events/{root.event_id}/related"
    )

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


def test_agent_identity_related_events_route_handles_missing_relatedness_and_unknown_event(
    client,
    monkeypatch,
    runtime_inbox_db_session,
    agent_identity_manager_factory,
    implementation_partner_identity_factory,
):
    manager = agent_identity_manager_factory(implementation_partner_identity_factory())
    _patch_default_identity_manager(monkeypatch, manager)
    isolated = _linear_mentioned_event(
        event_id="linear:agent_mentioned:isolated",
        correlation_id=None,
        causation_id=None,
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)
    dispatcher.publish(isolated)

    response = client.get(
        f"/agents/identities/implementation_partner/events/{isolated.event_id}/related"
    )
    missing_response = client.get(
        "/agents/identities/implementation_partner/events/missing-event/related"
    )

    assert response.status_code == 200
    assert response.json()["correlation_events"] == []
    assert response.json()["causation_events"] == {
        "direct_cause": None,
        "direct_effects": [],
    }
    assert missing_response.status_code == 404
    assert "Unknown CAO event" in missing_response.json()["detail"]

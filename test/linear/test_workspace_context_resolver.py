"""Tests for Linear workspace context resolution."""

from __future__ import annotations

from cli_agent_orchestrator.agent_identity import AgentIdentity, AgentWorkspaceContextConfig
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.workspace_context_store import (
    WORKSPACE_CONTEXT_ROLE_CHILD_WORK_ITEM,
    WORKSPACE_CONTEXT_ROLE_INTERACTION,
)
from cli_agent_orchestrator.events import CaoEvent, agent_participants_for
from cli_agent_orchestrator.linear.workspace_context_resolver import (
    LINEAR_PLANNING_RESOLVER_ID,
    register_linear_workspace_context_resolver,
    resolve_linear_workspace_event,
)
from cli_agent_orchestrator.linear.workspace_events import (
    LINEAR_AGENT_PARTICIPANT_ROLE_DELEGATED,
    LINEAR_AGENT_PARTICIPANT_ROLE_LIFECYCLE_ACTIVITY,
    LINEAR_AGENT_PARTICIPANT_ROLE_MENTIONED,
    LINEAR_AGENT_PARTICIPANT_ROLE_PROMPTED,
    LINEAR_AGENT_PARTICIPANT_ROLE_STOP_REQUESTED,
    LinearAgentMentionedEvent,
    LinearAgentSessionLifecycleActivityEvent,
    LinearAgentSessionPromptedEvent,
    LinearAgentSessionStopRequestedEvent,
    LinearIssueDelegatedToAgentEvent,
    publish_linear_provider_event,
)
from cli_agent_orchestrator.workspace_contexts import resolve_workspace_context_for_identity


def _agent_session_payload(issue: dict | None, *, session_id: str = "session-1") -> dict:
    session = {
        "id": session_id,
        "creator": {"id": "user-1", "name": "User"},
    }
    if issue is not None:
        session["issue"] = issue
    return {
        "type": "AgentSessionEvent",
        "action": "prompted",
        "data": {
            "agentSession": session,
        },
    }


def _published_event(payload: dict) -> CaoEvent:
    publication = publish_linear_provider_event(payload)
    assert publication is not None
    return publication.event


def _context_identity() -> AgentIdentity:
    return AgentIdentity(
        id="implementation_partner",
        display_name="Implementation Partner",
        agent_profile="developer",
        cli_provider="codex",
        workdir="/tmp/cao",
        session_name="implementation-partner",
        workspace_context=AgentWorkspaceContextConfig(
            enabled=True,
            resolver_id=LINEAR_PLANNING_RESOLVER_ID,
        ),
    )


def test_linear_issue_without_parent_creates_boundary_context(runtime_inbox_db_session):
    resolution = resolve_linear_workspace_event(
        _published_event(_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"}))
    )

    assert resolution is not None
    assert resolution.boundary_provider_id == "linear"
    assert resolution.boundary_object_type == "issue"
    assert resolution.boundary_object_id == "CAO-79"
    assert (
        db_module.get_workspace_context_for_object(
            provider_id="linear",
            object_type="issue",
            object_id="CAO-79",
        ).id
        == resolution.workspace_context_id
    )


def test_linear_child_issue_groups_under_parent_boundary(runtime_inbox_db_session):
    resolution = resolve_linear_workspace_event(
        _published_event(
            _agent_session_payload(
                {
                    "id": "issue-80",
                    "identifier": "CAO-80",
                    "parent": {"id": "issue-79", "identifier": "CAO-79"},
                },
                session_id="session-child",
            )
        )
    )

    assert resolution is not None
    assert resolution.boundary_object_id == "CAO-79"
    child_context = db_module.get_workspace_context_for_object(
        provider_id="linear",
        object_type="issue",
        object_id="CAO-80",
    )
    session_context = db_module.get_workspace_context_for_object(
        provider_id="linear",
        object_type="agent_session",
        object_id="session-child",
    )
    assert child_context is not None
    assert session_context is not None
    assert child_context.id == resolution.workspace_context_id
    assert session_context.id == resolution.workspace_context_id
    with db_module.SessionLocal() as session:
        roles = {
            row.object_id: row.role
            for row in session.query(db_module.WorkspaceContextObjectMappingModel).all()
        }
    assert roles["CAO-80"] == WORKSPACE_CONTEXT_ROLE_CHILD_WORK_ITEM
    assert roles["session-child"] == WORKSPACE_CONTEXT_ROLE_INTERACTION


def test_existing_child_boundary_context_takes_precedence_over_parent_grouping(
    runtime_inbox_db_session,
):
    child_boundary = db_module.ensure_workspace_context_for_boundary(
        resolver_id=LINEAR_PLANNING_RESOLVER_ID,
        provider_id="linear",
        object_type="issue",
        object_id="CAO-80",
    )

    resolution = resolve_linear_workspace_event(
        _published_event(
            _agent_session_payload(
                {
                    "id": "issue-80",
                    "identifier": "CAO-80",
                    "parent": {"id": "issue-79", "identifier": "CAO-79"},
                },
                session_id="session-child",
            )
        )
    )

    assert resolution is not None
    assert resolution.workspace_context_id == child_boundary.id
    assert resolution.boundary_object_id == "CAO-80"
    assert (
        db_module.get_workspace_context_for_object(
            provider_id="linear",
            object_type="agent_session",
            object_id="session-child",
        ).id
        == child_boundary.id
    )
    assert (
        db_module.get_workspace_context_for_object(
            provider_id="linear",
            object_type="issue",
            object_id="CAO-79",
        )
        is None
    )


def test_linear_event_without_issue_does_not_guess_context(runtime_inbox_db_session):
    assert (
        resolve_linear_workspace_event(
            _published_event(_agent_session_payload(None, session_id="s"))
        )
        is None
    )


def test_identity_resolver_explicitly_resolves_traced_linear_provider_event(
    runtime_inbox_db_session,
):
    register_linear_workspace_context_resolver()
    resolution = resolve_workspace_context_for_identity(
        _context_identity(),
        _published_event(_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"})),
    )

    assert resolution is not None
    assert resolution.boundary_object_id == "CAO-79"


def test_linear_provider_publication_uses_semantic_event_names():
    cases = {
        "human_mention_or_prompt": (
            _agent_session_payload({"id": "issue-79", "identifier": "CAO-79"}),
            LinearAgentMentionedEvent,
        ),
        "human_issue_delegation": (
            _agent_session_payload(
                {
                    "id": "issue-79",
                    "identifier": "CAO-79",
                    "delegate": {"id": "delegate-1", "name": "CAO"},
                }
            ),
            LinearIssueDelegatedToAgentEvent,
        ),
        "follow_up_user_prompt": (
            {
                **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"}),
                "data": {
                    **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"})["data"],
                    "agentActivity": {"id": "activity-1", "type": "prompt", "body": "continue"},
                },
            },
            LinearAgentSessionPromptedEvent,
        ),
        "stop_or_cancel": (
            {
                **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"}),
                "data": {
                    **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"})["data"],
                    "agentActivity": {
                        "id": "activity-1",
                        "content": {"signal": "stop", "body": "stop"},
                    },
                },
            },
            LinearAgentSessionStopRequestedEvent,
        ),
        "agent_lifecycle_activity": (
            {
                **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"}),
                "data": {
                    **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"})["data"],
                    "agentActivity": {
                        "id": "activity-1",
                        "type": "response",
                        "body": "done",
                    },
                },
            },
            LinearAgentSessionLifecycleActivityEvent,
        ),
    }

    for payload, event_type in cases.values():
        publication = publish_linear_provider_event(payload)

        assert publication is not None
        assert isinstance(publication.event, event_type)


def test_linear_provider_publication_carries_cao_metadata_and_agent_participants():
    payload = {
        **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"}),
        "_cao_linear_agent_id": "implementation_partner",
        "webhookTimestamp": "2026-05-12T12:00:00Z",
    }

    publication = publish_linear_provider_event(payload, delivery_id="delivery-1")

    assert publication is not None
    event = publication.event
    assert isinstance(event, LinearAgentMentionedEvent)
    assert event.event_id.startswith("linear:agent_mentioned:")
    assert event.source.source_type == "linear"
    assert event.source.source_id == "delivery-1"
    assert event.occurred_at.isoformat() == "2026-05-12T12:00:00+00:00"
    assert event.correlation_id == "session-1"
    assert agent_participants_for(event) == (
        type(event.agent_participants[0])(
            agent_identity_id="implementation_partner",
            role=LINEAR_AGENT_PARTICIPANT_ROLE_MENTIONED,
        ),
    )


def test_linear_provider_publication_assigns_linear_owned_participant_roles():
    cases = [
        (
            {
                **_agent_session_payload(
                    {
                        "id": "issue-79",
                        "identifier": "CAO-79",
                        "delegate": {"id": "delegate-1", "name": "CAO"},
                    }
                ),
                "_cao_linear_agent_id": "implementation_partner",
            },
            LINEAR_AGENT_PARTICIPANT_ROLE_DELEGATED,
        ),
        (
            {
                **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"}),
                "_cao_linear_agent_id": "implementation_partner",
                "data": {
                    **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"})["data"],
                    "agentActivity": {"id": "activity-1", "type": "prompt", "body": "continue"},
                },
            },
            LINEAR_AGENT_PARTICIPANT_ROLE_PROMPTED,
        ),
        (
            {
                **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"}),
                "_cao_linear_agent_id": "implementation_partner",
                "data": {
                    **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"})["data"],
                    "agentActivity": {
                        "id": "activity-1",
                        "content": {"signal": "stop", "body": "stop"},
                    },
                },
            },
            LINEAR_AGENT_PARTICIPANT_ROLE_STOP_REQUESTED,
        ),
        (
            {
                **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"}),
                "_cao_linear_agent_id": "implementation_partner",
                "data": {
                    **_agent_session_payload({"id": "issue-79", "identifier": "CAO-79"})["data"],
                    "agentActivity": {
                        "id": "activity-1",
                        "type": "response",
                        "body": "done",
                    },
                },
            },
            LINEAR_AGENT_PARTICIPANT_ROLE_LIFECYCLE_ACTIVITY,
        ),
    ]

    for payload, role in cases:
        publication = publish_linear_provider_event(payload)

        assert publication is not None
        assert agent_participants_for(publication.event)[0].role == role


def test_linear_provider_publication_carries_typed_context_fields():
    publication = publish_linear_provider_event(
        _agent_session_payload(
            {
                "id": "issue-80",
                "identifier": "CAO-80",
                "parent": {"id": "issue-79", "identifier": "CAO-79"},
            },
            session_id="session-child",
        )
    )

    assert publication is not None
    assert isinstance(publication.event, LinearAgentMentionedEvent)
    assert publication.event.issue_id == "issue-80"
    assert publication.event.issue_identifier == "CAO-80"
    assert publication.event.parent_issue_id == "issue-79"
    assert publication.event.parent_issue_identifier == "CAO-79"
    assert publication.event.agent_session_id == "session-child"
    assert publication.event.canonical_issue_id == "CAO-80"
    assert publication.event.boundary_issue_id == "CAO-79"

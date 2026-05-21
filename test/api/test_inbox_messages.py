"""Tests for agent inbox HTTP endpoints."""

from unittest.mock import patch

import pytest

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig
from cli_agent_orchestrator.inbox import (
    list_notifications,
    send as create_inbox_notification,
    update_notification_statuses,
)
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.workspace_contexts import WorkspaceContextResolution
from cli_agent_orchestrator.workspaces import (
    DEFAULT_WORKSPACE_ID,
    WorkspaceCollaborationManager,
    Workspace,
    WorkspaceRegistry,
    WorkspaceTeam,
    WorkspaceTeamRegistry,
    WorkspaceTeamStore,
)


class TestGetInboxMessagesEndpoint:
    """GET /agents/{agent_id}/inbox/messages."""

    def test_get_all_messages_uses_semantic_deliveries(self, client, runtime_inbox_db_session):
        create_inbox_notification("abcdef12", "Hello world", sender_agent_id="sender1")
        create_inbox_notification("abcdef12", "Another message", sender_agent_id="sender2")

        response = client.get("/agents/abcdef12/inbox/messages")

        assert response.status_code == 200
        data = response.json()
        assert data[0] == {
            "notification_id": 1,
            "sender_agent_id": "sender1",
            "receiver_agent_id": "abcdef12",
            "body": "Hello world",
            "status": "pending",
            "created_at": data[0]["created_at"],
        }
        assert data[1]["sender_agent_id"] == "sender2"
        assert data[1]["body"] == "Another message"

    def test_get_messages_with_status_and_limit(self, client, runtime_inbox_db_session):
        pending = create_inbox_notification(
            "abcdef12",
            "Pending message",
            sender_agent_id="sender1",
        )
        delivered = create_inbox_notification(
            "abcdef12",
            "Delivered message",
            sender_agent_id="sender2",
        )
        update_notification_statuses([delivered.id], MessageStatus.DELIVERED)

        response = client.get("/agents/abcdef12/inbox/messages?status=pending&limit=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["notification_id"] == pending.id
        assert data[0]["status"] == "pending"

    def test_invalid_status_parameter(self, client):
        response = client.get("/agents/abcdef12/inbox/messages?status=invalid_status")

        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    def test_limit_exceeds_maximum(self, client):
        response = client.get("/agents/abcdef12/inbox/messages?limit=150")

        assert response.status_code == 422

    def test_database_error_handling(self, client):
        with patch("cli_agent_orchestrator.api.main.list_notifications") as mock_list:
            mock_list.side_effect = Exception("Database connection failed")

            response = client.get("/agents/abcdef12/inbox/messages")

        assert response.status_code == 500
        assert "Failed to retrieve inbox messages" in response.json()["detail"]

    def test_agent_not_found_error(self, client):
        with patch("cli_agent_orchestrator.api.main.list_notifications") as mock_list:
            mock_list.side_effect = ValueError("Agent not found")

            response = client.get("/agents/deadbeef/inbox/messages")

        assert response.status_code == 404
        assert "Agent not found" in response.json()["detail"]

    def test_empty_message_list(self, client, runtime_inbox_db_session):
        response = client.get("/agents/abcdef12/inbox/messages")

        assert response.status_code == 200
        assert response.json() == []


class TestCreateInboxMessageEndpoint:
    """POST /agents/{agent_id}/inbox/messages."""

    def test_create_message_returns_notification_and_durable_message_ids(
        self,
        client,
        runtime_inbox_db_session,
    ):
        with patch("cli_agent_orchestrator.api.main._require_inbox_message_policy"):
            response = client.post(
                "/agents/abcdef12/inbox/messages",
                params={"sender_agent_id": "sender1", "body": "Hello world"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["notification_id"] == 1
        assert body["sender_agent_id"] == "sender1"
        assert body["receiver_agent_id"] == "abcdef12"
        assert body["body"] == "Hello world"
        assert "id" not in body
        persisted = list_notifications("abcdef12")
        assert len(persisted) == 1
        assert persisted[0].body == "Hello world"

    def test_rejects_cross_team_message_before_inbox_persistence(
        self,
        client,
        runtime_inbox_db_session,
    ):
        from fastapi import HTTPException

        with patch(
            "cli_agent_orchestrator.api.main._require_inbox_message_policy",
            side_effect=HTTPException(
                status_code=403,
                detail="Workspace team collaboration rejected",
            ),
        ):
            response = client.post(
                "/agents/receiver/inbox/messages",
                params={"sender_agent_id": "sender", "body": "Hello world"},
            )

        assert response.status_code == 403
        assert "Workspace team collaboration rejected" in response.json()["detail"]
        assert list_notifications("receiver") == []

    def test_allows_same_team_message_before_inbox_persistence(
        self,
        client,
        runtime_inbox_db_session,
    ):
        with patch("cli_agent_orchestrator.api.main._require_inbox_message_policy"):
            response = client.post(
                "/agents/receiver/inbox/messages",
                params={"sender_agent_id": "sender", "body": "Hello world"},
            )

        assert response.status_code == 200
        assert list_notifications("receiver")[0].sender_agent_id == "sender"


def _agent(agent_id: str, team: str) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/tmp",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(team=team),
    )


def _resolver(_event):
    return WorkspaceContextResolution(
        workspace_context_id="wctx",
        resolver_id="test",
        boundary_provider_id="test",
        boundary_object_type="issue",
        boundary_object_id="CAO-1",
    )


def _patch_inbox_policy(monkeypatch, tmp_path, *, sender_team: str, receiver_team: str) -> None:
    from cli_agent_orchestrator.services import collaboration_policy

    workspace_registry = WorkspaceRegistry(
        (
            Workspace(
                id=DEFAULT_WORKSPACE_ID,
                display_name="CAO Default",
                providers=("example",),
                resolver=_resolver,
            ),
        )
    )
    team_store = WorkspaceTeamStore(
        tmp_path / "workspace-teams.json",
        bootstrap_teams=(
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace=DEFAULT_WORKSPACE_ID,
            ),
            WorkspaceTeam(
                id="research",
                display_name="Research",
                workspace=DEFAULT_WORKSPACE_ID,
            ),
        ),
    )
    manager = WorkspaceCollaborationManager(
        workspace_registry=workspace_registry,
        team_registry=WorkspaceTeamRegistry(team_store),
        agent_registry=AgentRegistry(
            {
                "sender": _agent("sender", sender_team),
                "receiver": _agent("receiver", receiver_team),
            }
        ),
        provider_adapters={},
    )

    def _metadata(terminal_id: str):
        if terminal_id == "aaaaaaaa":
            return {"id": terminal_id, "agent_id": "sender"}
        if terminal_id == "bbbbbbbb":
            return {"id": terminal_id, "agent_id": "receiver"}
        return None

    monkeypatch.setattr(collaboration_policy.db_module, "get_terminal_metadata", _metadata)
    monkeypatch.setattr(
        collaboration_policy,
        "default_workspace_collaboration_manager",
        lambda: manager,
    )

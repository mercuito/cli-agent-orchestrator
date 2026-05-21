"""Tests for routing inbox replies back to provider-backed provider conversation threads."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig, LinearConfig
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base, create_inbox_delivery, create_terminal
from cli_agent_orchestrator.inbox.models import Notification
from cli_agent_orchestrator.linear.workspace_adapter import LinearWorkspaceAdapter
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.provider_conversations.inbox_bridge import (
    PROVIDER_CONVERSATION_INBOX_SOURCE_KIND,
    create_notification_for_message,
)
from cli_agent_orchestrator.provider_conversations.persistence import (
    list_messages,
    upsert_message,
    upsert_thread,
)
from cli_agent_orchestrator.provider_conversations.reply_service import (
    ProviderConversationReplyDeliveryError,
    ProviderConversationReplyNotFoundError,
    ProviderConversationReplyUnsupportedSourceError,
    reply_to_provider_conversation,
)
from cli_agent_orchestrator.services.tool_service import ToolAccessDecision
from cli_agent_orchestrator.workspaces import (
    DEFAULT_WORKSPACE_ID,
    WorkspaceCollaborationManager,
    WorkspaceTeam,
    WorkspaceTeamRegistry,
    default_workspace_registry,
)


class _TeamStore:
    def __init__(self, teams: tuple[WorkspaceTeam, ...]) -> None:
        self._teams = {team.id: team for team in teams}

    def get(self, team_id: str) -> WorkspaceTeam:
        return self._teams[team_id]

    def list(self) -> tuple[WorkspaceTeam, ...]:
        return tuple(self._teams.values())


@pytest.fixture
def test_session(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    monkeypatch.setattr(
        "cli_agent_orchestrator.provider_conversations.inbox_authorization.default_tool_service",
        lambda: _ProviderInboxToolService(),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.provider_conversations.inbox_bridge.default_tool_service",
        lambda: _ProviderInboxToolService(),
    )
    return TestSession


class _ProviderInboxToolService:
    def provider_conversation_decision(self, *args, **kwargs) -> ToolAccessDecision:
        return ToolAccessDecision.allow(reason="provider_conversation_allowed")

    def provider_conversation_decision_for_inbox(self, *args, **kwargs) -> ToolAccessDecision:
        return ToolAccessDecision.allow(reason="provider_conversation_allowed")


def _provider_inbox_collaboration_manager() -> WorkspaceCollaborationManager:
    agent = Agent(
        id="implementation_partner",
        display_name="Implementation Partner",
        cli_provider="codex",
        workdir="/repo",
        session_name="implementation-partner",
        prompt="",
        workspace=AgentWorkspaceConfig(team="cao_delivery"),
        linear=LinearConfig(app_key="implementation_partner", access_token="token"),
    )
    return WorkspaceCollaborationManager(
        workspace_registry=default_workspace_registry(),
        agent_registry=AgentRegistry({agent.id: agent}),
        provider_adapters={"linear": LinearWorkspaceAdapter()},
        team_registry=WorkspaceTeamRegistry(
            _TeamStore(
                (
                    WorkspaceTeam(
                        id="cao_delivery",
                        display_name="CAO Delivery",
                        workspace=DEFAULT_WORKSPACE_ID,
                    ),
                )
            )
        ),
    )


def _ensure_reply_terminal() -> None:
    if db_module.get_terminal_metadata("terminal-a") is not None:
        return
    create_terminal(
        "terminal-a",
        "session",
        "window",
        "codex",
        agent_id="implementation_partner",
        workspace_context_id=db_module.ensure_default_workspace_context(
            "implementation_partner"
        ).id,
    )


def _provider_conversation_inbox_message() -> tuple[int, int]:
    _ensure_reply_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="thread-1",
        external_url="https://linear.app/agent-session/thread-1",
        kind="conversation",
        metadata={"linear_app_key": "implementation_partner"},
    )
    inbound = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="message-1",
        direction="inbound",
        kind="prompt",
        body="Can you reply?",
    )
    notification = create_notification_for_message(
        provider_message_id=inbound.id,
        receiver_id="terminal-a",
        authorized_agent_id="implementation_partner",
    )
    return notification.delivery.notification.id, inbound.id


def _reply(notification_id: int, body: str, **kwargs):
    _ensure_reply_terminal()
    delivery = db_module.get_inbox_delivery(notification_id)
    assert delivery is not None
    return reply_to_provider_conversation(
        delivery.notification,
        body,
        caller_agent_id="implementation_partner",
        **kwargs,
    )


def test_successful_reply_resolves_inbox_thread_and_linear_provider(test_session, monkeypatch):
    notification_id, _ = _provider_conversation_inbox_message()
    create_activity = Mock(return_value={"id": "reply-1"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        create_activity,
    )

    result = _reply(notification_id, "I am on it")

    assert result.delivery.notification.id == notification_id
    assert result.thread.external_id == "thread-1"
    assert result.outbound_message.direction == "outbound"
    assert result.outbound_message.state == "delivered"
    assert result.outbound_message.external_id == "reply-1"
    assert result.outbound_message.metadata == {
        "inbox_notification_id": notification_id,
        "provider_reply_ref": {
            "provider": "linear",
            "id": "reply-1",
            "url": None,
        },
        "reply_status": "delivered",
    }
    create_activity.assert_called_once_with(
        "thread-1",
        {"type": "response", "body": "I am on it"},
        app_key="implementation_partner",
    )


def test_provider_reply_uses_thread_external_id_not_message_ref(test_session, monkeypatch):
    notification_id, inbound_id = _provider_conversation_inbox_message()
    create_activity = Mock(return_value={"id": "reply-1"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        create_activity,
    )

    _reply(notification_id, "Thread-level reply")

    inbound = list_messages(1)[0]
    assert inbound.id == inbound_id
    assert create_activity.call_args.args[0] == "thread-1"
    assert create_activity.call_args.args[0] != inbound.external_id


def test_successful_provider_response_is_recorded_durably(test_session, monkeypatch):
    notification_id, _ = _provider_conversation_inbox_message()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        Mock(return_value={"id": "reply-1"}),
    )

    result = _reply(notification_id, "Persist me")

    messages = list_messages(result.thread.id)
    assert [message.direction for message in messages] == ["inbound", "outbound"]
    assert messages[1].id == result.outbound_message.id
    assert messages[1].body == "Persist me"
    assert messages[1].state == "delivered"


def test_provider_error_records_visible_failed_state(test_session, monkeypatch):
    notification_id, _ = _provider_conversation_inbox_message()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        Mock(side_effect=RuntimeError("provider is down")),
    )

    with pytest.raises(ProviderConversationReplyDeliveryError, match="provider reply failed"):
        _reply(notification_id, "This will fail")

    failed = list_messages(1)[-1]
    assert failed.direction == "outbound"
    assert failed.state == "failed"
    assert failed.body == "This will fail"
    assert failed.metadata == {
        "error": "provider is down",
        "error_type": "RuntimeError",
        "inbox_notification_id": notification_id,
        "reply_status": "failed",
    }


def test_unsupported_provider_records_visible_failed_state(test_session):
    _ensure_reply_terminal()
    thread = upsert_thread(
        provider="example",
        external_id="thread-unsupported",
        kind="conversation",
    )
    inbound = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-unsupported",
        direction="inbound",
        kind="prompt",
        body="Can you reply?",
    )
    notification_id = create_notification_for_message(
        provider_message_id=inbound.id,
        receiver_id="terminal-a",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id

    with pytest.raises(
        ProviderConversationReplyDeliveryError, match="not supported for inbox replies"
    ):
        _reply(notification_id, "No supported provider")

    failed = list_messages(thread.id)[-1]
    assert failed.direction == "outbound"
    assert failed.state == "failed"
    assert failed.metadata["error_type"] == "ProviderConversationReplyUnsupportedSourceError"
    assert failed.metadata["error"] == "provider 'example' is not supported for inbox replies"


def test_missing_notification_id_fails_clearly(test_session):
    notification = Notification(
        id=999,
        receiver_agent_id="terminal-a",
        body="Missing provider message",
        source_kind=PROVIDER_CONVERSATION_INBOX_SOURCE_KIND,
        source_id="999",
        status=MessageStatus.PENDING,
        created_at=datetime(2026, 1, 1),
    )

    with pytest.raises(
        ProviderConversationReplyNotFoundError, match="inbox notification 999 not found"
    ):
        reply_to_provider_conversation(
            notification,
            "No inbox",
            caller_agent_id="implementation_partner",
        )


def test_non_provider_conversation_source_fails_as_unsupported(test_session):
    delivery = create_inbox_delivery(
        "worker-a",
        "terminal-a",
        "Plain terminal message",
        source_kind="terminal",
        source_id="worker-a",
    )

    with pytest.raises(
        ProviderConversationReplyUnsupportedSourceError,
        match="source_kind 'terminal' is not supported",
    ):
        _reply(delivery.notification.id, "No provider conversation target")


def test_missing_provider_conversation_thread_source_fails_clearly(test_session):
    delivery = create_inbox_delivery(
        "provider_conversation",
        "terminal-a",
        "Provider conversation update",
        source_kind=PROVIDER_CONVERSATION_INBOX_SOURCE_KIND,
        source_id="999",
    )

    with pytest.raises(
        ProviderConversationReplyNotFoundError,
        match=f"provider conversation message 999 for inbox notification {delivery.notification.id} not found",
    ):
        _reply(delivery.notification.id, "No durable thread")

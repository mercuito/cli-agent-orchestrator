"""Tests for CAO MCP inbox read/reply tools."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig, LinearConfig
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import (
    Base,
    create_inbox_delivery,
    create_inbox_notification_event,
    create_terminal,
)
from cli_agent_orchestrator.inbox import PlainSource
from cli_agent_orchestrator.inbox import send as send_inbox_message
from cli_agent_orchestrator.linear.workspace_adapter import LinearWorkspaceAdapter
from cli_agent_orchestrator.mcp_server.server import (
    _read_inbox_message_impl,
    _reply_to_inbox_message_impl,
    read_inbox_message,
)
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.linear.inbox_bridge import (
    PROVIDER_CONVERSATION_INBOX_SOURCE_KIND,
    create_notification_for_message,
)
from cli_agent_orchestrator.linear.inbox_read_presentation import (
    inbox_read_presentation_metadata,
)
from cli_agent_orchestrator.linear.persistence import (
    get_thread,
    list_messages,
    upsert_message,
    upsert_thread,
    upsert_work_item,
)
from cli_agent_orchestrator.workspaces import (
    DEFAULT_WORKSPACE_ID,
    WorkspaceCollaborationManager,
    WorkspaceTeam,
    WorkspaceTeamRegistry,
    WorkspaceTeamRole,
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
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.inbox_authorization.default_workspace_collaboration_manager",
        _provider_inbox_collaboration_manager,
    )
    monkeypatch.setenv("CAO_AGENT_ID", "implementation_partner")
    yield


def _provider_inbox_collaboration_manager(
    cao_tools: tuple[str, ...] = ("read_inbox_message", "reply_to_inbox_message"),
) -> WorkspaceCollaborationManager:
    implementation = Agent(
        id="implementation_partner",
        display_name="Implementation Partner",
        cli_provider="codex",
        workdir="/repo",
        session_name="implementation-partner",
        prompt="",
        workspace=AgentWorkspaceConfig(team="cao_delivery"),
        linear=LinearConfig(app_key="implementation_partner", access_token="token"),
    )
    other = Agent(
        id="other_partner",
        display_name="Other Partner",
        cli_provider="codex",
        workdir="/repo",
        session_name="other-partner",
        prompt="",
        workspace=AgentWorkspaceConfig(team="other_team"),
        linear=LinearConfig(app_key="other_partner", access_token="token"),
    )
    return WorkspaceCollaborationManager(
        workspace_registry=default_workspace_registry(),
        agent_registry=AgentRegistry({agent.id: agent for agent in (implementation, other)}),
        provider_adapters={"linear": LinearWorkspaceAdapter()},
        team_registry=WorkspaceTeamRegistry(
            _TeamStore(
                (
                    WorkspaceTeam(
                        id="cao_delivery",
                        display_name="CAO Delivery",
                        workspace=DEFAULT_WORKSPACE_ID,
                        roles={
                            "member": WorkspaceTeamRole(
                                display_name="Member",
                                cao_tools=cao_tools,
                            )
                        },
                    ),
                    WorkspaceTeam(
                        id="other_team",
                        display_name="Other Team",
                        workspace=DEFAULT_WORKSPACE_ID,
                        roles={
                            "member": WorkspaceTeamRole(
                                display_name="Member",
                                cao_tools=("read_inbox_message", "reply_to_inbox_message"),
                            )
                        },
                    ),
                )
            )
        ),
    )


def _ensure_caller_agent_terminal(agent_id: str = "implementation_partner") -> None:
    create_terminal(
        "terminal-a",
        "session",
        "window",
        "codex",
        agent_id=agent_id,
        workspace_context_id=db_module.ensure_default_workspace_context(agent_id).id,
    )


def _provider_conversation_notification() -> int:
    _ensure_caller_agent_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="thread-1",
        external_url="https://presence.example/thread-1",
        kind="conversation",
        prompt_context="Full context from provider",
        metadata={"linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="message-1",
        direction="inbound",
        kind="prompt",
        body="Full provider body",
        raw_snapshot={"provider": {"body": "Full provider body", "extra": "metadata"}},
    )
    return create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id


def _provider_conversation_notification_with_large_raw_snapshot() -> int:
    _ensure_caller_agent_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="thread-raw",
        raw_snapshot={"large": "x" * 50_000, "_cao_linear_app_key": "implementation_partner"},
        metadata={"large": "y" * 50_000, "linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="message-raw",
        direction="inbound",
        kind="prompt",
        body="Small provider body",
        raw_snapshot={"large": "z" * 50_000},
        metadata={"actor": {"name": "Provider Author"}, "linear_app_key": "implementation_partner"},
    )
    return create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id


def _linear_provider_conversation_notification() -> int:
    _ensure_caller_agent_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="session-1",
        kind="conversation",
        raw_snapshot={"_cao_linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-1",
        direction="inbound",
        kind="prompt",
        body="Linear body",
    )
    return create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id


def _linear_provider_conversation_notification_with_work_item_and_metadata() -> int:
    _ensure_caller_agent_terminal()
    work_item = upsert_work_item(
        provider="linear",
        external_id="issue-uuid-1",
        identifier="CAO-34",
        title="Add workspace breadcrumb contribution path",
        raw_snapshot={"large": "issue-raw-" * 5000},
    )
    thread = upsert_thread(
        provider="linear",
        external_id="session-123",
        kind="conversation",
        work_item_id=work_item.id,
        metadata={"linear_app_key": "implementation_partner"},
        raw_snapshot={"large": "thread-raw-" * 5000},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-123",
        direction="inbound",
        kind="prompt",
        body="Please implement the breadcrumb.",
        metadata=inbox_read_presentation_metadata(
            workspace={
                "name": "Linear",
                "breadcrumb": {
                    "agent_session_id": "session-123",
                    "issue": "CAO-34",
                },
            },
            source_label="Implementation Partner",
        ),
        raw_snapshot={
            "actor": {"name": "Raw Snapshot Author Should Not Leak"},
            "large": "message-raw-" * 5000,
        },
    )
    return create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id


def _linear_provider_conversation_notification_with_prompt_context(prompt_context: str) -> int:
    _ensure_caller_agent_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="session-context",
        kind="conversation",
        prompt_context=prompt_context,
        metadata={"linear_app_key": "implementation_partner"},
        raw_snapshot={"data": {"promptContext": prompt_context, "token": "raw-secret"}},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-context",
        direction="inbound",
        kind="prompt",
        body="Please use the bounded context.",
        metadata=inbox_read_presentation_metadata(
            context={"linear_prompt_context": prompt_context[:3500]},
            source_label="Linear",
        ),
    )
    return create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id


@pytest.mark.asyncio
async def test_read_inbox_message_returns_terminal_backed_slim_payload_with_workspace_null(
    test_session,
):
    _ensure_caller_agent_terminal()
    create_terminal(
        "terminal-sender",
        "session",
        "window",
        "codex",
        agent_id="other_partner",
        workspace_context_id=db_module.ensure_default_workspace_context("other_partner").id,
    )
    delivery = create_inbox_delivery(
        "terminal-sender",
        "agent:implementation_partner",
        "I finished the patch. Can you review it?",
    )

    result = await read_inbox_message(delivery.notification.id)

    assert result == {
        "success": True,
        "notification_id": delivery.notification.id,
        "message_id": delivery.message.id,
        "from": "Other Partner",
        "body": "I finished the patch. Can you review it?",
        "replyable": False,
        "reply_error": "no provider reply route",
    }


def test_provider_backed_read_returns_slim_payload_without_raw_context(test_session):
    notification_id = _provider_conversation_notification()

    result = _read_inbox_message_impl(notification_id)

    assert result == {
        "success": True,
        "notification_id": notification_id,
        "message_id": result["message_id"],
        "from": "Linear",
        "body": "Full provider body",
        "replyable": True,
    }
    assert "id" not in result
    assert "provider_context" not in result
    assert "inbox_message" not in result
    assert "reply" not in result


def test_plain_agent_notification_read_returns_body_and_replyability(test_session, monkeypatch):
    # Given
    _ensure_caller_agent_terminal()
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.check_and_send_pending_messages",
        lambda _receiver_agent_id: False,
    )
    notification = send_inbox_message(
        "implementation_partner",
        "Plain body",
        source=PlainSource("other_partner"),
    )

    # When
    result = _read_inbox_message_impl(notification.id)

    # Then
    assert result == {
        "success": True,
        "notification_id": notification.id,
        "message_id": notification.id,
        "from": "Other Partner",
        "body": "Plain body",
        "replyable": True,
    }


def test_read_inbox_message_allows_agent_context_receiver(test_session):
    # Given
    _ensure_caller_agent_terminal()
    notification = create_inbox_notification_event(
        "agent:implementation_partner:context:ctx-1",
        "Context-scoped body",
        source_kind="plain",
        source_id="other_partner",
    )

    # When
    result = _read_inbox_message_impl(notification.id)

    # Then
    assert result == {
        "success": True,
        "notification_id": notification.id,
        "message_id": notification.id,
        "from": "Other Partner",
        "body": "Context-scoped body",
        "replyable": True,
    }


def test_provider_backed_read_is_not_replyable_when_reply_tool_is_hidden(test_session, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.inbox_authorization.default_workspace_collaboration_manager",
        lambda: _provider_inbox_collaboration_manager(("read_inbox_message",)),
    )
    notification_id = _provider_conversation_notification()

    result = _read_inbox_message_impl(notification_id)

    assert result["success"] is True
    assert result["replyable"] is False
    assert "reply_to_inbox_message" in result["reply_error"]


def test_linear_backed_read_returns_provider_owned_workspace_breadcrumb(test_session):
    notification_id = _linear_provider_conversation_notification_with_work_item_and_metadata()

    result = _read_inbox_message_impl(notification_id)

    assert result == {
        "success": True,
        "notification_id": notification_id,
        "message_id": result["message_id"],
        "from": "Implementation Partner",
        "body": "Please implement the breadcrumb.",
        "replyable": True,
        "breadcrumb": {
            "workspace": "Linear",
            "agent_session_id": "session-123",
            "issue": "CAO-34",
        },
    }


def test_read_inbox_message_rejects_non_receiver_terminal(test_session, monkeypatch):
    notification_id = _linear_provider_conversation_notification()
    create_terminal(
        "terminal-other",
        "session",
        "window",
        "codex",
        agent_id="other_partner",
        workspace_context_id=db_module.ensure_default_workspace_context("other_partner").id,
    )
    monkeypatch.setenv("CAO_AGENT_ID", "other_partner")

    result = _read_inbox_message_impl(notification_id)

    assert result["success"] is False
    assert result["error_type"] == "InboxReadError"
    assert "not authorized" in result["error"]


def test_linear_backed_read_does_not_expose_prompt_context(test_session):
    # Shape sources:
    # https://linear.app/developers/agent-interaction/
    # https://linear.app/developers/agents
    # https://hexdocs.pm/linear_sdk/LinearSDK.Objects.AgentSessionEventWebhookPayload.html
    prompt_context = "<issue>Current scope</issue>\n" + ("prior comment " * 800)
    notification_id = _linear_provider_conversation_notification_with_prompt_context(prompt_context)

    result = _read_inbox_message_impl(notification_id)
    encoded = json.dumps(result)

    assert result["success"] is True
    assert result["body"] == "Please use the bounded context."
    assert "context" not in result
    assert "token" not in encoded
    assert "raw-secret" not in encoded
    assert "prior comment " * 500 not in encoded


def test_linear_backed_read_never_uses_prompt_context_as_message_body(test_session):
    _ensure_caller_agent_terminal()
    prompt_context = "<issue>Should stay out of message reads</issue>"
    thread = upsert_thread(
        provider="linear",
        external_id="session-empty-body",
        kind="conversation",
        prompt_context=prompt_context,
        metadata={"linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-empty-body",
        direction="inbound",
        kind="prompt",
        body=None,
        metadata=inbox_read_presentation_metadata(source_label="Linear"),
    )
    notification_id = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id

    result = _read_inbox_message_impl(notification_id)
    encoded = json.dumps(result)

    assert result["body"] == "(no text body)"
    assert prompt_context not in encoded


def test_provider_backed_read_body_is_backing_message_not_notification_wrapper(test_session):
    notification_id = _provider_conversation_notification()

    result = _read_inbox_message_impl(notification_id)

    assert result["body"] == "Full provider body"
    assert "[CAO inbox notification]" not in result["body"]
    assert "read_inbox_message" not in result["body"]


def test_provider_backed_read_missing_backing_message_fails_clearly(test_session):
    notification_id = _provider_conversation_notification()

    with db_module.SessionLocal() as session:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        session.query(db_module.ProviderConversationMessageModel).delete()
        session.commit()

    result = _read_inbox_message_impl(notification_id)

    assert result["success"] is False
    assert result["error_type"] == "InboxReadNotFoundError"
    assert "provider conversation message" in result["error"]
    assert "not found" in result["error"]


def test_provider_backed_read_missing_backing_thread_fails_clearly(test_session):
    notification_id = _provider_conversation_notification()

    with db_module.SessionLocal() as session:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        session.query(db_module.ProviderConversationThreadModel).delete()
        session.commit()

    result = _read_inbox_message_impl(notification_id)

    assert result["success"] is False
    assert result["error_type"] == "InboxReadNotFoundError"
    assert "provider conversation thread" in result["error"]
    assert "not found" in result["error"]


def test_read_inbox_message_uses_bounded_sender_fallback_without_internal_ids(test_session):
    _ensure_caller_agent_terminal()
    delivery = create_inbox_delivery(
        "missing-terminal-id",
        "agent:implementation_partner",
        "Plain terminal message",
    )

    result = _read_inbox_message_impl(delivery.notification.id)

    assert result["from"] == "Terminal sender"
    assert "missing-terminal-id" not in json.dumps(result)


def test_large_raw_snapshots_do_not_inflate_default_read_response(test_session):
    notification_id = _provider_conversation_notification_with_large_raw_snapshot()

    result = _read_inbox_message_impl(notification_id)
    encoded = json.dumps(result)

    assert result["body"] == "Small provider body"
    assert result["from"] == "Linear"
    assert len(encoded) < 500
    assert "z" * 1000 not in encoded


def test_large_linear_raw_snapshots_do_not_leak_through_breadcrumb_or_sender_label(test_session):
    notification_id = _linear_provider_conversation_notification_with_work_item_and_metadata()

    result = _read_inbox_message_impl(notification_id)
    encoded = json.dumps(result)

    assert result["from"] == "Implementation Partner"
    assert result["breadcrumb"] == {
        "workspace": "Linear",
        "agent_session_id": "session-123",
        "issue": "CAO-34",
    }
    assert "Raw Snapshot Author Should Not Leak" not in encoded
    assert "message-raw-message-raw" not in encoded
    assert len(encoded) < 500


def test_invalid_provider_authored_workspace_metadata_is_omitted_from_slim_read(test_session):
    _ensure_caller_agent_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="thread-invalid-workspace",
        metadata={"linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="message-invalid-workspace",
        direction="inbound",
        kind="prompt",
        body="Full provider body",
        metadata=inbox_read_presentation_metadata(
            workspace={"name": "Example", "breadcrumb": ["not", "a", "mapping"]}
        ),
    )
    notification_id = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id

    result = _read_inbox_message_impl(notification_id)

    assert result["success"] is True
    assert "breadcrumb" not in result
    assert result["body"] == "Full provider body"


def test_oversized_provider_authored_workspace_metadata_is_omitted_from_slim_read(test_session):
    _ensure_caller_agent_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="thread-oversized-workspace",
        metadata={"linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="message-oversized-workspace",
        direction="inbound",
        kind="prompt",
        body="Full provider body",
        metadata=inbox_read_presentation_metadata(
            workspace={
                "name": "Example",
                "breadcrumb": {"thread_id": "thread-oversized-workspace", "snapshot": "x" * 2000},
            }
        ),
    )
    notification_id = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id

    result = _read_inbox_message_impl(notification_id)
    encoded = json.dumps(result)

    assert result["success"] is True
    assert "breadcrumb" not in result
    assert "x" * 1000 not in encoded


def test_provider_backed_read_uses_notification_source_message_id(test_session):
    _ensure_caller_agent_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="thread-with-reply",
        external_url="https://presence.example/thread-with-reply",
        kind="conversation",
        raw_snapshot={"_cao_linear_app_key": "implementation_partner"},
    )
    inbound_message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="message-inbound",
        direction="inbound",
        kind="prompt",
        body="Original provider prompt",
    )
    upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="message-outbound",
        direction="outbound",
        kind="response",
        body="Previous CAO reply",
    )
    delivery = create_notification_for_message(
        provider_message_id=inbound_message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    )

    result = _read_inbox_message_impl(delivery.delivery.notification.id)

    assert result["success"] is True
    assert result["body"] == "Original provider prompt"
    assert result["replyable"] is True


def test_reply_to_inbox_message_routes_through_linear_provider(test_session, monkeypatch):
    # Given
    notification_id = _linear_provider_conversation_notification()
    create_activity = Mock(return_value={"id": "reply-1"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        create_activity,
    )

    # When
    result = _reply_to_inbox_message_impl(notification_id, "Reply through CAO")

    # Then
    assert result["success"] is True
    assert result["provider"] == "linear"
    assert result["thread_id"] == "session-1"
    assert result["outbound_message"]["external_id"] == "reply-1"
    create_activity.assert_called_once_with(
        "session-1",
        {"type": "response", "body": "Reply through CAO"},
        app_key="implementation_partner",
    )
    thread = get_thread("linear", "session-1")
    assert thread is not None
    messages = list_messages(thread.id)
    assert messages[-1].direction == "outbound"
    assert messages[-1].body == "Reply through CAO"


def test_reply_to_terminal_addressed_provider_notification_routes_through_inbox_reply(
    test_session,
    monkeypatch,
):
    # Given
    _ensure_caller_agent_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="terminal-addressed-session",
        kind="conversation",
        metadata={"linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="terminal-addressed-activity",
        direction="inbound",
        kind="prompt",
        body="Reply to the terminal-addressed notification.",
    )
    notification_id = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="terminal-a",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id
    create_activity = Mock(return_value={"id": "reply-terminal-addressed"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        create_activity,
    )

    # When
    result = _reply_to_inbox_message_impl(notification_id, "Reply through terminal ownership")

    # Then
    assert result["success"] is True
    create_activity.assert_called_once_with(
        "terminal-addressed-session",
        {"type": "response", "body": "Reply through terminal ownership"},
        app_key="implementation_partner",
    )


def test_reply_to_inbox_message_returns_normal_error_payload_for_empty_body(test_session):
    # Given
    notification_id = _linear_provider_conversation_notification()

    # When
    result = _reply_to_inbox_message_impl(notification_id, " ")

    # Then
    assert result["success"] is False
    assert result["error_type"] == "InboxReplyError"
    assert result["error"] == "body is required"


def test_reply_to_plain_inbox_message_loops_back_to_sender_terminal(
    test_session,
    monkeypatch,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    # Given
    _ensure_caller_agent_terminal()
    create_terminal(
        "terminal-other",
        "session",
        "window-other",
        "codex",
        agent_id="other_partner",
        workspace_context_id=db_module.ensure_default_workspace_context("other_partner").id,
    )
    notification = create_inbox_notification_event(
        "agent:implementation_partner",
        "Plain body from agent A",
        source_kind="plain",
        source_id="other_partner",
    )
    from cli_agent_orchestrator.inbox import readiness

    terminal_provider_patcher(readiness.provider_manager, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(readiness.terminal_service)

    # When
    result = _reply_to_inbox_message_impl(notification.id, "Plain reply body")

    # Then
    assert result["success"] is True
    assert result["notification_id"] == notification.id
    send_input.assert_called_once()
    assert send_input.call_args.args[0] == "terminal-other"
    assert "Plain reply body" in send_input.call_args.args[1]


def test_reply_to_inbox_message_ignores_agent_visible_breadcrumb_for_routing(
    test_session,
    monkeypatch,
):
    _ensure_caller_agent_terminal()
    work_item = upsert_work_item(
        provider="linear",
        external_id="work-breadcrumb",
        identifier="CAO-39",
        title="Breadcrumb is presentation only",
    )
    thread = upsert_thread(
        provider="linear",
        external_id="thread-route",
        external_url="https://linear.app/agent-session/thread-route",
        work_item_id=work_item.id,
        kind="conversation",
        metadata={"linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="message-route",
        direction="inbound",
        kind="prompt",
        body="Reply using hidden route data.",
        metadata=inbox_read_presentation_metadata(
            workspace={
                "name": "Example",
                "breadcrumb": {
                    "thread_id": "misleading-agent-visible-thread",
                    "issue": "CAO-39",
                },
            },
            source_label="Example Workspace",
        ),
    )
    notification_id = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    ).delivery.notification.id
    create_activity = Mock(return_value={"id": "reply-1"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        create_activity,
    )

    result = _reply_to_inbox_message_impl(notification_id, "Routed reply")

    assert result["success"] is True
    assert create_activity.call_args.args[0] == "thread-route"
    assert "misleading-agent-visible-thread" not in json.dumps(create_activity.call_args.kwargs)


def test_reply_to_inbox_message_uses_linear_provider_directly(
    test_session,
    monkeypatch,
):
    notification_id = _linear_provider_conversation_notification()
    create_activity = Mock(return_value={"id": "reply-1"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        create_activity,
    )

    read_result = _read_inbox_message_impl(notification_id)
    result = _reply_to_inbox_message_impl(notification_id, "Reply through default Linear provider")

    assert "implementation_partner" not in json.dumps(read_result)
    assert "provider_context" not in read_result
    assert result["success"] is True
    create_activity.assert_called_once_with(
        "session-1",
        {"type": "response", "body": "Reply through default Linear provider"},
        app_key="implementation_partner",
    )


def test_reply_to_inbox_message_uses_selected_message_identity_context(
    test_session,
    monkeypatch,
):
    _ensure_caller_agent_terminal()
    thread = upsert_thread(
        provider="linear",
        external_id="message-owned-session",
        kind="conversation",
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="message-owned-activity",
        direction="inbound",
        kind="prompt",
        body="Reply using the selected message identity.",
        metadata={"linear_app_key": "implementation_partner"},
    )
    delivery = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id="agent:implementation_partner",
        authorized_agent_id="implementation_partner",
    )
    notification_id = delivery.delivery.notification.id
    create_activity = Mock(return_value={"id": "reply-1"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        create_activity,
    )

    assert "reply_to_inbox_message" in delivery.delivery.notification.body
    read_result = _read_inbox_message_impl(notification_id)
    result = _reply_to_inbox_message_impl(notification_id, "Reply through selected message")

    assert read_result["replyable"] is True
    assert result["success"] is True
    create_activity.assert_called_once_with(
        "message-owned-session",
        {"type": "response", "body": "Reply through selected message"},
        app_key="implementation_partner",
    )


def test_reply_to_inbox_message_rejects_non_receiver_terminal(test_session, monkeypatch):
    notification_id = _linear_provider_conversation_notification()
    create_terminal(
        "terminal-other",
        "session",
        "window",
        "codex",
        agent_id="other_partner",
        workspace_context_id=db_module.ensure_default_workspace_context("other_partner").id,
    )
    monkeypatch.setenv("CAO_AGENT_ID", "other_partner")

    result = _reply_to_inbox_message_impl(notification_id, "Should not route")

    assert result["success"] is False
    assert result["error_type"] == "InboxReadError"
    assert "not authorized" in result["error"]


def test_read_and_reply_fail_clearly_for_non_replyable_inbox_message(test_session):
    _ensure_caller_agent_terminal()
    delivery = create_inbox_delivery(
        "terminal-sender",
        "agent:implementation_partner",
        "Plain terminal message",
    )

    read_result = _read_inbox_message_impl(delivery.notification.id)
    reply_result = _reply_to_inbox_message_impl(delivery.notification.id, "No provider target")

    assert read_result == {
        "success": True,
        "notification_id": delivery.notification.id,
        "message_id": delivery.message.id,
        "from": "Terminal sender",
        "body": "Plain terminal message",
        "replyable": False,
        "reply_error": "no provider reply route",
    }
    assert reply_result["success"] is False
    assert reply_result["error_type"] == "NotReplyable"


def test_read_inbox_message_distinguishes_notification_without_backing_message(test_session):
    _ensure_caller_agent_terminal()
    notification = create_inbox_notification_event(
        "agent:implementation_partner",
        "CAO-123 has new comments.",
        source_kind="linear_issue",
        source_id="CAO-123",
    )

    result = _read_inbox_message_impl(notification.id)

    assert result == {
        "success": True,
        "notification_id": notification.id,
        "message_id": notification.id,
        "from": "Linear Issue",
        "body": "CAO-123 has new comments.",
        "replyable": False,
        "reply_error": "no provider reply route",
    }


def test_agent_runtime_backed_message_is_slim_and_not_replyable(test_session):
    _ensure_caller_agent_terminal()
    delivery = create_inbox_delivery(
        "linear-runtime",
        "agent:implementation_partner",
        "Agent runtime accepted a Linear event.",
        source_kind="linear_event",
        source_id="event-1",
    )

    read_result = _read_inbox_message_impl(delivery.notification.id)
    reply_result = _reply_to_inbox_message_impl(delivery.notification.id, "Reply to runtime event")

    assert read_result == {
        "success": True,
        "notification_id": delivery.notification.id,
        "message_id": delivery.message.id,
        "from": "Linear Event",
        "body": "Agent runtime accepted a Linear event.",
        "replyable": False,
        "reply_error": "no provider reply route",
    }
    assert reply_result["success"] is False
    assert reply_result["error_type"] == "NotReplyable"
    assert len(reply_result["error"]) < 180


def test_reply_to_inbox_message_surfaces_provider_failure(test_session):
    notification_id = _provider_conversation_notification()

    result = _reply_to_inbox_message_impl(notification_id, "No registered provider")

    assert result["success"] is False
    assert result["error_type"] == "ProviderConversationReplyDeliveryError"
    assert result["failed_message_state"] == "failed"


def test_provider_reply_failure_response_and_record_do_not_leak_provider_context(
    test_session,
    monkeypatch,
):
    notification_id = _linear_provider_conversation_notification()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        Mock(
            side_effect=RuntimeError(
                "Linear API failed access_token=secret-token "
                'password="correct horse battery staple" '
                "Authorization: Bearer bearer-secret "
                f"payload={'x' * 5000}\n"
                '  File "/tmp/provider.py", line 1, in reply\n'
                "stack locals include refresh_token=refresh-secret"
            )
        ),
    )

    result = _reply_to_inbox_message_impl(notification_id, "Reply that fails")

    thread = get_thread("linear", "session-1")
    assert thread is not None
    failed_message = list_messages(thread.id)[-1]
    encoded_response = json.dumps(result)
    encoded_failed_metadata = json.dumps(failed_message.metadata)

    assert result["success"] is False
    assert result["error_type"] == "ProviderConversationReplyDeliveryError"
    assert result["failed_message_state"] == "failed"
    assert "secret-token" not in encoded_response
    assert "correct horse battery staple" not in encoded_response
    assert "bearer-secret" not in encoded_response
    assert "refresh-secret" not in encoded_response
    assert "/tmp/provider.py" not in encoded_response
    assert "x" * 1000 not in encoded_response
    assert "secret-token" not in encoded_failed_metadata
    assert "correct horse battery staple" not in encoded_failed_metadata
    assert "bearer-secret" not in encoded_failed_metadata
    assert "refresh-secret" not in encoded_failed_metadata
    assert "/tmp/provider.py" not in encoded_failed_metadata
    assert len(result["error"]) < 360
    assert failed_message.metadata["error"].endswith("...")

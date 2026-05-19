"""Tests for Linear app OAuth and webhook API routes."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator import constants
from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig, LinearConfig
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.events import CaoEventDispatcher
from cli_agent_orchestrator.linear.app_client import LinearWebhookVerification
from cli_agent_orchestrator.linear.workspace_events import (
    LinearIssueContextEvent,
    publish_linear_provider_event,
    register_linear_cao_events,
)
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearPresence,
    LinearResolvedPresence,
    LinearWorkspaceProvider,
    LinearWorkspaceProviderConfigError,
)
from cli_agent_orchestrator.provider_conversations.inbox_bridge import (
    PROVIDER_CONVERSATION_INBOX_SOURCE_KIND,
)
from cli_agent_orchestrator.provider_conversations.persistence import (
    get_processed_event,
    get_thread,
    list_messages,
)
from cli_agent_orchestrator.provider_conversations.reply_service import (
    ProviderConversationReplyDeliveryError,
    reply_to_inbox_message,
)
from cli_agent_orchestrator.runtime.agent import (
    AgentRuntimeDeliveryResult,
    AgentRuntimeNotifyResult,
    AgentRuntimeStatus,
)
from cli_agent_orchestrator.services.tool_service import ToolAccessDecision


def _test_session(monkeypatch: pytest.MonkeyPatch) -> None:
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
    tool_service = _ProviderConversationToolService()
    monkeypatch.setattr(
        "cli_agent_orchestrator.provider_conversations.inbox_bridge.default_tool_service",
        lambda: tool_service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.provider_conversations.inbox_authorization.default_tool_service",
        lambda: tool_service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.default_tool_service",
        lambda: tool_service,
    )


class _ProviderConversationToolService:
    def provider_conversation_decision(self, *args, **kwargs) -> ToolAccessDecision:
        return ToolAccessDecision.allow(reason="provider_conversation_allowed")

    def provider_conversation_decision_for_inbox(self, *args, **kwargs) -> ToolAccessDecision:
        return ToolAccessDecision.allow(reason="provider_conversation_allowed")


def _attach_reply_terminal() -> str:
    terminal_id = "terminal-a"
    db_module.create_terminal(
        terminal_id,
        "session",
        "window",
        "codex",
        agent_id="implementation_partner",
        workspace_context_id=db_module.ensure_default_workspace_context(
            "implementation_partner"
        ).id,
    )
    return terminal_id


def _test_file_session(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / "linear-route.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(constants, "DATABASE_FILE", db_path)
    tool_service = _ProviderConversationToolService()
    monkeypatch.setattr(
        "cli_agent_orchestrator.provider_conversations.inbox_bridge.default_tool_service",
        lambda: tool_service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.provider_conversations.inbox_authorization.default_tool_service",
        lambda: tool_service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.default_tool_service",
        lambda: tool_service,
    )
    return engine


def _break_notification_marker_fks(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("DROP TABLE provider_conversation_inbox_notifications")
        connection.exec_driver_sql("DROP TABLE agent_runtime_notifications")
        connection.exec_driver_sql("""
            CREATE TABLE provider_conversation_inbox_notifications (
                id INTEGER NOT NULL,
                receiver_id VARCHAR NOT NULL,
                provider_message_id INTEGER NOT NULL,
                inbox_notification_id INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (receiver_id, provider_message_id),
                FOREIGN KEY(provider_message_id)
                    REFERENCES provider_conversation_messages (id) ON DELETE CASCADE,
                FOREIGN KEY(inbox_notification_id)
                    REFERENCES "inbox_notifications_old" (id) ON DELETE CASCADE
            )
        """)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("""
            CREATE TABLE agent_runtime_notifications (
                id INTEGER NOT NULL,
                agent_id VARCHAR NOT NULL,
                source_kind VARCHAR NOT NULL,
                source_id VARCHAR NOT NULL,
                inbox_notification_id INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (agent_id, source_kind, source_id),
                FOREIGN KEY(inbox_notification_id)
                    REFERENCES "inbox_notifications_old" (id) ON DELETE CASCADE
            )
        """)


def _notification_fk_targets(connection, table_name: str) -> list[str]:
    return [
        row[2]
        for row in connection.exec_driver_sql(f"PRAGMA foreign_key_list({table_name})")
        if row[3] == "inbox_notification_id"
    ]


def _pending_linear_notifications():
    return db_module.list_pending_inbox_notifications("agent:implementation_partner", limit=10)


def _linear_agent_payload(
    *,
    session_id: str = "session-1",
    activity_id: str = "activity-1",
    body: str = "Hello from Linear",
    extra_content: dict | None = None,
) -> dict:
    content = {"type": "prompt", "body": body}
    if extra_content is not None:
        content.update(extra_content)
    return {
        "action": "created",
        "data": {
            "agentSession": {
                "id": session_id,
                "url": f"https://linear.app/session/{session_id}",
                "issue": {
                    "id": f"issue-{session_id}",
                    "identifier": "CAO-23",
                    "title": "Wire Linear provider events into inbox bridge",
                },
            },
            "agentActivity": {
                "id": activity_id,
                "content": content,
            },
        },
    }


def _linear_context_only_payload(
    *,
    session_id: str = "session-context-only",
    context: str = '<issue identifier="CAO-29"><title>Route context</title></issue>',
) -> dict:
    return {
        "action": "created",
        "data": {
            "promptContext": context,
            "agentSession": {
                "id": session_id,
                "url": f"https://linear.app/session/{session_id}",
                "issue": {
                    "id": f"issue-{session_id}",
                    "identifier": "CAO-29",
                    "title": "Route Linear notifications to mapped CAO agents",
                },
            },
        },
    }


def _linear_headers(delivery_id: str = "delivery-1") -> dict:
    return {
        "Linear-Signature": "signature",
        "Linear-Delivery": delivery_id,
        "Linear-Event": "AgentSessionEvent",
    }


def _verified_linear_app() -> LinearWebhookVerification:
    return LinearWebhookVerification(True, app_key="implementation_partner")


class _FakeRuntimeHandle:
    def __init__(
        self,
        receiver_id: str = "agent:implementation_partner",
        *,
        terminal_id: str | None = "terminal-inbox",
        status: AgentRuntimeStatus = AgentRuntimeStatus.BUSY,
        error: str | None = None,
    ) -> None:
        self.inbox_receiver_id = receiver_id
        self.terminal_id = terminal_id
        self.status = status
        self.error = error
        self.accepted = []

    def accept_notification(self, notification, *, causing_event=None):
        self.accepted.append(notification)
        return AgentRuntimeNotifyResult(
            notification=notification,
            status=self.status,
            terminal_id=self.terminal_id,
            started=False,
            delivery=AgentRuntimeDeliveryResult(
                status=self.status,
                terminal_id=self.terminal_id,
                attempted=False,
                delivered=False,
            ),
            error=self.error,
        )


def _resolved_presence() -> LinearResolvedPresence:
    return LinearResolvedPresence(
        presence=LinearPresence(
            presence_id="implementation_partner",
            agent_id="implementation_partner",
            app_key="implementation_partner",
            app_user_name="Implementation Partner",
        ),
        agent=Agent(
            id="implementation_partner",
            display_name="Implementation Partner",
            cli_provider="codex",
            workdir="/repo",
            session_name="implementation-partner",
            prompt="Implement the requested CAO task.",
            workspace=AgentWorkspaceConfig(team="cao_delivery"),
        ),
    )


def _resolved_discovery_presence() -> LinearResolvedPresence:
    return LinearResolvedPresence(
        presence=LinearPresence(
            presence_id="discovery_partner",
            agent_id="discovery_partner",
            app_key="discovery_partner",
            app_user_name="Discovery Partner",
            access_token="linear-token",
        ),
        agent=Agent(
            id="discovery_partner",
            display_name="Discovery Partner",
            cli_provider="codex",
            workdir="/repo",
            session_name="discovery-partner",
            prompt="Discover the requested CAO context.",
            workspace=AgentWorkspaceConfig(team="cao_delivery"),
        ),
    )


def _install_linear_provider_for_agent(
    monkeypatch: pytest.MonkeyPatch,
    agent: Agent,
) -> LinearWorkspaceProvider:
    provider = LinearWorkspaceProvider(
        agent_registry=AgentRegistry({agent.id: agent}),
        preflight_credentials=False,
    )
    provider.initialize()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider._default_linear_workspace_provider",
        provider,
    )
    return provider


def _use_mapped_linear_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    terminal_id: str | None = "terminal-inbox",
    status: AgentRuntimeStatus = AgentRuntimeStatus.BUSY,
    error: str | None = None,
) -> _FakeRuntimeHandle:
    handle = _FakeRuntimeHandle(terminal_id=terminal_id, status=status, error=error)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._resolve_linear_event",
        lambda event: _resolved_presence(),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.should_enable_linear_agent_policies",
        lambda: False,
    )
    handle.update_external_url = Mock()
    handle.create_activity = Mock(return_value={"id": "activity-lifecycle"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.app_client.update_agent_session_external_url",
        handle.update_external_url,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.app_client.public_cao_runtime_url",
        lambda terminal_id, *, agent_id=None: (
            f"https://cao.test/agents/{agent_id}"
            if agent_id
            else f"https://cao.test/terminals/{terminal_id}"
        ),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.app_client.create_agent_activity",
        handle.create_activity,
    )
    return handle


def _delegated_discovery_payload() -> dict:
    return {
        "action": "created",
        "data": {
            "agentSession": {
                "id": "session-discovery-denied",
                "url": "https://linear.app/session/session-discovery-denied",
                "creator": {"id": "user-1", "name": "RJ Wilson"},
                "sourceMetadata": None,
                "comment": {
                    "id": "comment-delegated",
                    "body": "RJ Wilson delegated this issue to Discovery Partner.",
                },
                "issue": {
                    "id": "issue-implementation",
                    "identifier": "CAO-69",
                    "title": "Implement bounded work",
                    "delegate": {"id": "app-user-1", "name": "Discovery Partner"},
                },
            },
        },
    }


@pytest.fixture(autouse=True)
def _legacy_linear_route_compatibility(tmp_path, monkeypatch):
    config_path = tmp_path / "workspace-providers.toml"
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_providers.registry.WORKSPACE_PROVIDERS_CONFIG_PATH",
        config_path,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.should_enable_linear_routes",
        lambda: True,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.app_client.public_cao_runtime_url",
        lambda terminal_id, *, agent_id=None: (
            f"https://cao.test/agents/{agent_id}"
            if agent_id
            else f"https://cao.test/terminals/{terminal_id}"
        ),
    )


def test_linear_oauth_callback_requires_code(client):
    response = client.get("/linear/oauth/callback")

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing Linear OAuth code"


def test_linear_oauth_callback_returns_install_agent(client, monkeypatch):
    install = Mock(
        return_value={
            "viewer": {"id": "app-user-1", "name": "Discovery Partner"},
            "token_type": "Bearer",
            "expires_in": 3600,
            "state_verified": True,
        }
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.install_linear_app", install
    )

    response = client.get("/linear/oauth/callback?code=code-123&state=state-123")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "app_key": None,
        "viewer_id": "app-user-1",
        "viewer_name": "Discovery Partner",
        "token_type": "Bearer",
        "expires_in": 3600,
        "state_verified": True,
    }
    install.assert_called_once_with("code-123", "state-123")


def test_linear_oauth_callback_surfaces_linear_error(client):
    response = client.get("/linear/oauth/callback?error=access_denied&error_description=Nope")

    assert response.status_code == 400
    assert response.json()["detail"] == "Nope"


def test_linear_routes_require_agent_owned_linear_config(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.should_enable_linear_routes",
        lambda: False,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Linear workspace provider is not enabled"


def test_linear_routes_require_agent_owned_provider_config(client, tmp_path, monkeypatch):
    config_path = tmp_path / "missing-workspace-providers.toml"
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_providers.registry.WORKSPACE_PROVIDERS_CONFIG_PATH",
        config_path,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.should_enable_linear_routes",
        lambda: False,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Linear workspace provider is not enabled"


def test_linear_agent_webhook_accepts_event(client, monkeypatch):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.parse_webhook_payload",
        lambda raw: {
            "action": "created",
            "data": {
                "agentSession": {"id": "session-1"},
                "agentActivity": {"id": "activity-1", "body": "Hello"},
            },
        },
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json={"action": "created"},
        headers={
            "Linear-Signature": "signature",
            "Linear-Delivery": "delivery-1",
            "Linear-Event": "AgentSessionEvent",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "verified": True,
        "event": "AgentSessionEvent",
        "action": "created",
        "delivery": "delivery-1",
        "app_key": "implementation_partner",
        "agent_session_id": "session-1",
        "routed": True,
    }
    assert len(handle.accepted) == 1
    assert get_processed_event("linear", "delivery-1").event_type == (
        "agent_session_lifecycle_activity"
    )


def test_linear_agent_webhook_publishes_exactly_one_cao_event(client, monkeypatch):
    _test_session(monkeypatch)
    _use_mapped_linear_runtime(monkeypatch)
    dispatcher = CaoEventDispatcher()
    register_linear_cao_events(dispatcher)
    published = []
    dispatcher.subscribe_all(
        handler=lambda event: published.append(event),
        subscription_id="test-linear-route",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.parse_webhook_payload",
        lambda raw: {
            "action": "created",
            "data": {
                "agentSession": {"id": "session-1"},
                "agentActivity": {"id": "activity-1", "body": "Hello"},
            },
        },
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(
            True,
            app_key="implementation_partner",
            agent_id="implementation_partner",
        ),
    )

    def publish_once(payload, *, delivery_id=None, header_event=None):
        return publish_linear_provider_event(
            payload,
            delivery_id=delivery_id,
            header_event=header_event,
            dispatcher=dispatcher,
        )

    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.publish_linear_provider_event",
        publish_once,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json={"action": "created"},
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert len(published) == 1
    assert isinstance(published[0], LinearIssueContextEvent)


def test_linear_agent_webhook_routes_verified_app_key_to_runtime(client, monkeypatch):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.parse_webhook_payload",
        lambda raw: {
            "action": "created",
            "data": {
                "agentSession": {"id": "session-1"},
                "agentActivity": {"id": "activity-1", "body": "Hello"},
            },
        },
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(
            True,
            app_key="implementation_partner",
        ),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json={"action": "created"},
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert response.json()["app_key"] == "implementation_partner"
    assert len(handle.accepted) == 1
    assert (
        _pending_linear_notifications()[0].message.source_kind
        == PROVIDER_CONVERSATION_INBOX_SOURCE_KIND
    )


def test_linear_agent_webhook_duplicate_delivery_does_not_duplicate_mapped_runtime_notification(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.parse_webhook_payload",
        lambda raw: {
            "action": "created",
            "data": {
                "agentSession": {"id": "session-1"},
                "agentActivity": {"id": "activity-1", "body": "Hello"},
            },
        },
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    headers = {
        "Linear-Signature": "signature",
        "Linear-Delivery": "delivery-1",
        "Linear-Event": "AgentSessionEvent",
    }
    first = client.post("/linear/webhooks/agent", json={"action": "created"}, headers=headers)
    second = client.post("/linear/webhooks/agent", json={"action": "created"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["routed"] is True
    assert second.json()["routed"] is True
    assert len(handle.accepted) == 1
    assert len(_pending_linear_notifications()) == 1


def test_linear_agent_webhook_unknown_mapping_is_not_routed(client, monkeypatch):
    _test_session(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True, app_key="unknown"),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._resolve_linear_event",
        Mock(side_effect=LinearWorkspaceProviderConfigError("Unknown Linear app key: unknown")),
    )
    handle_factory = Mock()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._runtime_handle_for_resolved_presence",
        handle_factory,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert response.json()["routed"] is False
    assert get_thread("linear", "session-1") is None
    assert _pending_linear_notifications() == []
    handle_factory.assert_not_called()


def test_linear_agent_webhook_no_team_agent_is_not_persisted_before_authorization(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    agent = Agent(
        id="implementation_partner",
        display_name="Implementation Partner",
        cli_provider="codex",
        workdir="/repo",
        session_name="implementation-partner",
        prompt="Implement the requested CAO task.",
        linear=LinearConfig(app_key="implementation_partner"),
        workspace=AgentWorkspaceConfig(),
    )
    _install_linear_provider_for_agent(monkeypatch, agent)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )
    handle_factory = Mock()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._runtime_handle_for_resolved_presence",
        handle_factory,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers("delivery-no-team"),
    )

    assert response.status_code == 200
    assert response.json()["routed"] is False
    assert get_processed_event("linear", "delivery-no-team") is None
    assert get_thread("linear", "session-1") is None
    assert _pending_linear_notifications() == []
    handle_factory.assert_not_called()


def test_linear_agent_webhook_unverified_no_source_is_not_routed(client, monkeypatch):
    _test_session(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(False),
    )
    handle_factory = Mock()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._runtime_handle_for_resolved_presence",
        handle_factory,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert response.json()["verified"] is False
    assert response.json()["routed"] is False
    assert get_thread("linear", "session-1") is None
    assert _pending_linear_notifications() == []
    handle_factory.assert_not_called()


def test_linear_agent_webhook_rejects_bad_payload(client, monkeypatch):
    from cli_agent_orchestrator.linear.app_client import LinearWebhookVerificationError

    def raise_bad_payload(raw):
        raise LinearWebhookVerificationError("bad webhook")

    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.parse_webhook_payload",
        raise_bad_payload,
    )

    response = client.post("/linear/webhooks/agent", json={"action": "created"})

    assert response.status_code == 401
    assert response.json()["detail"] == "bad webhook"


def test_linear_agent_webhook_rejects_failed_signature_verification(client, monkeypatch):
    from cli_agent_orchestrator.linear.app_client import LinearWebhookVerificationError

    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        Mock(side_effect=LinearWebhookVerificationError("Invalid Linear webhook signature")),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Linear webhook signature"


def test_linear_agent_webhook_creates_provider_conversation_records_and_inbox_notification(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(body="Please wire this into the inbox."),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert response.json()["routed"] is True
    assert len(handle.accepted) == 1
    thread = get_thread("linear", "session-1")
    assert thread is not None
    messages = _pending_linear_notifications()
    assert len(messages) == 1
    assert messages[0].message.sender_id == "provider_conversation"
    assert messages[0].message.source_kind == PROVIDER_CONVERSATION_INBOX_SOURCE_KIND
    assert messages[0].message.source_id == str(thread.id)
    assert messages[0].message.route_id == str(thread.id)
    assert "Please wire this into the inbox." in messages[0].message.body
    assert get_processed_event("linear", "delivery-1").event_type == "agent_session_prompted"


def test_linear_agent_webhook_routes_session_comment_body_without_prompt_context(
    client,
    monkeypatch,
):
    prompt_context = '<issue identifier="CAO-43"><title>Do not deliver this</title></issue>'
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json={
            "action": "created",
            "data": {
                "promptContext": prompt_context,
                "agentSession": {
                    "id": "session-43",
                    "creator": {"name": "RJ Wilson"},
                    "comment": {
                        "id": "comment-43",
                        "body": "@discoverypartner testing",
                    },
                    "issue": {
                        "id": "issue-43",
                        "identifier": "CAO-43",
                        "title": "Durable agent",
                    },
                },
            },
        },
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert response.json()["routed"] is True
    assert len(handle.accepted) == 1
    delivery = _pending_linear_notifications()[0]
    assert delivery.message.body == "testing"
    encoded = str(delivery.message.body) + str(delivery.notification.body)
    assert "Do not deliver this" not in encoded
    assert prompt_context not in encoded


def test_linear_agent_webhook_delivers_after_migration_repairs_marker_fk_targets(
    client,
    tmp_path,
    monkeypatch,
):
    engine = _test_file_session(monkeypatch, tmp_path)
    _break_notification_marker_fks(engine)
    db_module._migrate_ensure_provider_conversation_tables()
    db_module._migrate_ensure_agent_runtime_tables()
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(body="Please wire this into the inbox."),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert response.json()["routed"] is True
    assert len(handle.accepted) == 1
    assert len(_pending_linear_notifications()) == 1
    with engine.connect() as connection:
        assert _notification_fk_targets(
            connection, "provider_conversation_inbox_notifications"
        ) == ["inbox_notifications"]
        assert _notification_fk_targets(connection, "agent_runtime_notifications") == [
            "inbox_notifications"
        ]


def test_linear_agent_webhook_does_not_route_created_session_with_prompt_context_only(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_context_only_payload(),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert response.json()["routed"] is False
    assert len(handle.accepted) == 0
    thread = get_thread("linear", "session-context-only")
    assert thread is not None
    messages = list_messages(thread.id)
    assert messages == []


def test_linear_agent_webhook_suppresses_app_created_bootstrap_then_routes_user_prompt(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )
    base_session = {
        "id": "session-proactive",
        "url": "https://linear.app/session/session-proactive",
        "creator": None,
        "sourceMetadata": None,
        "comment": {
            "id": "comment-linear",
            "body": "RJ Wilson connected Discovery Partner to this issue.",
        },
        "issue": {
            "id": "issue-67",
            "identifier": "CAO-67",
            "title": "Allow proactive sessions",
        },
    }

    bootstrap = client.post(
        "/linear/webhooks/agent",
        json={"action": "created", "data": {"agentSession": base_session}},
        headers=_linear_headers("delivery-bootstrap"),
    )
    prompt = client.post(
        "/linear/webhooks/agent",
        json={
            "action": "created",
            "data": {
                "agentSession": base_session,
                "agentActivity": {
                    "id": "activity-user-prompt",
                    "content": {"type": "prompt", "body": "testing"},
                },
            },
        },
        headers=_linear_headers("delivery-prompt"),
    )

    assert bootstrap.status_code == 200
    assert bootstrap.json()["routed"] is False
    assert prompt.status_code == 200
    assert prompt.json()["routed"] is True
    assert len(handle.accepted) == 1
    thread = get_thread("linear", "session-proactive")
    assert thread is not None
    messages = list_messages(thread.id)
    assert [message.body for message in messages] == ["testing"]
    assert _pending_linear_notifications()[0].message.body == "testing"


def test_linear_agent_webhook_policy_denial_suppresses_discovery_runtime_and_comments(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _FakeRuntimeHandle(receiver_id="agent:discovery_partner")
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._resolve_linear_event",
        lambda event: _resolved_discovery_presence(),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.should_enable_linear_agent_policies",
        lambda: True,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(
            True,
            app_key="discovery_partner",
        ),
    )
    comments = []
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.app_client.create_comment_on_issue",
        lambda issue_id, body, *, app_key=None: comments.append(
            {"issue_id": issue_id, "body": body, "app_key": app_key}
        )
        or {"id": "comment-policy"},
    )

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        assert variables == {"id": "issue-implementation"}
        assert access_token == "linear-token"
        assert app_key == "discovery_partner"
        return {
            "data": {
                "issue": {
                    "id": "issue-implementation",
                    "identifier": "CAO-69",
                    "title": "Implement bounded work",
                    "description": "This has a Coding Implementation Plan.",
                    "state": {"name": "Todo", "type": "unstarted"},
                    "team": {"key": "CAO", "name": "CAO"},
                    "labels": {"nodes": []},
                }
            }
        }

    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.agent_policies.app_client.linear_graphql",
        fake_graphql,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_delegated_discovery_payload(),
        headers=_linear_headers("delivery-discovery-denied"),
    )

    assert response.status_code == 200
    assert response.json()["routed"] is False
    assert handle.accepted == []
    assert comments == [
        {
            "issue_id": "issue-implementation",
            "app_key": "discovery_partner",
            "body": (
                "**CAO policy notice**\n\n"
                "CAO rejected this invocation of Discovery Partner.\n\n"
                "Discovery Partner does not take already-bounded implementation or review "
                "handoffs.\n\n"
                "CAO did not notify or start Discovery Partner."
            ),
        }
    ]
    assert get_processed_event("linear", "delivery-discovery-denied") is None
    assert get_thread("linear", "session-discovery-denied") is None


def test_linear_agent_webhook_policy_disabled_routes_discovery_runtime_without_comment(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _FakeRuntimeHandle(receiver_id="agent:discovery_partner")
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._resolve_linear_event",
        lambda event: _resolved_discovery_presence(),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime._runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.should_enable_linear_agent_policies",
        lambda: False,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(
            True,
            app_key="discovery_partner",
        ),
    )
    comments = []
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.app_client.create_comment_on_issue",
        lambda issue_id, body, *, app_key=None: comments.append(
            {"issue_id": issue_id, "body": body, "app_key": app_key}
        )
        or {"id": "comment-policy"},
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.agent_policies.app_client.linear_graphql",
        Mock(side_effect=AssertionError("disabled policies must not query Linear policy data")),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_delegated_discovery_payload(),
        headers=_linear_headers("delivery-discovery-policy-disabled"),
    )

    assert response.status_code == 200
    assert response.json()["routed"] is True
    assert len(handle.accepted) == 1
    assert comments == []


def test_linear_agent_webhook_posts_accepted_activity_and_external_url_once(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch, terminal_id="terminal-ready")
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(
            True,
            app_key="implementation_partner",
        ),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(body="Please start visibly."),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    handle.create_activity.assert_called_once_with(
        "session-1",
        {
            "type": "thought",
            "body": "CAO accepted this Linear session and is starting or notifying "
            "Implementation Partner.",
        },
        app_key="implementation_partner",
    )
    handle.update_external_url.assert_called_once_with(
        "session-1",
        "terminal-ready",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )


def test_linear_agent_webhook_duplicate_delivery_does_not_duplicate_inbox_or_terminal_effects(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    payload = _linear_agent_payload(body="Only notify once.")
    first = client.post("/linear/webhooks/agent", json=payload, headers=_linear_headers())
    second = client.post("/linear/webhooks/agent", json=payload, headers=_linear_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(_pending_linear_notifications()) == 1
    assert len(handle.accepted) == 1
    handle.create_activity.assert_called_once()
    handle.update_external_url.assert_called_once()


def test_linear_agent_webhook_retry_after_startup_failure_updates_external_url_once(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    failed_handle = _use_mapped_linear_runtime(
        monkeypatch,
        terminal_id=None,
        status=AgentRuntimeStatus.NOT_STARTED,
        error="cannot start yet",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )
    payload = _linear_agent_payload(body="Persist me until startup works.")

    first = client.post("/linear/webhooks/agent", json=payload, headers=_linear_headers())
    ready_handle = _use_mapped_linear_runtime(monkeypatch, terminal_id="terminal-ready")
    second = client.post("/linear/webhooks/agent", json=payload, headers=_linear_headers())
    third = client.post("/linear/webhooks/agent", json=payload, headers=_linear_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert failed_handle.update_external_url.call_count == 0
    ready_handle.update_external_url.assert_called_once_with(
        "session-1",
        "terminal-ready",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )
    assert len(_pending_linear_notifications()) == 1
    failed_handle.create_activity.assert_any_call(
        "session-1",
        {
            "type": "error",
            "body": "CAO could not start or reuse the mapped runtime. "
            "The inbox notification was saved for retry.",
        },
        app_key="implementation_partner",
    )
    ready_handle.create_activity.assert_not_called()


def test_linear_agent_webhook_duplicate_activity_does_not_duplicate_lifecycle_effects(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    payload = _linear_agent_payload(body="Only one lifecycle set.", activity_id="activity-1")
    first = client.post("/linear/webhooks/agent", json=payload, headers=_linear_headers())
    second = client.post(
        "/linear/webhooks/agent",
        json=payload,
        headers=_linear_headers("delivery-2"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(_pending_linear_notifications()) == 1
    handle.create_activity.assert_called_once()
    handle.update_external_url.assert_called_once()


def test_linear_agent_sessions_produce_distinct_provider_conversation_inbox_sources(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(session_id="session-1", activity_id="activity-1"),
        headers=_linear_headers("delivery-1"),
    )
    client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(session_id="session-2", activity_id="activity-2"),
        headers=_linear_headers("delivery-2"),
    )

    messages = _pending_linear_notifications()
    assert len(messages) == 2
    assert {delivery.notification.source_kind for delivery in messages} == {
        PROVIDER_CONVERSATION_INBOX_SOURCE_KIND
    }
    assert messages[0].notification.source_id != messages[1].notification.source_id
    assert messages[0].notification.source_id == str(get_thread("linear", "session-1").id)
    assert messages[1].notification.source_id == str(get_thread("linear", "session-2").id)


def test_linear_lifecycle_api_failures_are_logged_without_secret_payloads(
    client,
    monkeypatch,
    caplog,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(monkeypatch, terminal_id="terminal-ready")
    handle.update_external_url.side_effect = RuntimeError(
        "Linear failed access_token=secret-token Authorization: Bearer bearer-secret "
        + ("payload " * 200)
        + '\n  File "/tmp/linear.py", line 1'
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    with caplog.at_level("WARNING", logger="cli_agent_orchestrator.linear.runtime"):
        response = client.post(
            "/linear/webhooks/agent",
            json=_linear_agent_payload(body="Lifecycle should be best effort."),
            headers=_linear_headers(),
        )

    assert response.status_code == 200
    log_text = caplog.text
    assert "Failed to update Linear AgentSession external URL" in log_text
    assert "secret-token" not in log_text
    assert "bearer-secret" not in log_text
    assert "/tmp/linear.py" not in log_text
    assert "payload " * 80 not in log_text


def test_linear_text_preview_is_lightweight_and_bounded(client, monkeypatch):
    _test_session(monkeypatch)
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )
    body = "Latest Linear request. " + "older transcript line " * 80

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(body=body),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    notification = _pending_linear_notifications()[0].notification.body
    assert len(notification) <= 700
    assert "Latest Linear request." in notification
    assert notification.count("older transcript line") < 20


def test_linear_attachment_metadata_does_not_block_text_notification(client, monkeypatch):
    _test_session(monkeypatch)
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(
            body="Text should still notify.",
            extra_content={"attachments": [{"id": "file-1", "name": "trace.png"}]},
        ),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    notification = _pending_linear_notifications()[0].notification.body
    assert "Text should still notify." in notification


def test_linear_agent_webhook_posts_bounded_error_activity_when_runtime_startup_fails(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(
        monkeypatch,
        terminal_id=None,
        status=AgentRuntimeStatus.NOT_STARTED,
        error="Traceback: LINEAR_ACCESS_TOKEN=secret-value\n" + ("frame " * 100),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(body="Please start even if offline."),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert handle.update_external_url.call_count == 0
    assert handle.create_activity.call_count == 2
    error_content = handle.create_activity.call_args_list[1].args[1]
    assert error_content["type"] == "error"
    assert len(error_content["body"]) <= 220
    assert "could not start or reuse" in error_content["body"]
    assert "secret-value" not in error_content["body"]
    assert "LINEAR_ACCESS_TOKEN" not in error_content["body"]


def test_linear_agent_webhook_does_not_report_startup_failed_for_delivery_error_after_terminal(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    handle = _use_mapped_linear_runtime(
        monkeypatch,
        terminal_id="terminal-ready",
        status=AgentRuntimeStatus.IDLE,
        error="delivery failed after terminal startup",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(body="Please start and deliver."),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    handle.update_external_url.assert_called_once()
    handle.create_activity.assert_called_once()
    assert handle.create_activity.call_args.args[1]["type"] == "thought"


def test_linear_reply_from_inbox_notification_routes_through_linear_provider(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(
            True,
            app_key="implementation_partner",
        ),
    )
    create_activity = Mock(return_value={"id": "reply-1"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        create_activity,
    )

    client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )
    notification = _pending_linear_notifications()[0].notification

    result = reply_to_inbox_message(
        notification.id,
        "Reply through Linear",
        caller_terminal_id=_attach_reply_terminal(),
    )

    create_activity.assert_called_with(
        "session-1",
        {"type": "response", "body": "Reply through Linear"},
        app_key="implementation_partner",
    )
    assert result.outbound_message.external_id == "reply-1"
    assert result.outbound_message.state == "delivered"


def test_linear_reply_failure_from_inbox_notification_is_visible(client, monkeypatch):
    _test_session(monkeypatch)
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: _verified_linear_app(),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.app_client.create_agent_activity",
        Mock(side_effect=RuntimeError("Linear down")),
    )

    client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )
    notification = _pending_linear_notifications()[0].notification

    with pytest.raises(ProviderConversationReplyDeliveryError, match="provider reply failed"):
        reply_to_inbox_message(
            notification.id,
            "This should surface failure",
            caller_terminal_id=_attach_reply_terminal(),
        )

    thread = get_thread("linear", "session-1")
    failed = list_messages(thread.id)[-1]
    assert failed.direction == "outbound"
    assert failed.state == "failed"
    assert failed.metadata["error"] == "Linear down"
    assert failed.metadata["reply_status"] == "failed"

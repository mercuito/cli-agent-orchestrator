"""Tests for Linear app OAuth and webhook API routes."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.agent_identity import AgentIdentity
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.linear.app_client import LinearWebhookVerification
from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearPresence,
    LinearResolvedPresence,
    LinearWorkspaceProviderConfigError,
)
from cli_agent_orchestrator.presence.inbox_bridge import PRESENCE_INBOX_SOURCE_KIND
from cli_agent_orchestrator.presence.manager import (
    PresenceProviderManager,
    presence_provider_manager,
)
from cli_agent_orchestrator.presence.persistence import (
    get_processed_event,
    get_thread,
    list_messages,
)
from cli_agent_orchestrator.presence.reply_service import (
    PresenceReplyDeliveryError,
    reply_to_inbox_message,
)
from cli_agent_orchestrator.runtime.agent import (
    AgentRuntimeDeliveryResult,
    AgentRuntimeNotifyResult,
    AgentRuntimeStatus,
)


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


def _pending_linear_notifications():
    return db_module.list_pending_inbox_notifications("agent:implementation_partner", limit=10)


def _disable_linear_inbox_receiver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.inbox_bridge.app_client.linear_env",
        lambda name: None,
    )


def _enable_linear_inbox_receiver(monkeypatch: pytest.MonkeyPatch, receiver_id: str) -> Mock:
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.inbox_bridge.app_client.linear_env",
        lambda name: receiver_id if name == "LINEAR_PRESENCE_INBOX_RECEIVER_ID" else None,
    )
    delivery = Mock()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.inbox_bridge.inbox_service.check_and_send_pending_messages",
        delivery,
    )
    return delivery


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
                    "title": "Wire Linear presence events into inbox bridge",
                },
            },
            "agentActivity": {
                "id": activity_id,
                "content": content,
            },
        },
    }


def _linear_headers(delivery_id: str = "delivery-1") -> dict:
    return {
        "Linear-Signature": "signature",
        "Linear-Delivery": delivery_id,
        "Linear-Event": "AgentSessionEvent",
    }


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

    def accept_notification(self, notification):
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
        identity=AgentIdentity(
            id="implementation_partner",
            display_name="Implementation Partner",
            agent_profile="developer",
            cli_provider="codex",
            workdir="/repo",
            session_name="implementation-partner",
        ),
    )


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
        lambda resolved: handle,
    )
    handle.update_external_url = Mock()
    handle.create_activity = Mock(return_value={"id": "activity-lifecycle"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.app_client.update_agent_session_external_url",
        handle.update_external_url,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.app_client.create_agent_activity",
        handle.create_activity,
    )
    return handle


@pytest.fixture(autouse=True)
def _legacy_linear_route_compatibility(tmp_path, monkeypatch):
    config_path = tmp_path / "workspace-providers.toml"
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_providers.registry.WORKSPACE_PROVIDERS_CONFIG_PATH",
        config_path,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.has_legacy_linear_provider_config",
        lambda: True,
    )


def test_linear_oauth_callback_requires_code(client):
    response = client.get("/linear/oauth/callback")

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing Linear OAuth code"


def test_linear_oauth_callback_returns_install_identity(client, monkeypatch):
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


def test_linear_routes_honor_disabled_workspace_provider(client, tmp_path, monkeypatch):
    enabled_config = tmp_path / "workspace-providers.toml"
    enabled_config.write_text('enabled = ["github"]\n')
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_providers.registry.WORKSPACE_PROVIDERS_CONFIG_PATH",
        enabled_config,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Linear workspace provider is not enabled"


def test_linear_routes_require_explicit_or_legacy_provider_config(client, tmp_path, monkeypatch):
    config_path = tmp_path / "missing-workspace-providers.toml"
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_providers.registry.WORKSPACE_PROVIDERS_CONFIG_PATH",
        config_path,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.has_legacy_linear_provider_config",
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
    presence_provider_manager.clear_providers()
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
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
        "app_key": None,
        "agent_session_id": "session-1",
        "routed": True,
    }
    assert len(handle.accepted) == 1
    assert get_processed_event("linear", "delivery-1").event_type == "AgentSessionEvent"
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_routes_verified_app_key_to_runtime(client, monkeypatch):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
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
    assert _pending_linear_notifications()[0].message.source_kind == PRESENCE_INBOX_SOURCE_KIND
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_duplicate_delivery_does_not_duplicate_mapped_runtime_notification(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
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
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_unknown_mapping_is_not_routed(client, monkeypatch):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
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
    assert get_thread("linear", "session-1") is not None
    assert _pending_linear_notifications() == []
    handle_factory.assert_not_called()
    presence_provider_manager.clear_providers()


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


def test_linear_agent_webhook_creates_presence_records_and_inbox_notification(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
    assert messages[0].message.sender_id == "presence"
    assert messages[0].message.source_kind == PRESENCE_INBOX_SOURCE_KIND
    assert messages[0].message.source_id == str(thread.id)
    assert messages[0].message.route_id == str(thread.id)
    assert "Please wire this into the inbox." in messages[0].message.body
    assert get_processed_event("linear", "delivery-1").event_type == "AgentSessionEvent"
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_posts_accepted_activity_and_external_url_once(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
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
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_duplicate_delivery_does_not_duplicate_inbox_or_terminal_effects(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_duplicate_activity_does_not_duplicate_lifecycle_effects(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    handle = _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
    presence_provider_manager.clear_providers()


def test_linear_agent_sessions_produce_distinct_presence_inbox_sources(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
    assert {delivery.message.source_kind for delivery in messages} == {PRESENCE_INBOX_SOURCE_KIND}
    assert messages[0].message.source_id != messages[1].message.source_id
    assert messages[0].message.source_id == str(get_thread("linear", "session-1").id)
    assert messages[1].message.source_id == str(get_thread("linear", "session-2").id)
    presence_provider_manager.clear_providers()


def test_linear_text_preview_is_lightweight_and_bounded(client, monkeypatch):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
    )
    body = "Latest Linear request. " + "older transcript line " * 80

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(body=body),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    notification = _pending_linear_notifications()[0].message.body
    assert len(notification) <= 700
    assert "Latest Linear request." in notification
    assert notification.count("older transcript line") < 20
    presence_provider_manager.clear_providers()


def test_linear_attachment_metadata_does_not_block_text_notification(client, monkeypatch):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
    notification = _pending_linear_notifications()[0].message.body
    assert "Text should still notify." in notification
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_posts_bounded_error_activity_when_runtime_startup_fails(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    handle = _use_mapped_linear_runtime(
        monkeypatch,
        terminal_id=None,
        status=AgentRuntimeStatus.NOT_STARTED,
        error="Traceback: LINEAR_ACCESS_TOKEN=secret-value\n" + ("frame " * 100),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_does_not_report_startup_failed_for_delivery_error_after_terminal(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    handle = _use_mapped_linear_runtime(
        monkeypatch,
        terminal_id="terminal-ready",
        status=AgentRuntimeStatus.IDLE,
        error="delivery failed after terminal startup",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
    presence_provider_manager.clear_providers()


def test_linear_reply_from_inbox_notification_routes_through_provider_registry(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(
            True,
            app_key="implementation_partner",
        ),
    )
    create_activity = Mock(return_value={"id": "reply-1"})
    manager = PresenceProviderManager(
        {
            "linear": LinearPresenceProvider(
                client=Mock(create_agent_activity=create_activity),
            )
        }
    )

    client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )
    notification = _pending_linear_notifications()[0].notification

    result = reply_to_inbox_message(
        notification.id, "Reply through Linear", provider_manager=manager
    )

    create_activity.assert_called_once_with(
        "session-1",
        {"type": "response", "body": "Reply through Linear"},
        app_key="implementation_partner",
    )
    assert result.outbound_message.external_id == "reply-1"
    assert result.outbound_message.state == "delivered"
    presence_provider_manager.clear_providers()


def test_linear_reply_failure_from_inbox_notification_is_visible(client, monkeypatch):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _use_mapped_linear_runtime(monkeypatch)
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
    )
    manager = PresenceProviderManager(
        {
            "linear": LinearPresenceProvider(
                client=Mock(create_agent_activity=Mock(side_effect=RuntimeError("Linear down"))),
            )
        }
    )

    client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(),
        headers=_linear_headers(),
    )
    notification = _pending_linear_notifications()[0].notification

    with pytest.raises(PresenceReplyDeliveryError, match="provider reply failed"):
        reply_to_inbox_message(
            notification.id, "This should surface failure", provider_manager=manager
        )

    thread = get_thread("linear", "session-1")
    failed = list_messages(thread.id)[-1]
    assert failed.direction == "outbound"
    assert failed.state == "failed"
    assert failed.metadata["error"] == "Linear down"
    assert failed.metadata["reply_status"] == "failed"
    presence_provider_manager.clear_providers()

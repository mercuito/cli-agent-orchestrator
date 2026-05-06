"""Tests for Linear app OAuth and webhook API routes."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base, get_inbox_messages
from cli_agent_orchestrator.linear.app_client import LinearWebhookVerification
from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider
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
    _disable_linear_inbox_receiver(monkeypatch)
    presence_provider_manager.clear_providers()
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
    routed = Mock()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.handle_presence_event",
        routed,
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
    routed.assert_called_once()
    assert get_processed_event("linear", "delivery-1").event_type == "AgentSessionEvent"
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_routes_verified_app_key_to_runtime(client, monkeypatch):
    _test_session(monkeypatch)
    _disable_linear_inbox_receiver(monkeypatch)
    presence_provider_manager.clear_providers()
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
    routed = Mock()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.handle_presence_event",
        routed,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json={"action": "created"},
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert response.json()["app_key"] == "implementation_partner"
    routed.assert_called_once()
    event = routed.call_args.args[0]
    assert event.raw_payload["_cao_linear_app_key"] == "implementation_partner"
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_duplicate_delivery_does_not_rerun_smoke_runtime(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    _disable_linear_inbox_receiver(monkeypatch)
    presence_provider_manager.clear_providers()
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
    routed = Mock()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.handle_presence_event",
        routed,
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
    routed.assert_called_once()
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
    delivery = _enable_linear_inbox_receiver(monkeypatch, "terminal-inbox")
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
    )
    routed = Mock()
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.runtime.handle_presence_event",
        routed,
    )

    response = client.post(
        "/linear/webhooks/agent",
        json=_linear_agent_payload(body="Please wire this into the inbox."),
        headers=_linear_headers(),
    )

    assert response.status_code == 200
    assert response.json()["routed"] is True
    routed.assert_not_called()
    delivery.assert_called_once_with("terminal-inbox")
    thread = get_thread("linear", "session-1")
    assert thread is not None
    messages = get_inbox_messages("terminal-inbox", limit=10)
    assert len(messages) == 1
    assert messages[0].sender_id == "presence"
    assert messages[0].source_kind == PRESENCE_INBOX_SOURCE_KIND
    assert messages[0].source_id == str(thread.id)
    assert "Please wire this into the inbox." in messages[0].message
    assert get_processed_event("linear", "delivery-1").event_type == "AgentSessionEvent"
    presence_provider_manager.clear_providers()


def test_linear_agent_webhook_duplicate_delivery_does_not_duplicate_inbox_or_terminal_effects(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    delivery = _enable_linear_inbox_receiver(monkeypatch, "terminal-inbox")
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
    )

    payload = _linear_agent_payload(body="Only notify once.")
    first = client.post("/linear/webhooks/agent", json=payload, headers=_linear_headers())
    second = client.post("/linear/webhooks/agent", json=payload, headers=_linear_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(get_inbox_messages("terminal-inbox", limit=10)) == 1
    delivery.assert_called_once_with("terminal-inbox")
    presence_provider_manager.clear_providers()


def test_linear_agent_sessions_produce_distinct_presence_inbox_sources(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _enable_linear_inbox_receiver(monkeypatch, "terminal-inbox")
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

    messages = get_inbox_messages("terminal-inbox", limit=10)
    assert len(messages) == 2
    assert {message.source_kind for message in messages} == {PRESENCE_INBOX_SOURCE_KIND}
    assert messages[0].source_id != messages[1].source_id
    assert messages[0].source_id == str(get_thread("linear", "session-1").id)
    assert messages[1].source_id == str(get_thread("linear", "session-2").id)
    presence_provider_manager.clear_providers()


def test_linear_text_preview_is_lightweight_and_bounded(client, monkeypatch):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _enable_linear_inbox_receiver(monkeypatch, "terminal-inbox")
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
    notification = get_inbox_messages("terminal-inbox", limit=10)[0].message
    assert len(notification) <= 700
    assert "Latest Linear request." in notification
    assert notification.count("older transcript line") < 20
    presence_provider_manager.clear_providers()


def test_linear_attachment_metadata_does_not_block_text_notification(client, monkeypatch):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _enable_linear_inbox_receiver(monkeypatch, "terminal-inbox")
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
    notification = get_inbox_messages("terminal-inbox", limit=10)[0].message
    assert "Text should still notify." in notification
    assert "Attachment/media metadata present." in notification
    presence_provider_manager.clear_providers()


def test_linear_reply_from_inbox_notification_routes_through_provider_registry(
    client,
    monkeypatch,
):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _enable_linear_inbox_receiver(monkeypatch, "terminal-inbox")
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook_source",
        lambda raw, signature, payload: LinearWebhookVerification(True),
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
    inbox = get_inbox_messages("terminal-inbox", limit=10)[0]

    result = reply_to_inbox_message(inbox.id, "Reply through Linear", provider_manager=manager)

    create_activity.assert_called_once_with(
        "session-1",
        {"type": "response", "body": "Reply through Linear"},
    )
    assert result.outbound_message.external_id == "reply-1"
    assert result.outbound_message.state == "delivered"
    presence_provider_manager.clear_providers()


def test_linear_reply_failure_from_inbox_notification_is_visible(client, monkeypatch):
    _test_session(monkeypatch)
    presence_provider_manager.clear_providers()
    _enable_linear_inbox_receiver(monkeypatch, "terminal-inbox")
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
    inbox = get_inbox_messages("terminal-inbox", limit=10)[0]

    with pytest.raises(PresenceReplyDeliveryError, match="provider reply failed"):
        reply_to_inbox_message(inbox.id, "This should surface failure", provider_manager=manager)

    thread = get_thread("linear", "session-1")
    failed = list_messages(thread.id)[-1]
    assert failed.direction == "outbound"
    assert failed.state == "failed"
    assert failed.metadata["error"] == "Linear down"
    assert failed.metadata["reply_status"] == "failed"
    presence_provider_manager.clear_providers()

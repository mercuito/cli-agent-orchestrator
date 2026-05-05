"""Tests for Linear app OAuth and webhook API routes."""

from __future__ import annotations

from unittest.mock import Mock


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
    monkeypatch.setattr("cli_agent_orchestrator.linear.routes.app_client.install_linear_app", install)

    response = client.get("/linear/oauth/callback?code=code-123&state=state-123")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "viewer_id": "app-user-1",
        "viewer_name": "Discovery Partner",
        "token_type": "Bearer",
        "expires_in": 3600,
        "state_verified": True,
    }
    install.assert_called_once_with("code-123", "state-123")


def test_linear_oauth_callback_surfaces_linear_error(client):
    response = client.get(
        "/linear/oauth/callback?error=access_denied&error_description=Nope"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Nope"


def test_linear_agent_webhook_accepts_event(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.parse_webhook_payload",
        lambda raw: {
            "action": "created",
            "data": {"agentSession": {"id": "session-1"}},
        },
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.routes.app_client.verify_webhook",
        lambda raw, signature, payload: True,
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
        "agent_session_id": "session-1",
        "routed": True,
    }
    routed.assert_called_once()


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

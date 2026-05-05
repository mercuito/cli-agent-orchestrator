"""Tests for Linear app OAuth and webhook helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import Mock

import pytest

from cli_agent_orchestrator.linear import app_client


def test_validate_oauth_state_is_disabled_without_expected_state(monkeypatch):
    monkeypatch.setattr(app_client, "linear_env", lambda name: None)

    assert app_client.validate_oauth_state("anything") is False


def test_validate_oauth_state_accepts_matching_state(monkeypatch):
    monkeypatch.setattr(app_client, "linear_env", lambda name: "state-123")

    assert app_client.validate_oauth_state("state-123") is True


def test_validate_oauth_state_rejects_mismatch(monkeypatch):
    monkeypatch.setattr(app_client, "linear_env", lambda name: "state-123")

    with pytest.raises(app_client.LinearOAuthError):
        app_client.validate_oauth_state("wrong")


def test_exchange_oauth_code_posts_expected_form(monkeypatch):
    env = {
        "LINEAR_CLIENT_ID": "client-id",
        "LINEAR_CLIENT_SECRET": "secret",
        "LINEAR_OAUTH_REDIRECT_URI": "https://example.test/linear/oauth/callback",
    }
    monkeypatch.setattr(app_client, "linear_env", env.get)

    response = Mock(status_code=200)
    response.json.return_value = {"access_token": "access-token"}
    post = Mock(return_value=response)
    monkeypatch.setattr(app_client.requests, "post", post)

    assert app_client.exchange_oauth_code("code-123") == {"access_token": "access-token"}
    post.assert_called_once()
    assert post.call_args.args == (app_client.LINEAR_TOKEN_URL,)
    assert post.call_args.kwargs["data"] == {
        "grant_type": "authorization_code",
        "code": "code-123",
        "redirect_uri": "https://example.test/linear/oauth/callback",
        "client_id": "client-id",
        "client_secret": "secret",
    }


def test_fetch_viewer_returns_viewer(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"data": {"viewer": {"id": "app-user-1", "name": "Discovery"}}}
    post = Mock(return_value=response)
    monkeypatch.setattr(app_client.requests, "post", post)

    assert app_client.fetch_viewer("access-token") == {
        "id": "app-user-1",
        "name": "Discovery",
    }
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer access-token"}


def test_install_linear_app_persists_tokens_and_viewer(monkeypatch):
    saved = {}
    monkeypatch.setattr(app_client, "validate_oauth_state", lambda state: True)
    monkeypatch.setattr(
        app_client,
        "exchange_oauth_code",
        lambda code: {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(
        app_client,
        "fetch_viewer",
        lambda token: {"id": "app-user-1", "name": "Discovery Partner"},
    )
    monkeypatch.setattr(app_client, "set_env_var", lambda key, value: saved.update({key: value}))

    result = app_client.install_linear_app("code-123", "state-123")

    assert result["viewer"] == {"id": "app-user-1", "name": "Discovery Partner"}
    assert result["state_verified"] is True
    assert saved["LINEAR_ACCESS_TOKEN"] == "access-token"
    assert saved["LINEAR_REFRESH_TOKEN"] == "refresh-token"
    assert saved["LINEAR_APP_USER_ID"] == "app-user-1"
    assert saved["LINEAR_APP_USER_NAME"] == "Discovery Partner"
    assert "LINEAR_TOKEN_EXPIRES_AT" in saved


def test_get_issue_returns_linear_issue(monkeypatch):
    graphql = Mock(
        return_value={
            "data": {
                "issue": {
                    "id": "issue-1",
                    "identifier": "CAO-14",
                    "title": "Demo",
                    "url": "https://linear.app/demo",
                }
            }
        }
    )
    monkeypatch.setattr(app_client, "linear_graphql", graphql)

    assert app_client.get_issue("CAO-14")["id"] == "issue-1"
    graphql.assert_called_once()


def test_get_issue_requires_issue(monkeypatch):
    monkeypatch.setattr(app_client, "linear_graphql", Mock(return_value={"data": {}}))

    with pytest.raises(app_client.LinearAppError, match="Linear issue not found"):
        app_client.get_issue("NOPE-1")


def test_create_agent_session_on_issue_sets_external_urls(monkeypatch):
    graphql = Mock(
        return_value={
            "data": {
                "agentSessionCreateOnIssue": {
                    "agentSession": {"id": "session-1", "url": "https://linear.app/session"}
                }
            }
        }
    )
    monkeypatch.setattr(app_client, "linear_graphql", graphql)

    session = app_client.create_agent_session_on_issue(
        "issue-1",
        external_urls=[{"label": "Open CAO", "url": "https://cao.test/terminals/t1"}],
    )

    assert session["id"] == "session-1"
    assert graphql.call_args.args[1] == {
        "input": {
            "issueId": "issue-1",
            "externalUrls": [{"label": "Open CAO", "url": "https://cao.test/terminals/t1"}],
        }
    }


def test_create_agent_activity_posts_content(monkeypatch):
    graphql = Mock(
        return_value={"data": {"agentActivityCreate": {"agentActivity": {"id": "activity-1"}}}}
    )
    monkeypatch.setattr(app_client, "linear_graphql", graphql)

    activity = app_client.create_agent_activity(
        "session-1", {"type": "thought", "body": "Working"}
    )

    assert activity["id"] == "activity-1"
    assert graphql.call_args.args[1] == {
        "input": {
            "agentSessionId": "session-1",
            "content": {"type": "thought", "body": "Working"},
        }
    }


def test_get_agent_session_returns_presence_fields(monkeypatch):
    graphql = Mock(
        return_value={
            "data": {
                "agentSession": {
                    "id": "session-1",
                    "url": "https://linear.app/session",
                    "context": {"issue": "CAO-18"},
                    "issue": {"id": "issue-1", "identifier": "CAO-18"},
                }
            }
        }
    )
    monkeypatch.setattr(app_client, "linear_graphql", graphql)

    session = app_client.get_agent_session("session-1")

    assert session["id"] == "session-1"
    query = graphql.call_args.args[0]
    assert "context" in query
    assert "promptContext" not in query
    assert graphql.call_args.args[1] == {"id": "session-1"}


def test_list_agent_session_activities_returns_first_page_nodes(monkeypatch):
    graphql = Mock(
        return_value={
            "data": {
                "agentSession": {
                    "id": "session-1",
                    "activities": {
                        "nodes": [
                            {"id": "activity-1", "content": {"type": "prompt"}},
                            "not-an-activity",
                        ]
                    },
                }
            }
        }
    )
    monkeypatch.setattr(app_client, "linear_graphql", graphql)

    activities = app_client.list_agent_session_activities("session-1")

    assert activities == [{"id": "activity-1", "content": {"type": "prompt"}}]
    query = graphql.call_args.args[0]
    assert "activities(first: 50)" in query
    assert "AgentActivityPromptContent" in query
    assert "agentActivities" not in query
    assert "\n                type\n" not in query
    assert "\n                body\n" not in query
    assert graphql.call_args.args[1] == {"id": "session-1"}


def test_verify_linear_webhook_accepts_valid_signature(monkeypatch):
    secret = "webhook-secret"
    payload = {"webhookTimestamp": int(time.time() * 1000), "action": "created"}
    raw_body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    monkeypatch.setattr(
        app_client,
        "linear_env",
        lambda name: secret if name == "LINEAR_WEBHOOK_SECRET" else None,
    )

    assert app_client.verify_webhook(raw_body, signature, payload) is True


def test_verify_linear_webhook_rejects_invalid_signature(monkeypatch):
    payload = {"webhookTimestamp": int(time.time() * 1000), "action": "created"}
    raw_body = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(
        app_client,
        "linear_env",
        lambda name: "webhook-secret" if name == "LINEAR_WEBHOOK_SECRET" else None,
    )

    with pytest.raises(app_client.LinearWebhookVerificationError):
        app_client.verify_webhook(raw_body, "bad-signature", payload)


def test_verify_linear_webhook_returns_false_when_secret_missing(monkeypatch):
    monkeypatch.setattr(app_client, "linear_env", lambda name: None)

    assert app_client.verify_webhook(b"{}", None, {}) is False


def test_parse_webhook_payload_rejects_invalid_json():
    with pytest.raises(app_client.LinearWebhookVerificationError):
        app_client.parse_webhook_payload(b"not-json")

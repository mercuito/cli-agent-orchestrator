"""Tests for Linear app OAuth and webhook helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear import workspace_provider as linear_provider


def _future_token_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


@pytest.fixture(autouse=True)
def _isolate_linear_provider_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        linear_provider,
        "LINEAR_PROVIDER_CONFIG_PATH",
        tmp_path / "workspace-providers" / "linear.toml",
    )


def test_validate_oauth_state_is_disabled_without_expected_state(monkeypatch):
    monkeypatch.setattr(app_client, "linear_env", lambda name: None)

    assert app_client.validate_oauth_state("anything") is False


def test_validate_oauth_state_accepts_matching_state(monkeypatch):
    monkeypatch.setattr(
        app_client,
        "linear_env",
        lambda name: "state-123" if name == "LINEAR_OAUTH_STATE" else None,
    )

    assert app_client.validate_oauth_state("state-123") is True


def test_validate_oauth_state_rejects_mismatch(monkeypatch):
    monkeypatch.setattr(
        app_client,
        "linear_env",
        lambda name: "state-123" if name == "LINEAR_OAUTH_STATE" else None,
    )

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


def test_exchange_oauth_code_uses_app_specific_credentials(monkeypatch):
    env = {
        "LINEAR_APP_IMPLEMENTATION_PARTNER_CLIENT_ID": "impl-client",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_CLIENT_SECRET": "impl-secret",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_OAUTH_REDIRECT_URI": (
            "https://example.test/linear/oauth/callback"
        ),
    }
    monkeypatch.setattr(app_client, "linear_env", env.get)

    response = Mock(status_code=200)
    response.json.return_value = {"access_token": "impl-token"}
    post = Mock(return_value=response)
    monkeypatch.setattr(app_client.requests, "post", post)

    assert app_client.exchange_oauth_code("code-123", app_key="implementation_partner") == {
        "access_token": "impl-token"
    }
    assert post.call_args.kwargs["data"]["client_id"] == "impl-client"
    assert post.call_args.kwargs["data"]["client_secret"] == "impl-secret"


def test_install_linear_app_uses_structured_presence_for_plain_oauth_state(tmp_path, monkeypatch):
    config_path = tmp_path / "workspace-providers" / "linear.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("""
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
client_id = "structured-client"
client_secret = "structured-secret"
oauth_redirect_uri = "https://example.test/linear/oauth/callback"
oauth_state = "nonce-123"
""")

    def post(url, **kwargs):
        response = Mock(status_code=200)
        if url == app_client.LINEAR_TOKEN_URL:
            assert kwargs["data"]["client_id"] == "structured-client"
            assert kwargs["data"]["client_secret"] == "structured-secret"
            assert kwargs["data"]["redirect_uri"] == "https://example.test/linear/oauth/callback"
            response.json.return_value = {
                "access_token": "structured-access-token",
                "refresh_token": "structured-refresh-token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
            return response
        if url == app_client.LINEAR_GRAPHQL_URL:
            response.json.return_value = {
                "data": {
                    "viewer": {
                        "id": "app-user-impl",
                        "name": "Implementation Partner",
                    }
                }
            }
            return response
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(app_client.requests, "post", post)

    result = app_client.install_linear_app("code-123", "nonce-123")

    assert result["app_key"] == "implementation_partner"
    config = linear_provider.load_linear_provider_config(
        config_path=config_path,
        allow_legacy_env=False,
    )
    assert config is not None
    presence = config.presence_by_app_key("implementation_partner")
    assert presence is not None
    assert presence.access_token == "structured-access-token"
    assert presence.refresh_token == "structured-refresh-token"
    assert presence.app_user_id == "app-user-impl"
    assert presence.app_user_name == "Implementation Partner"


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


def test_refresh_access_token_posts_refresh_grant_and_persists_rotation(monkeypatch):
    presence = linear_provider.LinearPresence(
        presence_id="implementation_partner",
        agent_id="implementation_partner",
        app_key="implementation_partner",
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="old-refresh-token",
    )
    response = Mock(status_code=200)
    response.json.return_value = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "expires_in": 3600,
    }
    post = Mock(return_value=response)
    persist = Mock()
    monkeypatch.setattr(app_client.requests, "post", post)
    monkeypatch.setattr(linear_provider, "persist_linear_oauth_install", persist)

    assert app_client.refresh_access_token(presence) == "new-access-token"

    assert post.call_args.args == (app_client.LINEAR_TOKEN_URL,)
    assert post.call_args.kwargs["data"] == {
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh-token",
        "client_id": "client-id",
        "client_secret": "client-secret",
    }
    persist.assert_called_once()
    assert persist.call_args.kwargs["app_key"] == "implementation_partner"
    assert persist.call_args.kwargs["access_token"] == "new-access-token"
    assert persist.call_args.kwargs["refresh_token"] == "new-refresh-token"
    assert persist.call_args.kwargs["token_expires_at"] is not None


def test_access_token_for_presence_refreshes_expired_token(monkeypatch):
    presence = linear_provider.LinearPresence(
        presence_id="implementation_partner",
        agent_id="implementation_partner",
        app_key="implementation_partner",
        access_token="old-access-token",
        refresh_token="refresh-token",
        token_expires_at="2026-05-01T00:00:00+00:00",
    )
    refresh = Mock(return_value="new-access-token")
    monkeypatch.setattr(app_client, "refresh_access_token", refresh)
    monkeypatch.setattr(app_client, "_configured_presence", lambda app_key: None)

    assert app_client.access_token_for_presence(presence) == "new-access-token"

    refresh.assert_called_once_with(presence)


def test_linear_graphql_refreshes_expired_configured_token_before_request(monkeypatch):
    env = {
        "LINEAR_APP_KEYS": "implementation_partner",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_ACCESS_TOKEN": "old-access-token",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_REFRESH_TOKEN": "old-refresh-token",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_TOKEN_EXPIRES_AT": "2026-05-01T00:00:00+00:00",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_CLIENT_ID": "client-id",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_CLIENT_SECRET": "client-secret",
    }
    monkeypatch.setattr(app_client, "linear_env", env.get)
    monkeypatch.setattr(linear_provider, "persist_linear_oauth_install", Mock())

    def post(url, **kwargs):
        response = Mock(status_code=200)
        if url == app_client.LINEAR_TOKEN_URL:
            response.json.return_value = {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600,
            }
            return response
        assert url == app_client.LINEAR_GRAPHQL_URL
        assert kwargs["headers"] == {"Authorization": "Bearer new-access-token"}
        response.json.return_value = {"data": {"ok": True}}
        return response

    monkeypatch.setattr(app_client.requests, "post", post)

    assert app_client.linear_graphql("query Test", app_key="implementation_partner") == {
        "data": {"ok": True}
    }


def test_linear_graphql_refreshes_once_after_auth_error(monkeypatch):
    env = {
        "LINEAR_APP_KEYS": "implementation_partner",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_ACCESS_TOKEN": "old-access-token",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_REFRESH_TOKEN": "old-refresh-token",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_TOKEN_EXPIRES_AT": _future_token_expires_at(),
        "LINEAR_APP_IMPLEMENTATION_PARTNER_CLIENT_ID": "client-id",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_CLIENT_SECRET": "client-secret",
    }
    graph_tokens = []
    monkeypatch.setattr(app_client, "linear_env", env.get)
    monkeypatch.setattr(linear_provider, "persist_linear_oauth_install", Mock())

    def post(url, **kwargs):
        response = Mock(status_code=200)
        if url == app_client.LINEAR_TOKEN_URL:
            response.json.return_value = {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600,
            }
            return response
        assert url == app_client.LINEAR_GRAPHQL_URL
        graph_tokens.append(kwargs["headers"]["Authorization"])
        if len(graph_tokens) == 1:
            response.json.return_value = {
                "errors": [{"message": "Authentication required, not authenticated"}]
            }
        else:
            response.json.return_value = {"data": {"ok": True}}
        return response

    monkeypatch.setattr(app_client.requests, "post", post)

    assert app_client.linear_graphql("query Test", app_key="implementation_partner") == {
        "data": {"ok": True}
    }
    assert graph_tokens == ["Bearer old-access-token", "Bearer new-access-token"]


def test_install_linear_app_persists_tokens_and_viewer(monkeypatch):
    monkeypatch.setattr(app_client, "validate_oauth_state", lambda state, **kwargs: True)
    monkeypatch.setattr(
        app_client,
        "exchange_oauth_code",
        lambda code, **kwargs: {
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
    persist_install = Mock()
    monkeypatch.setattr(linear_provider, "persist_linear_oauth_install", persist_install)

    result = app_client.install_linear_app("code-123", "state-123")

    assert result["viewer"] == {"id": "app-user-1", "name": "Discovery Partner"}
    assert result["state_verified"] is True
    persist_install.assert_called_once()
    assert persist_install.call_args.kwargs["app_key"] is None
    assert persist_install.call_args.kwargs["access_token"] == "access-token"
    assert persist_install.call_args.kwargs["refresh_token"] == "refresh-token"
    assert persist_install.call_args.kwargs["app_user_id"] == "app-user-1"
    assert persist_install.call_args.kwargs["app_user_name"] == "Discovery Partner"
    assert persist_install.call_args.kwargs["token_expires_at"] is not None


def test_install_linear_app_persists_tokens_under_state_app_key(monkeypatch):
    env = {
        "LINEAR_APP_KEYS": "discovery_partner,implementation_partner",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_CLIENT_ID": "impl-client",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_CLIENT_SECRET": "impl-secret",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_OAUTH_REDIRECT_URI": (
            "https://example.test/linear/oauth/callback"
        ),
    }
    monkeypatch.setattr(app_client, "linear_env", env.get)
    monkeypatch.setattr(linear_provider, "update_linear_presence_tokens", lambda *a, **kw: False)
    monkeypatch.setattr(
        app_client,
        "exchange_oauth_code",
        lambda code, *, app_key=None: {
            "access_token": f"{app_key}-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(
        app_client,
        "fetch_viewer",
        lambda token: {"id": "impl-user-1", "name": "Implementation Partner"},
    )
    persist_install = Mock()
    monkeypatch.setattr(linear_provider, "persist_linear_oauth_install", persist_install)

    result = app_client.install_linear_app("code-123", "implementation_partner")

    assert result["app_key"] == "implementation_partner"
    persist_install.assert_called_once()
    assert persist_install.call_args.kwargs["app_key"] == "implementation_partner"
    assert persist_install.call_args.kwargs["access_token"] == "implementation_partner-access-token"
    assert persist_install.call_args.kwargs["app_user_id"] == "impl-user-1"
    assert persist_install.call_args.kwargs["app_user_name"] == "Implementation Partner"


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


def test_public_cao_terminal_url_points_to_dashboard(monkeypatch):
    monkeypatch.setenv("LINEAR_CAO_PUBLIC_URL", "https://cao.test/")
    monkeypatch.setattr(
        app_client,
        "create_terminal_dashboard_token",
        Mock(return_value="signed.token"),
    )

    assert (
        app_client.public_cao_terminal_url("terminal/id")
        == "https://cao.test/?tab=agents&terminal_id=terminal%2Fid&terminal_token=signed.token"
    )


def test_public_cao_agent_url_points_to_stable_agent_deep_link(monkeypatch):
    monkeypatch.setenv("LINEAR_CAO_PUBLIC_URL", "https://cao.test/")
    monkeypatch.setattr(
        app_client,
        "create_agent_dashboard_token",
        Mock(return_value="agent.signed.token"),
    )

    assert (
        app_client.public_cao_agent_url("discovery partner")
        == "https://cao.test/?tab=agents&agent_id=discovery%20partner&agent_token=agent.signed.token"
    )


def test_update_agent_session_external_url_prefers_agent_deep_link(monkeypatch):
    graphql = Mock(return_value={"data": {"agentSessionUpdate": {"success": True}}})
    monkeypatch.setattr(app_client, "linear_graphql", graphql)
    monkeypatch.setattr(
        app_client,
        "public_cao_agent_url",
        Mock(return_value="https://cao.test/?agent_id=discovery_partner"),
    )
    monkeypatch.setattr(
        app_client,
        "public_cao_terminal_url",
        Mock(return_value="https://cao.test/?terminal_id=abcd1234"),
    )

    assert app_client.update_agent_session_external_url(
        "session-1",
        "abcd1234",
        agent_id="discovery_partner",
        app_key="discovery_partner",
    )

    variables = graphql.call_args.args[1]
    assert variables["input"]["externalUrls"] == [
        {"label": "Open CAO", "url": "https://cao.test/?agent_id=discovery_partner"}
    ]
    app_client.public_cao_terminal_url.assert_not_called()


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

    activity = app_client.create_agent_activity("session-1", {"type": "thought", "body": "Working"})

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


def test_verify_linear_webhook_source_identifies_configured_app(monkeypatch):
    env = {
        "LINEAR_APP_KEYS": "discovery_partner,implementation_partner",
        "LINEAR_APP_DISCOVERY_PARTNER_WEBHOOK_SECRET": "discovery-secret",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_WEBHOOK_SECRET": "implementation-secret",
    }
    payload = {"webhookTimestamp": int(time.time() * 1000), "action": "created"}
    raw_body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(
        env["LINEAR_APP_IMPLEMENTATION_PARTNER_WEBHOOK_SECRET"].encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    monkeypatch.setattr(app_client, "linear_env", env.get)

    result = app_client.verify_webhook_source(raw_body, signature, payload)

    assert result.verified is True
    assert result.app_key == "implementation_partner"


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

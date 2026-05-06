"""Linear OAuth, GraphQL, and webhook helpers for CAO-managed app users."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import requests

from cli_agent_orchestrator.linear import workspace_provider as linear_provider

logger = logging.getLogger(__name__)

LINEAR_TOKEN_URL = "https://api.linear.app/oauth/token"
LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
WEBHOOK_TIMESTAMP_TOLERANCE_MS = 60_000
APP_KEY_PATTERN = linear_provider.APP_KEY_PATTERN


class LinearAppError(Exception):
    """Base exception for Linear app integration failures."""


class LinearConfigError(LinearAppError):
    """Required Linear configuration is missing."""


class LinearOAuthError(LinearAppError):
    """Linear OAuth installation failed."""


class LinearWebhookVerificationError(LinearAppError):
    """Linear webhook signature or freshness verification failed."""


@dataclass(frozen=True)
class LinearWebhookVerification:
    """Result of matching and verifying a Linear webhook delivery."""

    verified: bool
    app_key: Optional[str] = None
    agent_id: Optional[str] = None
    app_user_id: Optional[str] = None
    app_user_name: Optional[str] = None


def linear_env(name: str) -> Optional[str]:
    """Read Linear config from process env first, then CAO's managed env file."""
    return linear_provider.linear_env(name)


def normalize_app_key(app_key: str) -> str:
    """Return a stable CAO app key for env lookup and routing."""
    try:
        return linear_provider.normalize_app_key(app_key)
    except linear_provider.LinearWorkspaceProviderConfigError as exc:
        raise LinearConfigError(str(exc)) from exc


def app_env_prefix(app_key: str) -> str:
    """Return the env prefix for a configured Linear app key."""
    return linear_provider.app_env_prefix(app_key)


def linear_app_env(app_key: Optional[str], name: str) -> Optional[str]:
    """Read a Linear app-specific variable, falling back to legacy global config."""
    try:
        return linear_provider.linear_app_env(app_key, name, env_reader=linear_env)
    except linear_provider.LinearWorkspaceProviderConfigError as exc:
        raise LinearConfigError(str(exc)) from exc


def required_linear_app_env(app_key: Optional[str], name: str) -> str:
    try:
        return linear_provider.required_linear_app_env(app_key, name, env_reader=linear_env)
    except linear_provider.LinearWorkspaceProviderConfigError as exc:
        raise LinearConfigError(str(exc)) from exc


def configured_app_keys() -> list[str]:
    """Return configured Linear app keys from structured config or legacy env."""
    try:
        return linear_provider.configured_app_keys(env_reader=linear_env)
    except linear_provider.LinearWorkspaceProviderConfigError as exc:
        raise LinearConfigError(str(exc)) from exc


def required_linear_env(name: str) -> str:
    value = linear_env(name)
    if not value:
        raise LinearConfigError(f"{name} is required")
    return value


def _split_oauth_state(state: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return ``(app_key, nonce)`` from a smoke-test OAuth state value."""
    if not state:
        return None, None

    configured = set(configured_app_keys())
    if ":" in state:
        possible_key, nonce = state.split(":", 1)
        normalized = normalize_app_key(possible_key)
        if normalized in configured:
            return normalized, nonce

    normalized = normalize_app_key(state)
    if normalized in configured:
        return normalized, None

    matched_key = linear_provider.configured_app_key_for_oauth_state(
        state,
        env_reader=linear_env,
    )
    if matched_key:
        return matched_key, state

    return None, state


def app_key_from_oauth_state(state: Optional[str]) -> Optional[str]:
    """Resolve the target Linear app key from the OAuth state value."""
    app_key, _nonce = _split_oauth_state(state)
    return app_key


def validate_oauth_state(state: Optional[str], *, app_key: Optional[str] = None) -> bool:
    """Validate OAuth state when a global or app-specific state is configured."""
    state_app_key, nonce = _split_oauth_state(state)
    effective_app_key = app_key or state_app_key
    state_to_compare = nonce if state_app_key and nonce is not None else state
    if effective_app_key:
        expected_state = linear_app_env(effective_app_key, "OAUTH_STATE")
    else:
        expected_state = linear_env("LINEAR_OAUTH_STATE")
    if not expected_state:
        return False
    if not state_to_compare or not hmac.compare_digest(state_to_compare, expected_state):
        if effective_app_key:
            raise LinearOAuthError(
                f"OAuth state did not match {app_env_prefix(effective_app_key)}_OAUTH_STATE"
            )
        raise LinearOAuthError("OAuth state did not match LINEAR_OAUTH_STATE")
    return True


def exchange_oauth_code(code: str, *, app_key: Optional[str] = None) -> Dict[str, Any]:
    """Exchange a Linear OAuth authorization code for app actor tokens."""
    client_id = required_linear_app_env(app_key, "CLIENT_ID")
    client_secret = required_linear_app_env(app_key, "CLIENT_SECRET")
    redirect_uri = required_linear_app_env(app_key, "OAUTH_REDIRECT_URI")

    try:
        response = requests.post(
            LINEAR_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise LinearOAuthError(f"Linear OAuth token exchange failed: {exc}") from exc

    if response.status_code >= 400:
        raise LinearOAuthError(f"Linear OAuth token exchange failed: {response.text}")

    return response.json()


def fetch_viewer(access_token: str) -> Dict[str, Any]:
    """Fetch the installed Linear app user's viewer identity."""
    try:
        response = requests.post(
            LINEAR_GRAPHQL_URL,
            json={"query": "query Me { viewer { id name } }"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise LinearOAuthError(f"Linear viewer lookup failed: {exc}") from exc

    if response.status_code >= 400:
        raise LinearOAuthError(f"Linear viewer lookup failed: {response.text}")

    payload = response.json()
    if payload.get("errors"):
        raise LinearOAuthError(f"Linear viewer lookup returned errors: {payload['errors']}")

    viewer = payload.get("data", {}).get("viewer")
    if not isinstance(viewer, dict) or not viewer.get("id"):
        raise LinearOAuthError("Linear viewer lookup did not return an app user id")
    return viewer


def linear_graphql(
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    *,
    access_token: Optional[str] = None,
    app_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Call Linear GraphQL with the installed app actor token."""
    token = access_token or required_linear_app_env(app_key, "ACCESS_TOKEN")
    try:
        response = requests.post(
            LINEAR_GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise LinearAppError(f"Linear GraphQL request failed: {exc}") from exc

    if response.status_code >= 400:
        raise LinearAppError(f"Linear GraphQL request failed: {response.text}")

    payload = response.json()
    if payload.get("errors"):
        raise LinearAppError(f"Linear GraphQL returned errors: {payload['errors']}")
    return payload


def install_linear_app(code: str, state: Optional[str]) -> Dict[str, Any]:
    """Complete Linear OAuth app installation and persist the resulting identity."""
    app_key = app_key_from_oauth_state(state)
    state_verified = validate_oauth_state(state, app_key=app_key)
    token_payload = exchange_oauth_code(code, app_key=app_key)
    access_token = token_payload.get("access_token")
    if not access_token:
        raise LinearOAuthError("Linear OAuth token response did not include access_token")

    viewer = fetch_viewer(access_token)

    token_expires_at = None
    if token_payload.get("expires_in") is not None:
        token_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(token_payload["expires_in"]))
        ).isoformat()

    linear_provider.persist_linear_oauth_install(
        app_key=app_key,
        access_token=access_token,
        refresh_token=token_payload.get("refresh_token"),
        token_expires_at=token_expires_at,
        app_user_id=str(viewer["id"]),
        app_user_name=str(viewer["name"]) if viewer.get("name") else None,
    )

    return {
        "app_key": app_key,
        "viewer": viewer,
        "token_type": token_payload.get("token_type"),
        "expires_in": token_payload.get("expires_in"),
        "state_verified": state_verified,
    }


def public_cao_url() -> Optional[str]:
    """Return the public CAO URL used for Linear callbacks, if configured."""
    config = linear_provider.load_linear_provider_config(allow_legacy_env=False)
    if config is not None and config.public_url:
        return config.public_url.rstrip("/")

    explicit_url = linear_env("LINEAR_CAO_PUBLIC_URL")
    if explicit_url:
        return explicit_url.rstrip("/")

    redirect_uri = linear_env("LINEAR_OAUTH_REDIRECT_URI")
    if not redirect_uri:
        return None
    parsed = urlsplit(redirect_uri)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def update_agent_session_external_url(
    agent_session_id: str,
    terminal_id: str,
    *,
    app_key: Optional[str] = None,
) -> bool:
    """Attach a CAO URL to a Linear AgentSession for smoke-test visibility."""
    base_url = public_cao_url()
    if not base_url:
        return False

    linear_graphql(
        """
        mutation AgentSessionUpdate($agentSessionId: String!, $input: AgentSessionUpdateInput!) {
          agentSessionUpdate(id: $agentSessionId, input: $input) {
            success
          }
        }
        """,
        {
            "agentSessionId": agent_session_id,
            "input": {
                "externalUrls": [
                    {
                        "label": "Open CAO",
                        "url": f"{base_url}/terminals/{terminal_id}",
                    }
                ]
            },
        },
        app_key=app_key,
    )
    return True


def get_issue(issue_id: str) -> Dict[str, Any]:
    """Fetch the Linear issue fields needed by the smoke agent-session flow."""
    payload = linear_graphql(
        """
        query Issue($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            url
          }
        }
        """,
        {"id": issue_id},
    )
    issue = payload.get("data", {}).get("issue")
    if not isinstance(issue, dict) or not issue.get("id"):
        raise LinearAppError(f"Linear issue not found: {issue_id}")
    return issue


def create_agent_session_on_issue(
    issue_id: str,
    *,
    external_urls: Optional[list[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Create a real Linear AgentSession on an issue for smoke testing."""
    input_data: Dict[str, Any] = {"issueId": issue_id}
    if external_urls:
        input_data["externalUrls"] = external_urls

    payload = linear_graphql(
        """
        mutation AgentSessionCreateOnIssue($input: AgentSessionCreateOnIssue!) {
          agentSessionCreateOnIssue(input: $input) {
            success
            agentSession {
              id
              url
              issue {
                id
                identifier
                title
                url
              }
            }
          }
        }
        """,
        {"input": input_data},
    )
    agent_session = payload.get("data", {}).get("agentSessionCreateOnIssue", {}).get("agentSession")
    if not isinstance(agent_session, dict) or not agent_session.get("id"):
        raise LinearAppError("Linear did not return an AgentSession")
    return agent_session


def create_agent_activity(
    agent_session_id: str,
    content: Dict[str, Any],
    *,
    app_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit a Linear Agent Activity for the current session."""
    payload = linear_graphql(
        """
        mutation AgentActivityCreate($input: AgentActivityCreateInput!) {
          agentActivityCreate(input: $input) {
            success
            agentActivity {
              id
            }
          }
        }
        """,
        {
            "input": {
                "agentSessionId": agent_session_id,
                "content": content,
            }
        },
        app_key=app_key,
    )
    agent_activity = payload.get("data", {}).get("agentActivityCreate", {}).get("agentActivity")
    if not isinstance(agent_activity, dict) or not agent_activity.get("id"):
        raise LinearAppError("Linear did not return an AgentActivity")
    return agent_activity


def get_agent_session(agent_session_id: str) -> Dict[str, Any]:
    """Fetch Linear AgentSession fields used by the presence provider."""
    payload = linear_graphql(
        """
        query AgentSession($id: String!) {
          agentSession(id: $id) {
            id
            url
            context
            status
            issue {
              id
              identifier
              title
              url
              state {
                name
              }
            }
          }
        }
        """,
        {"id": agent_session_id},
    )
    agent_session = payload.get("data", {}).get("agentSession")
    if not isinstance(agent_session, dict) or not agent_session.get("id"):
        raise LinearAppError(f"Linear AgentSession not found: {agent_session_id}")
    return agent_session


def list_agent_session_activities(agent_session_id: str) -> list[Dict[str, Any]]:
    """Fetch the first page of Linear AgentActivities for an AgentSession."""
    payload = linear_graphql(
        """
        query AgentSessionActivities($id: String!) {
          agentSession(id: $id) {
            id
            activities(first: 50) {
              nodes {
                id
                signal
                content {
                  ... on AgentActivityPromptContent {
                    type
                    body
                  }
                  ... on AgentActivityThoughtContent {
                    type
                    body
                  }
                  ... on AgentActivityResponseContent {
                    type
                    body
                  }
                  ... on AgentActivityElicitationContent {
                    type
                    body
                  }
                  ... on AgentActivityErrorContent {
                    type
                    body
                  }
                  ... on AgentActivityActionContent {
                    type
                    action
                    parameter
                    result
                  }
                }
              }
            }
          }
        }
        """,
        {"id": agent_session_id},
    )
    agent_session = payload.get("data", {}).get("agentSession")
    if not isinstance(agent_session, dict) or not agent_session.get("id"):
        raise LinearAppError(f"Linear AgentSession not found: {agent_session_id}")

    activities = agent_session.get("activities")
    nodes = activities.get("nodes") if isinstance(activities, dict) else None
    if not isinstance(nodes, list):
        return []
    return [node for node in nodes if isinstance(node, dict)]


def _verify_webhook_with_secret(
    raw_body: bytes,
    signature: Optional[str],
    payload: Dict[str, Any],
    secret: str,
) -> bool:
    if not signature:
        raise LinearWebhookVerificationError("Missing Linear-Signature header")

    expected_signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return False

    timestamp = payload.get("webhookTimestamp")
    if timestamp is None:
        raise LinearWebhookVerificationError("Missing webhookTimestamp")
    try:
        timestamp_ms = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise LinearWebhookVerificationError("Invalid webhookTimestamp") from exc

    if abs(int(time.time() * 1000) - timestamp_ms) > WEBHOOK_TIMESTAMP_TOLERANCE_MS:
        raise LinearWebhookVerificationError("Stale Linear webhook timestamp")

    return True


def verify_webhook_source(
    raw_body: bytes,
    signature: Optional[str],
    payload: Dict[str, Any],
) -> LinearWebhookVerification:
    """Verify a Linear webhook and identify the configured app key when possible."""
    try:
        presences = list(linear_provider.webhook_secret_presences(env_reader=linear_env))
    except linear_provider.LinearWorkspaceProviderConfigError as exc:
        raise LinearWebhookVerificationError(str(exc)) from exc

    if not presences:
        logger.warning("LINEAR_WEBHOOK_SECRET is not configured; accepting webhook unverified")
        return LinearWebhookVerification(verified=False, app_key=None)

    if not signature:
        raise LinearWebhookVerificationError("Missing Linear-Signature header")

    for presence in presences:
        if presence.webhook_secret and _verify_webhook_with_secret(
            raw_body,
            signature,
            payload,
            presence.webhook_secret,
        ):
            return LinearWebhookVerification(
                verified=True,
                app_key=presence.app_key,
                agent_id=presence.agent_id,
                app_user_id=presence.app_user_id,
                app_user_name=presence.app_user_name,
            )

    raise LinearWebhookVerificationError("Invalid Linear webhook signature")


def verify_webhook(raw_body: bytes, signature: Optional[str], payload: Dict[str, Any]) -> bool:
    """Verify a Linear webhook when a Linear webhook secret is configured."""
    return verify_webhook_source(raw_body, signature, payload).verified


def parse_webhook_payload(raw_body: bytes) -> Dict[str, Any]:
    """Parse a Linear webhook JSON payload from raw bytes."""
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LinearWebhookVerificationError("Invalid Linear webhook JSON body") from exc
    if not isinstance(payload, dict):
        raise LinearWebhookVerificationError("Linear webhook body must be a JSON object")
    return payload


def webhook_event_type(
    payload: Dict[str, Any], header_event: Optional[str] = None
) -> Optional[str]:
    """Return the Linear webhook event type from headers or body."""
    value = header_event or payload.get("type")
    return str(value) if value else None


def is_agent_session_event(payload: Dict[str, Any], header_event: Optional[str] = None) -> bool:
    """Return whether a Linear webhook payload describes an Agent Session event."""
    return webhook_event_type(payload, header_event) == "AgentSessionEvent"


def agent_session_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the AgentSession object from known Linear webhook payload shapes."""
    direct = payload.get("agentSession")
    if isinstance(direct, dict):
        return direct

    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("agentSession"), dict):
        return data["agentSession"]

    return {}


def agent_session_id_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    """Extract an AgentSession id from known Linear webhook payload shapes."""
    agent_session = agent_session_from_payload(payload)
    value = agent_session.get("id") or payload.get("agentSessionId")
    return str(value) if value else None


def agent_activity_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the AgentActivity object from known Linear webhook payload shapes."""
    direct = payload.get("agentActivity")
    if isinstance(direct, dict):
        return direct

    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("agentActivity"), dict):
        return data["agentActivity"]

    return {}


def prompt_context_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    """Extract Linear prompt context from known AgentSession payload shapes."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    agent_session = agent_session_from_payload(payload)
    value = (
        payload.get("promptContext")
        or data.get("promptContext")
        or payload.get("context")
        or data.get("context")
        or agent_session.get("promptContext")
        or agent_session.get("context")
    )
    return str(value) if value else None


def prompt_body_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    """Extract a user prompt body from known AgentActivity payload shapes."""
    activity = agent_activity_from_payload(payload)
    content = activity.get("content") if isinstance(activity.get("content"), dict) else {}
    body = activity.get("body") or content.get("body")
    return str(body) if body else None

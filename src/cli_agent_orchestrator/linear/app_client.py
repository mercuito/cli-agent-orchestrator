"""Linear OAuth, GraphQL, and webhook helpers for CAO-managed app users."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import requests

from cli_agent_orchestrator.utils.env import load_env_vars, set_env_var

logger = logging.getLogger(__name__)

LINEAR_TOKEN_URL = "https://api.linear.app/oauth/token"
LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
WEBHOOK_TIMESTAMP_TOLERANCE_MS = 60_000


class LinearAppError(Exception):
    """Base exception for Linear app integration failures."""


class LinearConfigError(LinearAppError):
    """Required Linear configuration is missing."""


class LinearOAuthError(LinearAppError):
    """Linear OAuth installation failed."""


class LinearWebhookVerificationError(LinearAppError):
    """Linear webhook signature or freshness verification failed."""


def linear_env(name: str) -> Optional[str]:
    """Read Linear config from process env first, then CAO's managed env file."""
    return os.environ.get(name) or load_env_vars().get(name)


def required_linear_env(name: str) -> str:
    value = linear_env(name)
    if not value:
        raise LinearConfigError(f"{name} is required")
    return value


def validate_oauth_state(state: Optional[str]) -> bool:
    """Validate OAuth state when LINEAR_OAUTH_STATE is configured."""
    expected_state = linear_env("LINEAR_OAUTH_STATE")
    if not expected_state:
        return False
    if not state or not hmac.compare_digest(state, expected_state):
        raise LinearOAuthError("OAuth state did not match LINEAR_OAUTH_STATE")
    return True


def exchange_oauth_code(code: str) -> Dict[str, Any]:
    """Exchange a Linear OAuth authorization code for app actor tokens."""
    client_id = required_linear_env("LINEAR_CLIENT_ID")
    client_secret = required_linear_env("LINEAR_CLIENT_SECRET")
    redirect_uri = required_linear_env("LINEAR_OAUTH_REDIRECT_URI")

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
) -> Dict[str, Any]:
    """Call Linear GraphQL with the installed app actor token."""
    token = access_token or required_linear_env("LINEAR_ACCESS_TOKEN")
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
    state_verified = validate_oauth_state(state)
    token_payload = exchange_oauth_code(code)
    access_token = token_payload.get("access_token")
    if not access_token:
        raise LinearOAuthError("Linear OAuth token response did not include access_token")

    viewer = fetch_viewer(access_token)

    set_env_var("LINEAR_ACCESS_TOKEN", access_token)
    if token_payload.get("refresh_token"):
        set_env_var("LINEAR_REFRESH_TOKEN", token_payload["refresh_token"])
    if token_payload.get("expires_in") is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_payload["expires_in"]))
        set_env_var("LINEAR_TOKEN_EXPIRES_AT", expires_at.isoformat())

    set_env_var("LINEAR_APP_USER_ID", str(viewer["id"]))
    if viewer.get("name"):
        set_env_var("LINEAR_APP_USER_NAME", str(viewer["name"]))

    return {
        "viewer": viewer,
        "token_type": token_payload.get("token_type"),
        "expires_in": token_payload.get("expires_in"),
        "state_verified": state_verified,
    }


def public_cao_url() -> Optional[str]:
    """Return the public CAO URL used for Linear callbacks, if configured."""
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


def update_agent_session_external_url(agent_session_id: str, terminal_id: str) -> bool:
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
    agent_session = payload.get("data", {}).get("agentSessionCreateOnIssue", {}).get(
        "agentSession"
    )
    if not isinstance(agent_session, dict) or not agent_session.get("id"):
        raise LinearAppError("Linear did not return an AgentSession")
    return agent_session


def create_agent_activity(agent_session_id: str, content: Dict[str, Any]) -> Dict[str, Any]:
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


def verify_webhook(raw_body: bytes, signature: Optional[str], payload: Dict[str, Any]) -> bool:
    """Verify a Linear webhook when LINEAR_WEBHOOK_SECRET is configured."""
    secret = linear_env("LINEAR_WEBHOOK_SECRET")
    if not secret:
        logger.warning("LINEAR_WEBHOOK_SECRET is not configured; accepting webhook unverified")
        return False

    if not signature:
        raise LinearWebhookVerificationError("Missing Linear-Signature header")

    expected_signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise LinearWebhookVerificationError("Invalid Linear webhook signature")

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


def parse_webhook_payload(raw_body: bytes) -> Dict[str, Any]:
    """Parse a Linear webhook JSON payload from raw bytes."""
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LinearWebhookVerificationError("Invalid Linear webhook JSON body") from exc
    if not isinstance(payload, dict):
        raise LinearWebhookVerificationError("Linear webhook body must be a JSON object")
    return payload


def webhook_event_type(payload: Dict[str, Any], header_event: Optional[str] = None) -> Optional[str]:
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

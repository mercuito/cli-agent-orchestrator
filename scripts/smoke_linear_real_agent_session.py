#!/usr/bin/env python3
"""Create a real Linear AgentSession on an issue and route it into CAO."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
import urllib.request
from typing import Any, Dict

from cli_agent_orchestrator.linear import app_client, runtime


def _terminal_url(terminal_id: str) -> str | None:
    base_url = app_client.public_cao_url()
    if not base_url:
        return None
    return f"{base_url}/terminals/{terminal_id}"


def _prompt_context(issue: Dict[str, Any], message: str) -> str:
    return "\n".join(
        [
            f'<issue identifier="{issue["identifier"]}">',
            f"<title>{issue['title']}</title>",
            f"<url>{issue['url']}</url>",
            "</issue>",
            "",
            message,
        ]
    )


def _post_signed_webhook(url: str, payload: Dict[str, Any]) -> str:
    secret = app_client.linear_env("LINEAR_WEBHOOK_SECRET")
    if not secret:
        raise SystemExit("LINEAR_WEBHOOK_SECRET is required to route through CAO")

    payload["webhookTimestamp"] = int(time.time() * 1000)
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        url,
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "Linear-Signature": signature,
            "Linear-Delivery": f"real-session-smoke-{payload['data']['agentSession']['id']}",
            "Linear-Event": "AgentSessionEvent",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("issue", help="Linear issue identifier or UUID, for example CAO-14.")
    parser.add_argument(
        "--webhook-url",
        default="http://127.0.0.1:9889/linear/webhooks/agent",
        help="Local CAO webhook endpoint used to route the real session into a terminal.",
    )
    parser.add_argument(
        "--message",
        default="Proactive CAO smoke test: create a real Linear Agent Session and route it into the Discovery Partner terminal.",
    )
    parser.add_argument(
        "--response",
        default="Smoke test acknowledged from CAO. The Discovery Partner terminal received this real Linear Agent Session.",
        help="Response activity to emit into Linear after routing the session.",
    )
    args = parser.parse_args()

    issue = app_client.get_issue(args.issue)
    terminal = runtime.ensure_discovery_terminal()
    terminal_id = terminal["id"]

    external_urls = []
    terminal_url = _terminal_url(terminal_id)
    if terminal_url:
        external_urls.append({"label": "Open CAO", "url": terminal_url})

    agent_session = app_client.create_agent_session_on_issue(
        issue["id"],
        external_urls=external_urls,
    )
    payload = {
        "type": "AgentSessionEvent",
        "action": "created",
        "data": {
            "agentSession": {
                "id": agent_session["id"],
                "issue": agent_session.get("issue") or issue,
                "promptContext": _prompt_context(issue, args.message),
            },
            "agentActivity": {
                "content": {
                    "body": "Please acknowledge this real Linear Agent Session smoke test."
                }
            },
        },
    }
    webhook_response = _post_signed_webhook(args.webhook_url, payload)
    response_activity = app_client.create_agent_activity(
        agent_session["id"],
        {
            "type": "response",
            "body": args.response,
        },
    )

    print(f"issue: {issue['identifier']} {issue['url']}")
    print(f"agent_session_id: {agent_session['id']}")
    if agent_session.get("url"):
        print(f"agent_session_url: {agent_session['url']}")
    if terminal_url:
        print(f"terminal_url: {terminal_url}")
    print(f"terminal_id: {terminal_id}")
    print(f"response_activity_id: {response_activity['id']}")
    print(f"webhook_response: {webhook_response}")


if __name__ == "__main__":
    main()

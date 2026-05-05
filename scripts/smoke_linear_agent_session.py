#!/usr/bin/env python3
"""Post a signed Linear AgentSessionEvent smoke payload to a local CAO server."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
import uuid
import urllib.request

from cli_agent_orchestrator.linear import app_client


def _build_payload(agent_session_id: str, message: str) -> bytes:
    return json.dumps(
        {
            "type": "AgentSessionEvent",
            "action": "created",
            "webhookTimestamp": int(time.time() * 1000),
            "data": {
                "agentSession": {
                    "id": agent_session_id,
                    "promptContext": message,
                },
                "agentActivity": {
                    "content": {
                        "body": "Please acknowledge that this smoke event reached Discovery Partner."
                    }
                },
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:9889/linear/webhooks/agent",
        help="CAO Linear webhook endpoint.",
    )
    parser.add_argument("--agent-session-id", default=str(uuid.uuid4()))
    parser.add_argument(
        "--message",
        default="Local CAO smoke test: route a signed Linear AgentSessionEvent into a terminal.",
    )
    args = parser.parse_args()

    secret = app_client.linear_env("LINEAR_WEBHOOK_SECRET")
    if not secret:
        raise SystemExit("LINEAR_WEBHOOK_SECRET is required for the signed smoke test")

    raw_body = _build_payload(args.agent_session_id, args.message)
    signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        args.url,
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "Linear-Signature": signature,
            "Linear-Delivery": f"local-smoke-{args.agent_session_id}",
            "Linear-Event": "AgentSessionEvent",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.status)
        print(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()

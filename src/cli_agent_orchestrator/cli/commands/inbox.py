"""Inbox commands for CLI Agent Orchestrator.

These commands allow an orchestrator (or human) to retrieve inbox messages via the HTTP API
without requiring additional MCP tools.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import click
import requests

from cli_agent_orchestrator.constants import API_BASE_URL


def _truncate(text: str, limit: int = 4096) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def _handle_http_error(exc: requests.HTTPError) -> click.ClickException:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", "unknown")
    body = getattr(response, "text", "") or str(exc)
    body = _truncate(body.strip())
    message = f"cao-server error: {status_code}"
    if body:
        message += f" {body}"
    return click.ClickException(message)


def _get_json(path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        response = requests.get(f"{API_BASE_URL}{path}", params=params)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        raise _handle_http_error(e)
    except requests.RequestException as e:
        raise click.ClickException(f"Failed to connect to cao-server: {e}")


@click.group()
def inbox() -> None:
    """Read inbox messages for CAO terminals via cao-server."""


@inbox.command("list")
@click.argument("terminal_id")
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(["pending", "delivered", "failed"], case_sensitive=False),
    default=None,
    help="Filter messages by status",
)
@click.option("--limit", type=int, default=10, show_default=True, help="Maximum messages to fetch")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def list_inbox_messages(
    terminal_id: str, status_filter: Optional[str], limit: int, json_output: bool
) -> None:
    """List inbox messages for a terminal."""
    params: Dict[str, Any] = {"limit": limit}
    if status_filter:
        params["status"] = status_filter.lower()

    messages: List[Dict[str, Any]] = _get_json(
        f"/terminals/{terminal_id}/inbox/messages", params=params
    )

    if json_output:
        click.echo(
            json.dumps(
                {"terminal_id": terminal_id, "messages": messages},
                indent=2,
                sort_keys=True,
            )
        )
        return

    for msg in messages:
        created_at = msg.get("created_at") or ""
        status = msg.get("status") or ""
        sender = msg.get("sender_id") or ""
        body = msg.get("message") or ""
        click.echo(f"{created_at} [{status}] from={sender} {body}")


"""``cao baton`` commands for operator baton inspection and recovery."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import click
import requests

from cli_agent_orchestrator.constants import API_BASE_URL
from cli_agent_orchestrator.models.baton import BatonStatus


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


def _connection_error(exc: requests.RequestException) -> click.ClickException:
    return click.ClickException(f"Failed to connect to cao-server: {exc}")


def _get_json(path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        response = requests.get(f"{API_BASE_URL}{path}", params=params)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        raise _handle_http_error(e)
    except requests.RequestException as e:
        raise _connection_error(e)


def _post_json(path: str, *, body: Optional[Dict[str, Any]] = None) -> Any:
    try:
        response = requests.post(f"{API_BASE_URL}{path}", json=body)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        raise _handle_http_error(e)
    except requests.RequestException as e:
        raise _connection_error(e)


def _status_choices() -> List[str]:
    return [status.value for status in BatonStatus]


def _format_baton_line(baton: Dict[str, Any]) -> str:
    holder = baton.get("current_holder_id") or "-"
    expected = baton.get("expected_next_action") or "-"
    return (
        f"{baton['id']} [{baton['status']}] holder={holder} "
        f"originator={baton['originator_id']} updated={baton['updated_at']} "
        f"next={expected}"
    )


def _format_baton_detail(baton: Dict[str, Any]) -> str:
    stack = baton.get("return_stack") or []
    return "\n".join(
        [
            f"id: {baton['id']}",
            f"title: {baton['title']}",
            f"status: {baton['status']}",
            f"current_holder_id: {baton.get('current_holder_id') or '-'}",
            f"originator_id: {baton['originator_id']}",
            f"return_stack: {', '.join(stack) if stack else '-'}",
            f"expected_next_action: {baton.get('expected_next_action') or '-'}",
            f"created_at: {baton['created_at']}",
            f"updated_at: {baton['updated_at']}",
            f"last_nudged_at: {baton.get('last_nudged_at') or '-'}",
            f"completed_at: {baton.get('completed_at') or '-'}",
        ]
    )


def _format_event_line(event: Dict[str, Any]) -> str:
    movement = ""
    if event.get("from_holder_id") or event.get("to_holder_id"):
        movement = f" {event.get('from_holder_id') or '-'} -> {event.get('to_holder_id') or '-'}"
    message = event.get("message") or ""
    suffix = f" message={message}" if message else ""
    return (
        f"{event['created_at']} {event['event_type']} actor={event['actor_id']}"
        f"{movement}{suffix}"
    )


@click.group()
def baton() -> None:
    """Inspect and recover batons via cao-server."""


@baton.command("list")
@click.option("--status", "status_filter", type=click.Choice(_status_choices()), default=None)
@click.option("--holder", "holder_id", default=None, help="Filter by current holder terminal id")
@click.option(
    "--originator", "originator_id", default=None, help="Filter by originator terminal id"
)
@click.option("--limit", type=int, default=50, show_default=True)
@click.option("--offset", type=int, default=0, show_default=True)
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def list_cmd(
    status_filter: Optional[str],
    holder_id: Optional[str],
    originator_id: Optional[str],
    limit: int,
    offset: int,
    json_output: bool,
) -> None:
    """List batons. Defaults to active batons server-side."""
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if status_filter:
        params["status"] = status_filter
    if holder_id:
        params["holder_id"] = holder_id
    if originator_id:
        params["originator_id"] = originator_id

    batons: List[Dict[str, Any]] = _get_json("/batons", params=params)
    if json_output:
        click.echo(json.dumps(batons, indent=2, sort_keys=True))
        return

    for row in batons:
        click.echo(_format_baton_line(row))


@baton.command("show")
@click.argument("baton_id")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def show_cmd(baton_id: str, json_output: bool) -> None:
    """Show one baton."""
    row = _get_json(f"/batons/{baton_id}")
    if json_output:
        click.echo(json.dumps(row, indent=2, sort_keys=True))
    else:
        click.echo(_format_baton_detail(row))


@baton.command("log")
@click.argument("baton_id")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def log_cmd(baton_id: str, json_output: bool) -> None:
    """Show a baton's audit events."""
    events: List[Dict[str, Any]] = _get_json(f"/batons/{baton_id}/events")
    if json_output:
        click.echo(json.dumps(events, indent=2, sort_keys=True))
        return

    for event in events:
        click.echo(_format_event_line(event))


@baton.command("cancel")
@click.argument("baton_id")
@click.option("--message", default=None, help="Recovery note for the audit event")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def cancel_cmd(baton_id: str, message: Optional[str], json_output: bool) -> None:
    """Cancel an unresolved baton through operator recovery."""
    row = _post_json(f"/batons/{baton_id}/cancel", body={"message": message})
    if json_output:
        click.echo(json.dumps(row, indent=2, sort_keys=True))
    else:
        click.echo(_format_baton_line(row))


@baton.command("reassign")
@click.argument("baton_id")
@click.option("--holder", "holder_id", required=True, help="New holder terminal id")
@click.option("--message", default=None, help="Recovery note for the audit event")
@click.option("--expected-next-action", default=None, help="Expectation for the new holder")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def reassign_cmd(
    baton_id: str,
    holder_id: str,
    message: Optional[str],
    expected_next_action: Optional[str],
    json_output: bool,
) -> None:
    """Reassign an unresolved baton through operator recovery."""
    body = {
        "holder_id": holder_id,
        "message": message,
        "expected_next_action": expected_next_action,
    }
    row = _post_json(f"/batons/{baton_id}/reassign", body=body)
    if json_output:
        click.echo(json.dumps(row, indent=2, sort_keys=True))
    else:
        click.echo(_format_baton_line(row))

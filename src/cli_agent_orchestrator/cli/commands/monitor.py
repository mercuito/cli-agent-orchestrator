"""``cao monitor`` commands — operator CLI for monitoring sessions.

Thin wrapper over the ``/monitoring/*`` HTTP API. Mirrors the style of
``cao inbox`` (see ``inbox.py``): ``requests`` against ``API_BASE_URL``,
``click.ClickException`` for user-facing errors, ``--json`` for structured
output on commands where that makes sense.

Intended to be called by yards procedure steps (``cao monitor start ...`` /
``cao monitor end ...``) so that conversation boundaries are orchestrated by
the workflow, not by agents.
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


def _get_text(path: str, *, params: Optional[Dict[str, Any]] = None) -> str:
    try:
        response = requests.get(f"{API_BASE_URL}{path}", params=params)
        response.raise_for_status()
        return response.text
    except requests.HTTPError as e:
        raise _handle_http_error(e)
    except requests.RequestException as e:
        raise _connection_error(e)


def _post_json(
    path: str, *, body: Optional[Dict[str, Any]] = None
) -> Optional[Any]:
    try:
        response = requests.post(f"{API_BASE_URL}{path}", json=body)
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()
    except requests.HTTPError as e:
        raise _handle_http_error(e)
    except requests.RequestException as e:
        raise _connection_error(e)


def _delete(path: str) -> Optional[Any]:
    try:
        response = requests.delete(f"{API_BASE_URL}{path}")
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()
    except requests.HTTPError as e:
        raise _handle_http_error(e)
    except requests.RequestException as e:
        raise _connection_error(e)


def _format_session_line(s: Dict[str, Any]) -> str:
    return (
        f"{s['id']} [{s['status']}] terminal={s['terminal_id']} "
        f"label={s.get('label') or '-'} started={s['started_at']}"
    )


@click.group()
def monitor() -> None:
    """Manage monitoring sessions via cao-server."""


@monitor.command("start")
@click.option("--terminal", "terminal_id", required=True, help="Monitored terminal id")
@click.option("--label", default=None, help="Human-readable label for the session")
@click.option("--json", "json_output", is_flag=True, help="Print full session JSON instead of just the id")
def start_session(
    terminal_id: str, label: Optional[str], json_output: bool
) -> None:
    """Start monitoring a terminal, or echo the existing session if already
    recording. Idempotent on the active state — calling this twice is safe
    and does not create duplicate sessions."""
    body = {
        "terminal_id": terminal_id,
        "label": label,
    }
    session = _post_json("/monitoring/sessions", body=body)

    if json_output:
        click.echo(json.dumps(session, indent=2, sort_keys=True))
    else:
        click.echo(session["id"])


@monitor.command("end")
@click.argument("session_id")
@click.option("--json", "json_output", is_flag=True)
def end_session(session_id: str, json_output: bool) -> None:
    """End an active monitoring session."""
    session = _post_json(f"/monitoring/sessions/{session_id}/end")
    if json_output:
        click.echo(json.dumps(session, indent=2, sort_keys=True))
    else:
        click.echo(_format_session_line(session))


@monitor.command("list")
@click.option("--terminal", "terminal_id", default=None, help="Filter by monitored terminal")
@click.option("--active", is_flag=True, help="Only active sessions")
@click.option("--ended", is_flag=True, help="Only ended sessions")
@click.option("--label", default=None, help="Filter by exact label match")
@click.option("--limit", type=int, default=50, show_default=True)
@click.option("--offset", type=int, default=0, show_default=True)
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def list_cmd(
    terminal_id: Optional[str],
    active: bool,
    ended: bool,
    label: Optional[str],
    limit: int,
    offset: int,
    json_output: bool,
) -> None:
    """List monitoring sessions."""
    if active and ended:
        raise click.UsageError("--active and --ended are mutually exclusive")

    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if terminal_id:
        params["terminal_id"] = terminal_id
    if active:
        params["status"] = "active"
    elif ended:
        params["status"] = "ended"
    if label:
        params["label"] = label

    sessions: List[Dict[str, Any]] = _get_json("/monitoring/sessions", params=params)

    if json_output:
        click.echo(json.dumps(sessions, indent=2, sort_keys=True))
        return

    for s in sessions:
        click.echo(_format_session_line(s))


@monitor.command("show")
@click.argument("session_id")
@click.option("--json", "json_output", is_flag=True)
def show_cmd(session_id: str, json_output: bool) -> None:
    """Show a single monitoring session."""
    session = _get_json(f"/monitoring/sessions/{session_id}")
    if json_output:
        click.echo(json.dumps(session, indent=2, sort_keys=True))
    else:
        click.echo(_format_session_line(session))


@monitor.command("log")
@click.argument("session_id")
@click.option(
    "--format",
    "format_choice",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    show_default=True,
    help="Artifact format",
)
@click.option(
    "--peer",
    "peers",
    multiple=True,
    help="Filter to messages involving a peer (repeatable; sender OR receiver).",
)
@click.option(
    "--since",
    default=None,
    help="ISO datetime — only include messages at or after this time (narrows within session window).",
)
@click.option(
    "--until",
    default=None,
    help="ISO datetime — only include messages at or before this time (narrows within session window).",
)
def log_cmd(
    session_id: str,
    format_choice: str,
    peers: tuple,
    since: Optional[str],
    until: Optional[str],
) -> None:
    """Fetch and print a session's log artifact (markdown by default).

    Filters apply at query time — sessions record everything, and
    --peer / --since / --until slice the recording without altering it.
    Running the same command with different filters yields different
    artifacts from one capture.
    """
    params: Dict[str, Any] = {"format": format_choice}
    if peers:
        params["peer"] = list(peers)
    if since:
        params["started_after"] = since
    if until:
        params["started_before"] = until

    if format_choice == "json":
        payload = _get_json(
            f"/monitoring/sessions/{session_id}/log", params=params
        )
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        body = _get_text(
            f"/monitoring/sessions/{session_id}/log", params=params
        )
        click.echo(body, nl=False)


@monitor.command("delete")
@click.argument("session_id")
def delete_cmd(session_id: str) -> None:
    """Delete a monitoring session (messages untouched)."""
    _delete(f"/monitoring/sessions/{session_id}")
    click.echo(f"Deleted {session_id}")

"""Terminal introspection commands for CLI Agent Orchestrator.

These commands are thin wrappers over the cao-server HTTP API. They provide a stable CLI surface
that orchestrators (and humans) can use without expanding MCP tool count.
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


def _post_json(path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        response = requests.post(f"{API_BASE_URL}{path}", params=params)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        raise _handle_http_error(e)
    except requests.RequestException as e:
        raise click.ClickException(f"Failed to connect to cao-server: {e}")


@click.group()
def terminals() -> None:
    """Inspect and control CAO terminals via cao-server."""


@terminals.command("get")
@click.argument("terminal_id")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def get_terminal(terminal_id: str, json_output: bool) -> None:
    """Get terminal metadata."""
    terminal: Dict[str, Any] = _get_json(f"/terminals/{terminal_id}")

    if json_output:
        click.echo(json.dumps(terminal, indent=2, sort_keys=True))
        return

    click.echo(
        f"id={terminal.get('id')} "
        f"status={terminal.get('status')} "
        f"provider={terminal.get('provider')} "
        f"session={terminal.get('session_name')} "
        f"agent_profile={terminal.get('agent_profile')}"
    )


@terminals.command("output")
@click.argument("terminal_id")
@click.option(
    "--mode",
    type=click.Choice(["full", "last"], case_sensitive=False),
    default="full",
    show_default=True,
    help="Output mode (full transcript or last assistant message)",
)
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def get_terminal_output(terminal_id: str, mode: str, json_output: bool) -> None:
    """Get terminal output."""
    data: Dict[str, Any] = _get_json(f"/terminals/{terminal_id}/output", params={"mode": mode})
    output = str(data.get("output") or "")

    if json_output:
        click.echo(
            json.dumps(
                {"terminal_id": terminal_id, "mode": mode.lower(), "output": output},
                indent=2,
                sort_keys=True,
            )
        )
        return

    # Print output only for easy piping.
    click.echo(output, nl=not output.endswith("\n"))


@terminals.command("exit")
@click.argument("terminal_id")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def exit_terminal(terminal_id: str, json_output: bool) -> None:
    """Send provider-specific exit command to a terminal."""
    result: Dict[str, Any] = _post_json(f"/terminals/{terminal_id}/exit")
    success = bool(result.get("success"))

    if json_output:
        click.echo(json.dumps({"terminal_id": terminal_id, "success": success}, indent=2))
        return

    if success:
        click.echo(f"✓ exit sent to {terminal_id}")
    else:
        raise click.ClickException(f"Failed to exit terminal {terminal_id}")


@terminals.command("list")
@click.option("--session", "session_name", required=True, help="Session name to list terminals for")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def list_terminals(session_name: str, json_output: bool) -> None:
    """List terminals in a session."""
    terminals_in_session: List[Dict[str, Any]] = _get_json(f"/sessions/{session_name}/terminals")

    if json_output:
        click.echo(
            json.dumps(
                {"session_name": session_name, "terminals": terminals_in_session},
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return

    click.echo(f"{'ID':<10} {'Window':<25} {'Provider':<12} {'Agent':<18} {'Last Active'}")
    click.echo("-" * 90)
    for t in terminals_in_session:
        click.echo(
            f"{t.get('id', ''):<10} "
            f"{t.get('tmux_window', ''):<25} "
            f"{t.get('provider', ''):<12} "
            f"{(t.get('agent_profile') or ''):<18} "
            f"{t.get('last_active', '')}"
        )


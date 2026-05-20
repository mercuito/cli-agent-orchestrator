"""Durable agent management CLI."""

from __future__ import annotations

import json
import os
import subprocess

import click

from cli_agent_orchestrator import agent as agent_config
from cli_agent_orchestrator.agent import (
    AGENT_CONFIG_FILENAME,
    Agent,
    load_agent,
    validate_agent_dir,
    write_agent,
)
from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.mcp_server.server import built_in_cao_tool_names
from cli_agent_orchestrator.runtime.agent import AgentRuntimeHandle
from cli_agent_orchestrator.services import terminal_service
from cli_agent_orchestrator.services.agent_manager import default_agent_manager
from cli_agent_orchestrator.services.tool_service import tool_service_for_loaded_agent


@click.group(name="agent")
def agent_command() -> None:
    """Manage durable CAO agents."""


@agent_command.command("list")
def list_agents() -> None:
    for status in default_agent_manager().list_statuses():
        state = "running" if status.active else "stopped"
        terminal = f" {status.active_terminal_id}" if status.active_terminal_id else ""
        team = status.workspace_team_id or "none"
        workspace = status.derived_workspace_id or "default"
        click.echo(
            f"{status.agent_id}\t{status.cli_provider}\t{state}\t"
            f"team={team}\tworkspace={workspace}{terminal}"
        )


@agent_command.command("show")
@click.argument("agent_id")
def show_agent(agent_id: str) -> None:
    agent = load_agent(agent_id)
    status = default_agent_manager().status_for_agent(agent_id)
    click.echo(f"status: {'running' if status.active else 'stopped'}")
    if status.active_terminal_id:
        click.echo(f"terminal_id: {status.active_terminal_id}")
    click.echo(f"workspace_team: {status.workspace_team_id or 'none'}")
    click.echo(f"workspace: {status.derived_workspace_id or 'default'}")
    tool_access = tool_service_for_loaded_agent(
        agent,
        fallback_agent_id=agent.id,
        cli_provider=agent.cli_provider,
    ).tools_for_agent(agent.id, built_in_tool_names=built_in_cao_tool_names())
    click.echo("\neffective_tool_access:")
    click.echo(f"registered_tools: {json.dumps(list(tool_access.registered_tools))}")
    click.echo(f"allowed_tools: {json.dumps(list(tool_access.allowed_tools))}")
    click.echo(
        "runtime_capabilities: "
        f"{json.dumps(list(tool_access.runtime_capabilities))}"
    )
    click.echo(
        "materialized_mcp_servers: "
        f"{json.dumps(tool_access.materialized_mcp_servers, sort_keys=True)}"
    )
    if tool_access.inactive_local_grants:
        click.echo(
            "inactive_local_grants: "
            f"{json.dumps(tool_access.inactive_local_grants, sort_keys=True)}"
        )
    for diagnostic in tool_access.diagnostics:
        click.echo(f"diagnostic: {diagnostic.code} {diagnostic.message}")
    config_path = agent_config.AGENTS_ROOT / agent.id / AGENT_CONFIG_FILENAME
    click.echo("\nagent.toml:")
    click.echo(config_path.read_text())
    click.echo("prompt.md:")
    click.echo(agent.prompt)


@agent_command.command("create")
@click.argument("agent_id")
@click.option("--provider", default=ProviderType.CODEX.value, show_default=True)
@click.option("--workdir", default=lambda: os.getcwd(), show_default="current directory")
@click.option("--team", default=None, help="Workspace team membership; omit for standalone.")
def create_agent(agent_id: str, provider: str, workdir: str, team: str | None) -> None:
    agent = Agent(
        id=agent_id,
        display_name=agent_id.replace("_", " ").title(),
        cli_provider=provider,
        workdir=workdir,
        session_name=agent_id,
        prompt="# Agent\n",
        workspace=agent_config.AgentWorkspaceConfig(team=team) if team else agent_config.AgentWorkspaceConfig(),
    )
    write_agent(agent)
    click.echo(f"created {agent_id}")


@agent_command.command("edit")
@click.argument("agent_id")
def edit_agent(agent_id: str) -> None:
    agent = load_agent(agent_id)
    path = agent_config.AGENTS_ROOT / agent.id / AGENT_CONFIG_FILENAME
    original_config = path.read_text()
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(path)], check=True)
    errors = validate_agent_dir(path.parent)
    if errors:
        path.write_text(original_config)
        raise click.ClickException("\n".join(errors))
    click.echo(f"validated {agent_id}")


@agent_command.command("delete")
@click.argument("agent_id")
@click.option("--confirm", is_flag=True)
def delete_agent(agent_id: str, confirm: bool) -> None:
    if not confirm:
        raise click.ClickException("--confirm is required")
    status = default_agent_manager().status_for_agent(agent_id)
    if status.active_terminal_id:
        raise click.ClickException(f"agent is running in terminal {status.active_terminal_id}")

    target = agent_config.AGENTS_ROOT / load_agent(agent_id).id
    import shutil

    shutil.rmtree(target)
    click.echo(f"deleted {agent_id}")


@agent_command.command("start")
@click.argument("agent_id")
def start_agent(agent_id: str) -> None:
    status = default_agent_manager().status_for_agent(agent_id)
    if status.active_terminal_id:
        raise click.ClickException(f"agent already running in terminal {status.active_terminal_id}")
    terminal = AgentRuntimeHandle(load_agent(agent_id)).ensure_started()
    click.echo(f"started {agent_id} in terminal {terminal.id}")
    if os.isatty(0):
        subprocess.run(["tmux", "attach-session", "-t", terminal.session_name], check=False)


@agent_command.command("stop")
@click.argument("agent_id")
def stop_agent(agent_id: str) -> None:
    status = default_agent_manager().status_for_agent(agent_id)
    if status.active_terminal_id:
        terminal_service.delete_terminal(status.active_terminal_id, require_window_killed=True)
    click.echo(f"stopped {agent_id}")

"""Durable agent management CLI."""

from __future__ import annotations

import os
import subprocess

import click

from cli_agent_orchestrator.agent import (
    AGENT_CONFIG_FILENAME,
    AGENTS_ROOT,
    Agent,
    load_agent,
    validate_agent_dir,
    write_agent,
)
from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.runtime.agent import AgentRuntimeHandle
from cli_agent_orchestrator.services.agent_manager import default_agent_manager
from cli_agent_orchestrator.services import terminal_service


@click.group(name="agent")
def agent_command() -> None:
    """Manage durable CAO agents."""


@agent_command.command("list")
def list_agents() -> None:
    for status in default_agent_manager().list_statuses():
        state = "running" if status.active else "stopped"
        terminal = f" {status.active_terminal_id}" if status.active_terminal_id else ""
        click.echo(f"{status.agent_id}\t{status.cli_provider}\t{state}{terminal}")


@agent_command.command("show")
@click.argument("agent_id")
def show_agent(agent_id: str) -> None:
    agent = load_agent(agent_id)
    status = default_agent_manager().status_for_agent(agent_id)
    click.echo(f"status: {'running' if status.active else 'stopped'}")
    if status.active_terminal_id:
        click.echo(f"terminal_id: {status.active_terminal_id}")
    config_path = AGENTS_ROOT / agent.id / AGENT_CONFIG_FILENAME
    click.echo("\nagent.toml:")
    click.echo(config_path.read_text())
    click.echo("prompt.md:")
    click.echo(agent.prompt)


@agent_command.command("create")
@click.argument("agent_id")
@click.option("--provider", default=ProviderType.CODEX.value, show_default=True)
@click.option("--workdir", default=lambda: os.getcwd(), show_default="current directory")
def create_agent(agent_id: str, provider: str, workdir: str) -> None:
    agent = Agent(
        id=agent_id,
        display_name=agent_id.replace("_", " ").title(),
        cli_provider=provider,
        workdir=workdir,
        session_name=agent_id,
        prompt="# Agent\n",
    )
    write_agent(agent)
    click.echo(f"created {agent_id}")


@agent_command.command("edit")
@click.argument("agent_id")
def edit_agent(agent_id: str) -> None:
    agent = load_agent(agent_id)
    path = AGENTS_ROOT / agent.id / AGENT_CONFIG_FILENAME
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

    target = AGENTS_ROOT / load_agent(agent_id).id
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

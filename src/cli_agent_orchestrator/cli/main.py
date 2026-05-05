"""Main CLI entry point for CLI Agent Orchestrator."""

import click

from cli_agent_orchestrator.cli.commands.baton import baton
from cli_agent_orchestrator.cli.commands.diagnostics import diagnostics
from cli_agent_orchestrator.cli.commands.env import env
from cli_agent_orchestrator.cli.commands.flow import flow
from cli_agent_orchestrator.cli.commands.inbox import inbox
from cli_agent_orchestrator.cli.commands.info import info
from cli_agent_orchestrator.cli.commands.init import init
from cli_agent_orchestrator.cli.commands.install import install
from cli_agent_orchestrator.cli.commands.launch import launch
from cli_agent_orchestrator.cli.commands.mcp_server import mcp_server
from cli_agent_orchestrator.cli.commands.monitor import monitor
from cli_agent_orchestrator.cli.commands.shutdown import shutdown
from cli_agent_orchestrator.cli.commands.skills import skills
from cli_agent_orchestrator.cli.commands.terminals import terminals
from cli_agent_orchestrator.services.baton_feature import is_baton_enabled


@click.group()
def cli():
    """CLI Agent Orchestrator."""


# Register commands
cli.add_command(launch)
cli.add_command(init)
cli.add_command(install)
cli.add_command(shutdown)
cli.add_command(flow)
cli.add_command(env)
cli.add_command(mcp_server)
cli.add_command(info)
cli.add_command(skills)
cli.add_command(diagnostics)
cli.add_command(terminals)
cli.add_command(inbox)
cli.add_command(monitor)
if is_baton_enabled():
    cli.add_command(baton)


if __name__ == "__main__":
    cli()

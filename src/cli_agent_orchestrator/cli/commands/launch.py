"""Launch command for CLI Agent Orchestrator CLI."""

import os
import subprocess

import click
import requests

from cli_agent_orchestrator.constants import DEFAULT_PROVIDER, PROVIDERS, SERVER_HOST, SERVER_PORT

# Providers that require workspace folder access
PROVIDERS_REQUIRING_WORKSPACE_ACCESS = {
    "claude_code",
    "codex",
    "copilot_cli",
    "gemini_cli",
    "kimi_cli",
    "kiro_cli",
}


@click.command()
@click.option("--agents", required=True, help="Agent profile to launch")
@click.option("--session-name", help="Name of the session (default: auto-generated)")
@click.option("--headless", is_flag=True, help="Launch in detached mode")
@click.option(
    "--provider", default=DEFAULT_PROVIDER, help=f"Provider to use (default: {DEFAULT_PROVIDER})"
)
@click.option(
    "--runtime-capability",
    "runtime_capabilities",
    multiple=True,
    help="Override profile runtimeCapabilities (e.g. execute_bash, fs_read). Repeatable.",
)
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Skip confirmation prompt (restrictions still enforced).",
)
@click.option(
    "--yolo",
    is_flag=True,
    help="[DANGEROUS] Unrestricted tool access AND skip confirmation prompts. "
    "Agent can execute ANY command including aws, rm, curl.",
)
def launch(
    agents,
    session_name,
    headless,
    provider,
    runtime_capabilities,
    auto_approve,
    yolo,
):
    """Launch cao session with specified agent profile."""
    try:
        # Validate provider
        if provider not in PROVIDERS:
            raise click.ClickException(
                f"Invalid provider '{provider}'. Available providers: {', '.join(PROVIDERS)}"
            )
        working_directory = os.path.realpath(os.getcwd())

        # Resolve runtime capabilities: --yolo > CLI override > profile > defaults.
        from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile
        from cli_agent_orchestrator.utils.tool_mapping import (
            format_tool_summary,
            resolve_runtime_capabilities,
        )

        resolved_runtime_capabilities = None
        no_runtime_capabilities_set = False
        if yolo:
            resolved_runtime_capabilities = ["*"]
        elif runtime_capabilities:
            resolved_runtime_capabilities = list(runtime_capabilities)
        else:
            # Load profile to get explicit runtime capabilities.
            try:
                profile = load_agent_profile(agents)
                mcp_server_names = list(profile.mcpServers.keys()) if profile.mcpServers else None
                no_runtime_capabilities_set = not profile.runtimeCapabilities
                resolved_runtime_capabilities = resolve_runtime_capabilities(
                    profile.runtimeCapabilities, mcp_server_names
                )
            except (FileNotFoundError, RuntimeError):
                # Profile not found — use developer-like defaults.
                no_runtime_capabilities_set = True
                resolved_runtime_capabilities = resolve_runtime_capabilities(None)

        # Confirmation / warning prompts
        if provider in PROVIDERS_REQUIRING_WORKSPACE_ACCESS:
            if yolo:
                # --yolo: warn but don't block
                click.echo(click.style("\n[WARNING] --yolo mode enabled", fg="yellow", bold=True))
                click.echo(
                    f"  Agent '{agents}' launching UNRESTRICTED on {provider}.\n"
                    f"  Agent can execute ANY command (aws, rm, curl, read credentials).\n"
                    f"  Directory: {working_directory}\n"
                )
            else:
                # Normal launch: show tool summary and confirm
                tool_summary = format_tool_summary(resolved_runtime_capabilities)

                click.echo(
                    f"\nAgent '{agents}' launching on {provider}:\n"
                    f"  Runtime capabilities: {tool_summary}\n"
                    f"  Directory: {working_directory}\n"
                )
                if no_runtime_capabilities_set:
                    click.echo(
                        "  Note: No runtimeCapabilities set — defaulting to developer-like native access.\n"
                        "  Add runtimeCapabilities to your agent profile to control native CLI access.\n"
                        "  Docs: https://github.com/awslabs/cli-agent-orchestrator/blob/main/docs/tool-restrictions.md\n"
                    )
                click.echo(
                    "  To skip this prompt next time, relaunch with --auto-approve\n"
                    "  To remove all restrictions, relaunch with --yolo\n"
                )
                if not auto_approve and not click.confirm("Proceed?", default=True):
                    raise click.ClickException("Launch cancelled by user")

        # Call API to create session
        url = f"http://{SERVER_HOST}:{SERVER_PORT}/sessions"
        params = {
            "provider": provider,
            "agent_profile": agents,
            "working_directory": working_directory,
        }
        if session_name:
            params["session_name"] = session_name
        if resolved_runtime_capabilities:
            # The server API still names this query parameter allowed_tools.
            # The value is the resolved runtime capability list.
            params["allowed_tools"] = ",".join(resolved_runtime_capabilities)

        response = requests.post(url, params=params)
        response.raise_for_status()

        terminal = response.json()

        click.echo(f"Session created: {terminal['session_name']}")
        click.echo(f"Terminal created: {terminal['name']}")

        # Attach to tmux session unless headless
        if not headless:
            subprocess.run(["tmux", "attach-session", "-t", terminal["session_name"]])

    except requests.exceptions.RequestException as e:
        raise click.ClickException(f"Failed to connect to cao-server: {str(e)}")
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))

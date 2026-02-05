"""Diagnostics command for CLI Agent Orchestrator CLI."""

from __future__ import annotations

import json
import os

import click

from cli_agent_orchestrator.diagnostics.runner import run_provider_diagnostics


@click.command()
@click.option("--provider", required=True, help="Provider to diagnose (e.g. codex)")
@click.option("--agent-profile", required=True, help="Agent profile name to use")
@click.option(
    "--mode",
    type=click.Choice(["offline", "online"], case_sensitive=False),
    default="offline",
    show_default=True,
    help="Diagnostics mode (online may incur provider costs)",
)
@click.option(
    "--allow-billing",
    is_flag=True,
    help="Required for --mode online (acknowledges provider/API costs)",
)
@click.option(
    "--working-directory",
    default=lambda: os.path.realpath(os.getcwd()),
    show_default="cwd",
    help="Working directory to trust/use for the diagnostic run",
)
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON")
def diagnostics(
    provider: str,
    agent_profile: str,
    mode: str,
    allow_billing: bool,
    working_directory: str,
    json_output: bool,
) -> None:
    """Run provider diagnostics (opt-in E2E-style preflight)."""
    try:
        result = run_provider_diagnostics(
            provider=provider,
            agent_profile=agent_profile,
            mode=mode,
            allow_billing=allow_billing,
            working_directory=working_directory,
        )

        if json_output:
            click.echo(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
        else:
            click.echo(
                f"{provider} diagnostics: {'OK' if result.ok else 'FAILED'} (mode={mode}, billing={'on' if allow_billing else 'off'})"
            )
            for step in result.steps:
                status = "OK" if step.ok else "FAIL"
                suffix = " (billable)" if step.billable else ""
                click.echo(f"- [{status}]{suffix} {step.name} ({step.duration_ms}ms)")
                if step.details and not step.ok:
                    click.echo(f"    {step.details}")

        if not result.ok:
            raise click.ClickException("Diagnostics failed")

    except ValueError as e:
        raise click.ClickException(str(e))

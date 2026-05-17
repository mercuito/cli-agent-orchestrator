"""Install command for CLI Agent Orchestrator."""

import re
import os
from pathlib import Path

import click
import frontmatter
import requests  # type: ignore[import-untyped]

from cli_agent_orchestrator.agent import Agent
from cli_agent_orchestrator.constants import (
    AGENT_CONTEXT_DIR,
    CAO_ENV_FILE,
    COPILOT_AGENTS_DIR,
    DEFAULT_PROVIDER,
    KIRO_AGENTS_DIR,
    PROVIDERS,
    Q_AGENTS_DIR,
    SKILLS_DIR,
)
from cli_agent_orchestrator.models.copilot_agent import CopilotAgentConfig
from cli_agent_orchestrator.models.kiro_agent import KiroAgentConfig
from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.models.q_agent import QAgentConfig
from cli_agent_orchestrator.utils.env import resolve_env_vars, set_env_var
from cli_agent_orchestrator.utils.skill_injection import compose_agent_prompt

EXAMPLE_AGENTS_DIR = Path(__file__).resolve().parents[4] / "examples" / "agents"


def _read_agent_source(source: str) -> tuple[str, str]:
    """Return ``(agent_name, markdown)`` for a URL, file path, or example agent."""
    if source.startswith("http://") or source.startswith("https://"):
        filename = Path(source).name
        if not filename.endswith(".md"):
            raise ValueError("URL must point to a .md file")
        response = requests.get(source)
        response.raise_for_status()
        return Path(filename).stem, response.text

    source_path = Path(source)
    if source_path.exists():
        if not source_path.suffix == ".md":
            raise ValueError("File must be a .md file")
        return source_path.stem, source_path.read_text()

    example_path = EXAMPLE_AGENTS_DIR / f"{source}.md"
    if example_path.exists():
        return source, example_path.read_text()
    raise FileNotFoundError(f"Source not found: {source}")


def _parse_env_assignment(env_assignment: str) -> tuple[str, str]:
    """Parse a ``KEY=VALUE`` env assignment for install-time injection."""
    if "=" not in env_assignment:
        raise click.BadParameter(
            f"Invalid env var '{env_assignment}'. Expected format KEY=VALUE.", param_hint="--env"
        )

    key, value = env_assignment.split("=", 1)
    if not key:
        raise click.BadParameter(
            f"Invalid env var '{env_assignment}'. Key must not be empty.", param_hint="--env"
        )
    return key, value


def _parse_agent_markdown(resolved_text: str, agent_name: str, provider: str) -> Agent:
    post = frontmatter.loads(resolved_text)
    metadata = post.metadata
    return Agent(
        id=str(metadata.get("name") or agent_name),
        display_name=str(metadata.get("display_name") or metadata.get("name") or agent_name),
        description=metadata.get("description"),
        cli_provider=provider,
        workdir=os.getcwd(),
        session_name=str(metadata.get("session_name") or metadata.get("name") or agent_name),
        prompt=post.content or str(metadata.get("prompt") or ""),
        model=metadata.get("model"),
        mcp_servers=metadata.get("mcpServers") or {},
        tools=tuple(metadata.get("tools") or ()),
        tool_aliases=metadata.get("toolAliases") or {},
        tools_settings=metadata.get("toolsSettings") or {},
        cao_tools=None if metadata.get("caoTools") is None else tuple(metadata.get("caoTools") or ()),
        runtime_capabilities=(
            None
            if metadata.get("runtimeCapabilities") is None
            else tuple(metadata.get("runtimeCapabilities") or ())
        ),
        hooks=metadata.get("hooks") or {},
    )


@click.command()
@click.argument("agent_source")
@click.option(
    "--provider",
    type=click.Choice(PROVIDERS),
    default=DEFAULT_PROVIDER,
    help=f"Provider to use (default: {DEFAULT_PROVIDER})",
)
@click.option(
    "--env",
    "env_vars",
    multiple=True,
    help=(
        "Set env vars before installing the agent. Values are stored in "
        "~/.aws/cli-agent-orchestrator/.env and can be referenced in profiles as ${VAR}. "
        "Repeatable: --env KEY=VALUE. Example: --env API_TOKEN=my-secret-token."
    ),
)
def install(agent_source: str, provider: str, env_vars: tuple[str, ...]):
    """
    Install an agent from a source-tree example, URL, or file path.

    AGENT_SOURCE can be:
    - Agent name (e.g., 'developer', 'code_supervisor')
    - File path (e.g., './my-agent.md', '/path/to/agent.md')
    - URL (e.g., 'https://example.com/agent.md')

    Agents can reference values from ~/.aws/cli-agent-orchestrator/.env using ${VAR}
    placeholders in frontmatter or markdown content. Use `cao env set KEY VALUE` to
    manage those values separately, or pass `--env KEY=VALUE` during install to write
    them before the profile is loaded.

    Example:
    \b
        cao install ./service-agent.md --provider claude_code \
          --env API_TOKEN=my-secret-token \
          --env SERVICE_URL=http://127.0.0.1:27124
    """
    try:
        agent_name, raw_content = _read_agent_source(agent_source)

        for env_assignment in env_vars:
            key, value = _parse_env_assignment(env_assignment)
            set_env_var(key, value)

        resolved_content = resolve_env_vars(raw_content)
        profile = _parse_agent_markdown(resolved_content, agent_name, provider)

        # Warn about unresolved placeholders that will leak into provider configs
        unresolved = set(re.findall(r"\$\{(\w+)\}", resolved_content))
        if unresolved:
            names = ", ".join(sorted(unresolved))
            click.echo(
                f"⚠ Unresolved env var(s) in profile: {names}. "
                f"Set them with `cao env set` or pass --env KEY=VALUE.",
                err=True,
            )

        # Write unresolved source to agent-context (secrets stay in .env)
        AGENT_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        dest_file = AGENT_CONTEXT_DIR / f"{profile.id}.md"
        dest_file.write_text(raw_content)

        # Resolve provider runtime capabilities from profile → defaults.
        from cli_agent_orchestrator.utils.tool_mapping import resolve_runtime_capabilities

        mcp_server_names = list(profile.mcp_servers.keys()) if profile.mcp_servers else None
        allowed_tools = resolve_runtime_capabilities(profile.runtime_capabilities, mcp_server_names)

        # Create agent config based on provider
        agent_file = None
        if provider == ProviderType.Q_CLI.value:
            Q_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
            agent_config = QAgentConfig(
                name=profile.id,
                description=profile.description,
                tools=list(profile.tools) if profile.tools else ["*"],
                allowedTools=allowed_tools,
                resources=[f"file://{dest_file.absolute()}"],
                prompt=compose_agent_prompt(profile),
                mcpServers=profile.mcp_servers,
                toolAliases=profile.tool_aliases,
                toolsSettings=profile.tools_settings,
                hooks=profile.hooks,
                model=profile.model,
            )
            safe_filename = profile.id.replace("/", "__")
            agent_file = Q_AGENTS_DIR / f"{safe_filename}.json"
            agent_file.write_text(
                agent_config.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
            )

        elif provider == ProviderType.KIRO_CLI.value:
            KIRO_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
            # Kiro natively supports skill:// resources with progressive loading
            # (metadata at startup, full content on demand).
            kiro_resources = [
                f"file://{dest_file.absolute()}",
                f"skill://{SKILLS_DIR}/**/SKILL.md",
            ]
            raw_prompt = (
                profile.prompt.strip() if profile.prompt and profile.prompt.strip() else None
            )
            agent_config = KiroAgentConfig(
                name=profile.id,
                description=profile.description,
                tools=list(profile.tools) if profile.tools else ["*"],
                allowedTools=allowed_tools,
                resources=kiro_resources,
                prompt=raw_prompt,
                mcpServers=profile.mcp_servers,
                toolAliases=profile.tool_aliases,
                toolsSettings=profile.tools_settings,
                hooks=profile.hooks,
                model=profile.model,
            )
            safe_filename = profile.id.replace("/", "__")
            agent_file = KIRO_AGENTS_DIR / f"{safe_filename}.json"
            agent_file.write_text(
                agent_config.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
            )

        elif provider == ProviderType.COPILOT_CLI.value:
            COPILOT_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
            base_prompt = profile.prompt.strip() if profile.prompt else ""
            if not base_prompt:
                raise ValueError(
                    f"Agent '{profile.id}' has no usable prompt content for Copilot"
                )

            # Bake skill catalog into the agent prompt body (same as Kiro/Q)
            prompt = compose_agent_prompt(profile, base_prompt=base_prompt) or base_prompt

            safe_filename = profile.id.replace("/", "__")
            agent_file = COPILOT_AGENTS_DIR / f"{safe_filename}.agent.md"
            agent_config = CopilotAgentConfig(
                name=profile.id,
                description=profile.description,
                prompt=prompt,
            )
            agent_post = frontmatter.Post(
                prompt.rstrip(),
                name=agent_config.name,
                description=agent_config.description,
            )
            agent_file.write_text(frontmatter.dumps(agent_post), encoding="utf-8")

        click.echo(f"✓ Agent '{profile.id}' installed successfully")
        if env_vars:
            click.echo(f"✓ Set {len(env_vars)} env var(s) in {CAO_ENV_FILE}")
        click.echo(f"✓ Context file: {dest_file}")
        if agent_file:
            click.echo(f"✓ {provider} agent: {agent_file}")

    except click.BadParameter:
        raise
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        return
    except requests.RequestException as e:
        click.echo(f"Error: Failed to download agent: {e}", err=True)
        return
    except Exception as e:
        click.echo(f"Error: Failed to install agent: {e}", err=True)
        return

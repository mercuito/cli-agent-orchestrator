"""Terminal service with workflow functions.

This module provides high-level terminal management operations that orchestrate
multiple components (database, tmux, providers) to create a unified terminal
abstraction for CLI agents.

Key Responsibilities:
- Terminal lifecycle management (create, get, delete)
- Provider initialization and cleanup
- Tmux session/window management
- Terminal output capture and message extraction

Terminal Workflow:
1. create_terminal() → Creates tmux window, initializes provider, starts logging
2. send_input() → Sends user message to the agent via tmux
3. get_output() → Retrieves agent response from terminal history
4. delete_terminal() → Cleans up provider, database record, and logging
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Mapping, Optional

from cli_agent_orchestrator.agent_identity import AgentIdentity, ensure_agent_identity_runtime_paths
from cli_agent_orchestrator.clients.database import create_terminal as db_create_terminal
from cli_agent_orchestrator.clients.database import delete_terminal as db_delete_terminal
from cli_agent_orchestrator.clients.database import (
    get_terminal_metadata,
    update_last_active,
)
from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.constants import SESSION_PREFIX, TERMINAL_LOG_DIR
from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.models.terminal import Terminal, TerminalStatus
from cli_agent_orchestrator.providers.base import AgentRuntimeLaunchContext
from cli_agent_orchestrator.providers.manager import provider_manager
from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile
from cli_agent_orchestrator.utils.skills import build_skill_catalog
from cli_agent_orchestrator.utils.terminal import (
    generate_session_name,
    generate_terminal_id,
    generate_window_name,
)

logger = logging.getLogger(__name__)


class OutputMode(str, Enum):
    """Output mode for terminal history retrieval.

    FULL: Returns complete terminal output (scrollback buffer)
    LAST: Returns only the last agent response (extracted by provider)
    """

    FULL = "full"
    LAST = "last"


# Providers that accept a runtime skill_prompt kwarg and append it to the
# system prompt at launch time.  Kiro receives skills via native skill://
# resources; Q and Copilot receive skills via baked prompts at install time.
RUNTIME_SKILL_PROMPT_PROVIDERS = {
    ProviderType.CLAUDE_CODE.value,
    ProviderType.CODEX.value,
    ProviderType.GEMINI_CLI.value,
    ProviderType.KIMI_CLI.value,
}


@dataclass(frozen=True)
class TerminalRuntimeInputs:
    """Resolved profile-derived inputs shared by terminal launch and freshness."""

    allowed_tools: Optional[list]
    skill_prompt: str
    profile_material: dict


def resolve_terminal_runtime_inputs(
    agent_profile: str,
    *,
    allowed_tools: Optional[list] = None,
) -> TerminalRuntimeInputs:
    """Resolve launch inputs that affect terminal runtime behavior."""
    profile = load_agent_profile(agent_profile)
    skill_prompt = build_skill_catalog()

    resolved_allowed_tools = allowed_tools
    if resolved_allowed_tools is None:
        try:
            from cli_agent_orchestrator.utils.tool_mapping import resolve_allowed_tools

            mcp_server_names = list(profile.mcpServers.keys()) if profile.mcpServers else None
            resolved_allowed_tools = resolve_allowed_tools(
                profile.allowedTools, profile.role, mcp_server_names
            )
        except FileNotFoundError:
            pass  # Profile not found; no tool restrictions

    return TerminalRuntimeInputs(
        allowed_tools=resolved_allowed_tools,
        skill_prompt=skill_prompt,
        profile_material=profile.model_dump(exclude_none=True),
    )


def create_terminal(
    provider: str,
    agent_profile: str,
    session_name: Optional[str] = None,
    new_session: bool = False,
    working_directory: Optional[str] = None,
    allowed_tools: Optional[list] = None,
    agent_identity: Optional[AgentIdentity] = None,
    provider_runtime: Optional[Mapping[str, Any]] = None,
) -> Terminal:
    """Create a new terminal with an initialized CLI agent.

    This function orchestrates the complete terminal creation workflow:
    1. Generate unique terminal ID and window name
    2. Create tmux session/window (new or existing)
    3. Save terminal metadata to database
    4. Initialize the CLI provider (starts the agent)
    5. Set up terminal logging via tmux pipe-pane

    Args:
        provider: Provider type string (e.g., "kiro_cli", "claude_code")
        agent_profile: Name of the agent profile to use
        session_name: Optional custom session name. If not provided, auto-generated.
        new_session: If True, creates a new tmux session. If False, adds to existing.
        working_directory: Optional working directory for the terminal shell

    Returns:
        Terminal object with all metadata populated

    Raises:
        ValueError: If session already exists (new_session=True) or not found (new_session=False)
        TimeoutError: If provider initialization times out
    """
    terminal_id = ""
    runtime_prepared = False
    try:
        # Step 1: Generate unique identifiers
        terminal_id = generate_terminal_id()

        if not session_name:
            session_name = generate_session_name()
        if new_session and not session_name.startswith(SESSION_PREFIX):
            session_name = f"{SESSION_PREFIX}{session_name}"

        window_name = generate_window_name(agent_profile)

        runtime_inputs = resolve_terminal_runtime_inputs(
            agent_profile,
            allowed_tools=allowed_tools,
        )
        allowed_tools = runtime_inputs.allowed_tools

        env: Optional[Dict[str, str]] = None
        launch_context: Optional[AgentRuntimeLaunchContext] = None
        if agent_identity is not None:
            runtime_paths = ensure_agent_identity_runtime_paths(agent_identity, provider)
            launch_context = AgentRuntimeLaunchContext(
                identity=agent_identity,
                identity_data_dir=runtime_paths.identity_data_dir,
                provider_data_dir=runtime_paths.provider_data_dir,
                terminal_id=terminal_id,
                session_name=session_name,
                window_name=window_name,
                working_directory=working_directory or "",
                agent_profile=agent_profile,
                allowed_tools=allowed_tools,
                skill_prompt=runtime_inputs.skill_prompt,
            )
        runtime = provider_manager.prepare_terminal_runtime(
            provider,
            terminal_id=terminal_id,
            agent_profile=agent_profile,
            working_directory=working_directory or "",
            launch_context=launch_context,
        )
        env = runtime.environment
        runtime_prepared = True
        runtime_resume_args: Optional[list[str]] = None
        if provider_runtime is not None:
            if launch_context is None:
                raise ValueError("provider_runtime requires an agent identity launch context")
            runtime_capability = provider_manager.runtime_state_capability(provider)
            if runtime_capability is None:
                raise ValueError(f"Provider {provider!r} does not support runtime restoration")
            runtime_state = runtime_capability.deserialize_runtime_state(
                provider_runtime,
                provider_data_dir=launch_context.provider_data_dir,
            )
            runtime_resume_args = runtime_capability.launch_resume_args(
                runtime_state,
                provider_data_dir=launch_context.provider_data_dir,
            )

        # Step 2: Create tmux session or window
        if new_session:
            # Prevent duplicate sessions
            if tmux_client.session_exists(session_name):
                raise ValueError(f"Session '{session_name}' already exists")

            # Create new tmux session with this terminal as the initial window
            tmux_client.create_session(
                session_name,
                window_name,
                terminal_id,
                working_directory,
                environment=env,
            )
        else:
            # Add window to existing session
            if not tmux_client.session_exists(session_name):
                raise ValueError(f"Session '{session_name}' not found")
            window_name = tmux_client.create_window(
                session_name, window_name, terminal_id, working_directory, environment=env
            )

        # Step 3: Persist terminal metadata to database
        db_create_terminal(
            terminal_id,
            session_name,
            window_name,
            provider,
            agent_profile,
            allowed_tools,
            agent_identity_id=agent_identity.id if agent_identity is not None else None,
        )

        # Step 4: Create and initialize the CLI provider
        # This starts the agent (e.g., runs "kiro-cli chat --agent developer")
        # Only runtime-prompt providers (Claude Code, Codex, Gemini, Kimi) receive
        # the skill catalog; Kiro uses native skill:// resources, Q and Copilot
        # get it baked at install time.
        provider_instance = provider_manager.create_provider(
            provider,
            terminal_id,
            session_name,
            window_name,
            agent_profile,
            allowed_tools,
            skill_prompt=(
                runtime_inputs.skill_prompt if provider in RUNTIME_SKILL_PROMPT_PROVIDERS else None
            ),
            runtime_resume_args=runtime_resume_args,
        )
        provider_instance.initialize()

        # Step 5: Set up terminal logging via tmux pipe-pane
        # This captures all terminal output to a log file for inbox monitoring
        log_path = TERMINAL_LOG_DIR / f"{terminal_id}.log"
        log_path.touch()  # Ensure file exists before watching
        tmux_client.pipe_pane(session_name, window_name, str(log_path))

        # Build and return the Terminal object
        terminal = Terminal(
            id=terminal_id,
            name=window_name,
            provider=ProviderType(provider),
            session_name=session_name,
            agent_profile=agent_profile,
            agent_identity_id=agent_identity.id if agent_identity is not None else None,
            allowed_tools=allowed_tools,
            status=TerminalStatus.IDLE,
            last_active=datetime.now(),
        )

        logger.info(
            f"Created terminal: {terminal_id} in session: {session_name} (new_session={new_session})"
        )
        return terminal

    except Exception as e:
        # Cleanup on failure: clean up provider resources and kill session
        logger.error(f"Failed to create terminal: {e}")
        try:
            provider_manager.cleanup_provider(terminal_id)
        except Exception:
            pass  # Ignore cleanup errors
        if runtime_prepared and terminal_id:
            try:
                provider_manager.cleanup_terminal_runtime(provider, terminal_id)
            except Exception:
                pass
        if new_session and session_name:
            try:
                tmux_client.kill_session(session_name)
            except:
                pass  # Ignore cleanup errors
        raise


def get_terminal(terminal_id: str) -> Dict:
    """Get terminal data."""
    try:
        metadata = get_terminal_metadata(terminal_id)
        if not metadata:
            raise ValueError(f"Terminal '{terminal_id}' not found")

        # Get status from provider
        provider = provider_manager.get_provider(terminal_id)
        if provider is None:
            raise ValueError(f"Provider not found for terminal {terminal_id}")
        status = provider.get_status().value

        return {
            "id": metadata["id"],
            "name": metadata["tmux_window"],
            "provider": metadata["provider"],
            "session_name": metadata["tmux_session"],
            "agent_profile": metadata["agent_profile"],
            "agent_identity_id": metadata.get("agent_identity_id"),
            "allowed_tools": metadata.get("allowed_tools"),
            "status": status,
            "last_active": metadata["last_active"],
        }

    except Exception as e:
        logger.error(f"Failed to get terminal {terminal_id}: {e}")
        raise


def get_working_directory(terminal_id: str) -> Optional[str]:
    """Get the current working directory of a terminal's pane.

    Args:
        terminal_id: The terminal identifier

    Returns:
        Working directory path, or None if pane has no directory

    Raises:
        ValueError: If terminal not found
        Exception: If unable to query working directory
    """
    try:
        metadata = get_terminal_metadata(terminal_id)
        if not metadata:
            raise ValueError(f"Terminal '{terminal_id}' not found")

        working_dir = tmux_client.get_pane_working_directory(
            metadata["tmux_session"], metadata["tmux_window"]
        )
        return working_dir

    except Exception as e:
        logger.error(f"Failed to get working directory for terminal {terminal_id}: {e}")
        raise


def send_input(terminal_id: str, message: str) -> bool:
    """Send input to terminal via tmux paste buffer.

    Uses bracketed paste mode (-p) to bypass TUI hotkey handling. The provider
    resolves how many Enter keys to send from provider runtime configuration.
    """
    try:
        metadata = get_terminal_metadata(terminal_id)
        if not metadata:
            raise ValueError(f"Terminal '{terminal_id}' not found")

        # Check how many Enter keys the provider needs after paste
        provider = provider_manager.get_provider(terminal_id)
        enter_count = provider.paste_enter_count if provider else 1

        tmux_client.send_keys(
            metadata["tmux_session"], metadata["tmux_window"], message, enter_count=enter_count
        )

        # Notify the provider that external input was received.
        # This allows providers to adjust status
        # detection — specifically to stop reporting IDLE for the post-init
        # state and resume normal COMPLETED detection after a real task.
        if provider:
            provider.mark_input_received()

        update_last_active(terminal_id)
        logger.info(f"Sent input to terminal: {terminal_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to send input to terminal {terminal_id}: {e}")
        raise


def send_special_key(terminal_id: str, key: str) -> bool:
    """Send a tmux special key sequence (e.g., C-d, C-c) to terminal.

    Unlike send_input(), this sends the key as a tmux key name (not literal text)
    and does not append a carriage return. Used for control signals like Ctrl+D (EOF).

    Args:
        terminal_id: Target terminal identifier
        key: Tmux key name (e.g., "C-d", "C-c", "Escape")

    Returns:
        True if the key was sent successfully

    Raises:
        ValueError: If terminal not found
    """
    try:
        metadata = get_terminal_metadata(terminal_id)
        if not metadata:
            raise ValueError(f"Terminal '{terminal_id}' not found")

        tmux_client.send_special_key(metadata["tmux_session"], metadata["tmux_window"], key)

        update_last_active(terminal_id)
        logger.info(f"Sent special key '{key}' to terminal: {terminal_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to send special key to terminal {terminal_id}: {e}")
        raise


def get_output(terminal_id: str, mode: OutputMode = OutputMode.FULL) -> str:
    """Get terminal output.

    For ``LAST`` mode, if the provider declares ``extraction_retries > 0``,
    retries extraction with 10 s delays between attempts.  This handles
    TUI-based providers (e.g. Gemini CLI's Ink renderer) whose notification
    spinners can temporarily obscure response text in the tmux capture buffer.
    """
    try:
        metadata = get_terminal_metadata(terminal_id)
        if not metadata:
            raise ValueError(f"Terminal '{terminal_id}' not found")

        full_output = tmux_client.get_history(metadata["tmux_session"], metadata["tmux_window"])

        if mode == OutputMode.FULL:
            return full_output
        elif mode == OutputMode.LAST:
            provider = provider_manager.get_provider(terminal_id)
            if provider is None:
                raise ValueError(f"Provider not found for terminal {terminal_id}")

            retries = provider.extraction_retries
            last_err: Exception | None = None
            for attempt in range(1 + retries):
                try:
                    if attempt > 0:
                        time.sleep(10.0)
                        full_output = tmux_client.get_history(
                            metadata["tmux_session"], metadata["tmux_window"]
                        )
                    return provider.extract_last_message_from_script(full_output)
                except ValueError as exc:
                    last_err = exc
                    logger.debug(
                        "Output extraction attempt %d/%d for %s failed: %s",
                        attempt + 1,
                        1 + retries,
                        terminal_id,
                        exc,
                    )
            raise last_err  # type: ignore[misc]

    except Exception as e:
        logger.error(f"Failed to get output from terminal {terminal_id}: {e}")
        raise


def delete_terminal(terminal_id: str, *, require_window_killed: bool = False) -> bool:
    """Delete terminal and kill its tmux window.

    When replacing an identity runtime, callers can require the tmux window to
    be killed before metadata is removed so stale live panes are not orphaned.
    """
    try:
        # Get metadata before deletion
        metadata = get_terminal_metadata(terminal_id)

        if metadata:
            # Stop pipe-pane logging
            try:
                tmux_client.stop_pipe_pane(metadata["tmux_session"], metadata["tmux_window"])
            except Exception as e:
                logger.warning(f"Failed to stop pipe-pane for {terminal_id}: {e}")

            # Kill the tmux window (this terminates the agent process)
            try:
                tmux_client.kill_window(metadata["tmux_session"], metadata["tmux_window"])
            except Exception as e:
                logger.warning(f"Failed to kill tmux window for {terminal_id}: {e}")
                if require_window_killed:
                    raise RuntimeError(
                        f"Failed to kill tmux window for terminal {terminal_id}"
                    ) from e

        # Cleanup provider state and database record
        provider_manager.cleanup_provider(terminal_id)
        deleted = db_delete_terminal(terminal_id)
        try:
            provider = metadata["provider"] if metadata else ""
            if provider:
                provider_manager.cleanup_terminal_runtime(provider, terminal_id)
        except Exception as e:
            logger.warning(f"Failed to cleanup provider runtime for terminal {terminal_id}: {e}")
        logger.info(f"Deleted terminal: {terminal_id}")
        return deleted

    except Exception as e:
        logger.error(f"Failed to delete terminal {terminal_id}: {e}")
        raise

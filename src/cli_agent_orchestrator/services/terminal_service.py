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
from typing import Dict, Optional

from cli_agent_orchestrator.agent import (
    Agent,
    AgentWorkspaceContextRuntimePaths,
    ensure_agent_workspace_context_runtime_paths,
    load_agent,
)
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


@dataclass(frozen=True)
class TerminalRuntimeInputs:
    """Resolved agent inputs shared by terminal launch and freshness."""

    allowed_tools: Optional[list]
    agent_material: dict


@dataclass(frozen=True)
class _AgentTerminalLaunch:
    """Agent-owned launch metadata prepared by create_terminal_for_agent."""

    agent: Agent
    workspace_context_id: str

    @property
    def agent_id(self) -> str:
        return self.agent.id

    def build_context(
        self,
        *,
        provider: str,
        terminal_id: str,
        session_name: str,
        window_name: str,
        working_directory: str,
        agent_id: str,
        allowed_tools: Optional[list],
    ) -> AgentRuntimeLaunchContext:
        runtime_paths: AgentWorkspaceContextRuntimePaths = (
            ensure_agent_workspace_context_runtime_paths(
                self.agent,
                self.workspace_context_id,
                provider,
            )
        )
        return AgentRuntimeLaunchContext(
            agent=self.agent,
            agent_data_dir=runtime_paths.agent_data_dir,
            provider_data_dir=runtime_paths.provider_data_dir,
            terminal_id=terminal_id,
            session_name=session_name,
            window_name=window_name,
            working_directory=working_directory,
            agent_id=agent_id,
            allowed_tools=allowed_tools,
        )


def resolve_terminal_runtime_inputs(
    agent_id: str,
    *,
    allowed_tools: Optional[list] = None,
) -> TerminalRuntimeInputs:
    """Resolve launch inputs that affect terminal runtime behavior."""
    agent = load_agent(agent_id)

    resolved_allowed_tools = allowed_tools
    if resolved_allowed_tools is None:
        try:
            from cli_agent_orchestrator.utils.tool_mapping import resolve_runtime_capabilities

            mcp_server_names = list(agent.mcp_servers.keys()) if agent.mcp_servers else None
            resolved_allowed_tools = resolve_runtime_capabilities(
                agent.runtime_capabilities, mcp_server_names
            )
        except FileNotFoundError:
            pass

    return TerminalRuntimeInputs(
        allowed_tools=resolved_allowed_tools,
        agent_material={
            "id": agent.id,
            "display_name": agent.display_name,
            "cli_provider": agent.cli_provider,
            "workdir": agent.workdir,
            "session_name": agent.session_name,
            "model": agent.model,
            "reasoning_effort": agent.reasoning_effort,
            "mcp_servers": dict(agent.mcp_servers),
            "tools": list(agent.tools),
            "cao_tools": None if agent.cao_tools is None else list(agent.cao_tools),
            "skills": list(agent.skills),
            "runtime_capabilities": (
                None if agent.runtime_capabilities is None else list(agent.runtime_capabilities)
            ),
            "codex_config": dict(agent.codex_config),
        },
    )


def create_terminal(
    provider: str,
    agent_id: str,
    session_name: Optional[str] = None,
    new_session: bool = False,
    working_directory: Optional[str] = None,
    allowed_tools: Optional[list] = None,
) -> Terminal:
    """Create a new generic terminal with an initialized CLI agent.

    This function orchestrates the complete terminal creation workflow:
    1. Generate unique terminal ID and window name
    2. Create tmux session/window (new or existing)
    3. Save terminal metadata to database
    4. Initialize the CLI provider (starts the agent)
    5. Set up terminal logging via tmux pipe-pane

    Args:
        provider: Provider type string (e.g., "kiro_cli", "claude_code")
        agent_id: Name of the agent to use
        session_name: Optional custom session name. If not provided, auto-generated.
        new_session: If True, creates a new tmux session. If False, adds to existing.
        working_directory: Optional working directory for the terminal shell

    Returns:
        Terminal object with all metadata populated

    Raises:
        ValueError: If session already exists (new_session=True) or not found (new_session=False)
        TimeoutError: If provider initialization times out
    """
    return _create_terminal_core(
        provider=provider,
        agent_id=agent_id,
        session_name=session_name,
        new_session=new_session,
        working_directory=working_directory,
        allowed_tools=allowed_tools,
    )


def create_terminal_for_agent(agent: Agent) -> Terminal:
    """Create a terminal owned by an already registered CAO agent."""
    session_name = _canonical_agent_session_name(agent.session_name)
    workspace_context_id = agent.current_workspace_context_id
    if workspace_context_id is None:
        raise ValueError(
            "create_terminal_for_agent requires an agent bound " "to current_workspace_context_id"
        )
    return _create_terminal_core(
        provider=agent.cli_provider,
        agent_id=agent.id,
        session_name=session_name,
        new_session=not tmux_client.session_exists(session_name),
        working_directory=agent.workdir,
        agent_launch=_AgentTerminalLaunch(
            agent=agent,
            workspace_context_id=workspace_context_id,
        ),
    )


def _create_terminal_core(
    *,
    provider: str,
    agent_id: str,
    session_name: Optional[str] = None,
    new_session: bool = False,
    working_directory: Optional[str] = None,
    allowed_tools: Optional[list] = None,
    agent_launch: Optional[_AgentTerminalLaunch] = None,
) -> Terminal:
    """Create a terminal for an agent-managed launch."""
    if agent_launch is None:
        raise ValueError("Terminal creation requires a configured agent")
    terminal_id = ""
    runtime_prepared = False
    try:
        # Step 1: Generate unique identifiers
        terminal_id = generate_terminal_id()

        if not session_name:
            session_name = generate_session_name()
        if new_session and not session_name.startswith(SESSION_PREFIX):
            session_name = f"{SESSION_PREFIX}{session_name}"

        window_name = generate_window_name(agent_id)

        runtime_inputs = resolve_terminal_runtime_inputs(
            agent_id,
            allowed_tools=allowed_tools,
        )
        allowed_tools = runtime_inputs.allowed_tools

        env: Optional[Dict[str, str]] = None
        launch_context = agent_launch.build_context(
            provider=provider,
            terminal_id=terminal_id,
            session_name=session_name,
            window_name=window_name,
            working_directory=working_directory or "",
            agent_id=agent_id,
            allowed_tools=allowed_tools,
        )
        runtime = provider_manager.prepare_terminal_runtime(
            provider,
            terminal_id=terminal_id,
            agent_id=agent_id,
            working_directory=working_directory or "",
            launch_context=launch_context,
        )
        env = runtime.environment
        runtime_prepared = True
        runtime_resume_args: Optional[list[str]] = None
        runtime_capability = None
        runtime_capability = provider_manager.runtime_state_capability(provider)
        if runtime_capability is not None:
            runtime_state = runtime_capability.load_runtime_state(
                provider_data_dir=launch_context.provider_data_dir
            )
            if runtime_state is not None:
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
            terminal_id=terminal_id,
            tmux_session=session_name,
            tmux_window=window_name,
            provider=provider,
            agent_id=agent_launch.agent_id,
            workspace_context_id=agent_launch.workspace_context_id,
            allowed_tools=allowed_tools,
        )

        # Step 4: Create and initialize the CLI provider
        # This starts the agent (e.g., runs "kiro-cli chat --agent developer")
        # Profile-scoped skills are delivered through provider-native runtime
        # storage during prepare_terminal_runtime, not appended as CAO prompt text.
        provider_instance = provider_manager.create_provider(
            provider,
            terminal_id,
            session_name,
            window_name,
            agent_id,
            allowed_tools,
            runtime_resume_args=runtime_resume_args,
            provider_data_dir=str(launch_context.provider_data_dir),
        )
        try:
            provider_instance.initialize()
        except Exception as exc:
            if (
                runtime_resume_args
                and runtime_capability is not None
                and _looks_like_stale_resume_failure(exc)
            ):
                logger.warning(
                    "Provider resume failed for terminal %s; clearing runtime state and "
                    "retrying cold start: %s",
                    terminal_id,
                    exc,
                )
                provider_manager.cleanup_provider(terminal_id)
                db_delete_terminal(terminal_id)
                if new_session and session_name:
                    tmux_client.kill_session(session_name)
                else:
                    tmux_client.kill_window(session_name, window_name)
                provider_manager.cleanup_terminal_runtime(provider, terminal_id)
                runtime_capability.clear_runtime_state(
                    provider_data_dir=launch_context.provider_data_dir
                )
                return _create_terminal_core(
                    provider=provider,
                    agent_id=agent_id,
                    session_name=session_name,
                    new_session=new_session,
                    working_directory=working_directory,
                    allowed_tools=allowed_tools,
                    agent_launch=agent_launch,
                )
            raise

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
            agent_id=agent_launch.agent_id,
            workspace_context_id=agent_launch.workspace_context_id,
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
        if terminal_id:
            try:
                db_delete_terminal(terminal_id)
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


def _looks_like_stale_resume_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    stale_markers = (
        "no saved session found",
        "session not found",
        "not found with id",
        "could not resume",
        "resume failed",
    )
    return any(marker in message for marker in stale_markers)


def _canonical_agent_session_name(session_name: str) -> str:
    """Return a managed CAO session name for an agent."""
    if session_name.startswith(SESSION_PREFIX):
        return session_name
    return f"{SESSION_PREFIX}{session_name}"


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
            "agent_id": metadata["agent_id"],
            "agent_id": metadata.get("agent_id"),
            "workspace_context_id": metadata.get("workspace_context_id"),
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


def interrupt_terminal(terminal_id: str) -> bool:
    """Ask the terminal's provider to interrupt its active turn."""
    try:
        metadata = get_terminal_metadata(terminal_id)
        if not metadata:
            raise ValueError(f"Terminal '{terminal_id}' not found")

        provider = provider_manager.get_provider(terminal_id)
        if provider is None:
            raise ValueError(f"Provider not found for terminal {terminal_id}")

        interrupted = provider.interrupt()
        if interrupted:
            update_last_active(terminal_id)
        logger.info(f"Interrupted terminal: {terminal_id} (sent={interrupted})")
        return interrupted

    except Exception as e:
        logger.error(f"Failed to interrupt terminal {terminal_id}: {e}")
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

    When replacing an agent runtime, callers can require the tmux window to
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

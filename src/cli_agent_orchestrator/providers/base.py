"""Base provider interface for CLI tool abstraction.

This module defines the abstract base class that all CLI providers must implement.
A "provider" is an adapter that enables CAO to interact with a specific CLI-based
AI agent (e.g., Kiro CLI, Claude Code, Codex, Q CLI).

Provider Responsibilities:
- Initialize the CLI tool in a tmux window (run startup commands)
- Detect terminal state by parsing terminal output (IDLE, PROCESSING, COMPLETED, etc.)
- Extract agent responses from terminal output
- Provide cleanup logic when terminal is deleted

Implemented Providers:
- KiroCliProvider: For Kiro CLI (kiro-cli chat)
- ClaudeCodeProvider: For Claude Code (claude)
- CodexProvider: For Codex CLI (codex)
- QCliProvider: For Amazon Q Developer CLI (q chat)

Each provider must implement pattern matching for its specific CLI's prompt
and output format to reliably detect status changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol

from cli_agent_orchestrator.agent_identity import AgentIdentity
from cli_agent_orchestrator.models.terminal import TerminalStatus


@dataclass(frozen=True)
class AgentRuntimeLaunchContext:
    """Provider-facing launch context for an identity-managed runtime."""

    identity: AgentIdentity
    identity_data_dir: Path
    provider_data_dir: Path
    terminal_id: str
    session_name: str
    window_name: str
    working_directory: str
    agent_profile: str
    allowed_tools: list[str] | None


@dataclass(frozen=True)
class ProviderRuntimeDescriptor:
    """Provider-owned material that contributes to runtime freshness."""

    schema_version: str
    material: Mapping[str, Any]


@dataclass(frozen=True)
class ProviderRuntimeState:
    """Provider-owned runtime/session state captured at the CAO/provider boundary."""

    provider_type: str
    provider_data_dir: Path
    payload: Mapping[str, Any]


class ProviderRuntimeStateCapability(Protocol):
    """Optional provider capability for runtime/session restoration.

    Providers expose this capability only when they support provider-owned
    runtime/session restoration. Unsupported providers expose no capability.
    """

    def discover_current_runtime_state(
        self,
        *,
        terminal_id: str,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState | None:
        """Discover the current provider-owned runtime state, if one exists."""
        ...

    def deserialize_runtime_state(
        self,
        payload: Mapping[str, Any],
        *,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState:
        """Validate a durable payload into provider-owned runtime state."""
        ...

    def serialize_runtime_state(
        self,
        state: ProviderRuntimeState,
    ) -> Mapping[str, Any]:
        """Serialize provider-owned runtime state for CAO persistence."""
        ...

    def launch_resume_args(
        self,
        state: ProviderRuntimeState,
        *,
        provider_data_dir: Path,
    ) -> list[str]:
        """Return provider-owned CLI arguments for session restoration."""
        ...


@dataclass(frozen=True)
class ProviderRuntimePreparation:
    """Provider-owned terminal runtime preparation returned to CAO."""

    environment: Optional[Dict[str, str]] = None
    identity_scoped: bool = False


class BaseProvider(ABC):
    """Abstract base class for CLI tool providers.

    All CLI providers must inherit from this class and implement the abstract methods.
    The provider abstraction allows CAO to work with different CLI-based AI agents
    through a unified interface.

    Attributes:
        terminal_id: Unique identifier for the terminal this provider manages
        session_name: Name of the tmux session containing the terminal
        window_name: Name of the tmux window containing the terminal
        _status: Internal status cache (use get_status() for current status)
        _allowed_tools: CAO-vocabulary tool names this agent is allowed to use
    """

    provider_type: Optional[str] = None

    def __init__(
        self,
        terminal_id: str,
        session_name: str,
        window_name: str,
        allowed_tools: Optional[List[str]] = None,
    ):
        """Initialize provider with terminal context.

        Args:
            terminal_id: Unique identifier for this terminal instance
            session_name: Name of the tmux session
            window_name: Name of the tmux window
            allowed_tools: Optional list of runtime capabilities the agent is allowed to use.
        """
        self.terminal_id = terminal_id
        self.session_name = session_name
        self.window_name = window_name
        self._status = TerminalStatus.IDLE
        self._allowed_tools: Optional[List[str]] = allowed_tools

    @property
    def status(self) -> TerminalStatus:
        """Get current provider status."""
        return self._status

    @property
    def paste_enter_count(self) -> int:
        """Number of Enter keys to send after pasting user input.

        TUI submit behavior is volatile, so CAO resolves this from provider
        runtime configuration instead of baking provider-specific counts into
        provider classes.
        """
        from cli_agent_orchestrator.providers.runtime_config import (
            get_provider_paste_enter_count,
        )

        return get_provider_paste_enter_count(self.provider_type)

    @classmethod
    def runtime_fingerprint_contribution(
        cls,
        *,
        launch_context: AgentRuntimeLaunchContext,
    ) -> ProviderRuntimeDescriptor:
        """Return provider-owned runtime inputs that affect terminal freshness."""
        from cli_agent_orchestrator.providers.runtime_config import get_provider_runtime_config

        return ProviderRuntimeDescriptor(
            schema_version="provider-runtime-default.v1",
            material={
                "provider_type": cls.provider_type,
                "provider_runtime_config": get_provider_runtime_config(cls.provider_type),
            },
        )

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the provider (e.g., start CLI tool, send setup commands).

        Returns:
            bool: True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    def get_status(self, tail_lines: Optional[int] = None) -> TerminalStatus:
        """Get current provider status by analyzing terminal output.

        Args:
            tail_lines: Number of lines to capture from terminal (default: provider-specific)

        Returns:
            TerminalStatus: Current status of the provider
        """
        pass

    @abstractmethod
    def get_idle_pattern_for_log(self) -> str:
        """Get pattern that indicates IDLE state in log file output.

        Used for quick detection in file watcher before calling full get_status().
        Should return a simple pattern that appears in the IDLE prompt.

        Returns:
            str: Pattern to search for in log file tail
        """
        pass

    @property
    def extraction_retries(self) -> int:
        """Number of extraction retries for transient TUI rendering issues.

        TUI-based providers (e.g. Gemini CLI's Ink renderer) may show
        notification spinners that temporarily obscure response text in
        the tmux capture buffer.  Override this to enable automatic retries
        with re-capture between attempts.  Default is 0 (no retries).
        """
        return 0

    @abstractmethod
    def extract_last_message_from_script(self, script_output: str) -> str:
        """Extract the last message from terminal script output.

        Args:
            script_output: Raw terminal output/script content

        Returns:
            str: Extracted last message from the provider
        """
        pass

    @abstractmethod
    def exit_cli(self) -> str:
        """Get the command to exit the provider CLI.

        Returns:
            Command string to send to terminal for exiting
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up provider resources."""
        pass

    def mark_input_received(self) -> None:
        """Notify the provider that external input was sent to the terminal.

        Called by the terminal service after send_input() delivers a message.
        Providers can override this to adjust status detection behavior.
        For example, providers with initial prompts can use this to
        distinguish post-init idle (ready for first input) from
        post-task completed.
        """
        pass

    def _update_status(self, status: TerminalStatus) -> None:
        """Update internal status."""
        self._status = status

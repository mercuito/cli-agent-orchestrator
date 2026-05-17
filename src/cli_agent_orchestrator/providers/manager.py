"""Provider manager as module singleton with direct terminal_id → provider mapping."""

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Type, cast

from cli_agent_orchestrator.clients.database import get_terminal_metadata
from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.providers.base import (
    AgentRuntimeLaunchContext,
    BaseProvider,
    ProviderRuntimeDescriptor,
    ProviderRuntimePreparation,
    ProviderRuntimeStateCapability,
)
from cli_agent_orchestrator.providers.claude_code import ClaudeCodeProvider
from cli_agent_orchestrator.providers.codex import CodexProvider
from cli_agent_orchestrator.providers.copilot_cli import CopilotCliProvider
from cli_agent_orchestrator.providers.gemini_cli import GeminiCliProvider
from cli_agent_orchestrator.providers.kimi_cli import KimiCliProvider
from cli_agent_orchestrator.providers.kiro_cli import KiroCliProvider
from cli_agent_orchestrator.providers.q_cli import QCliProvider

logger = logging.getLogger(__name__)


class ProviderManager:
    """Simplified provider manager with direct mapping."""

    def __init__(self) -> None:
        self._providers: Dict[str, BaseProvider] = {}

    def _provider_class(self, provider_type: str) -> Type[BaseProvider]:
        """Return the provider class for a provider type string."""
        if provider_type == ProviderType.Q_CLI.value:
            return QCliProvider
        if provider_type == ProviderType.KIRO_CLI.value:
            return KiroCliProvider
        if provider_type == ProviderType.CLAUDE_CODE.value:
            return ClaudeCodeProvider
        if provider_type == ProviderType.CODEX.value:
            return CodexProvider
        if provider_type == ProviderType.COPILOT_CLI.value:
            return CopilotCliProvider
        if provider_type == ProviderType.GEMINI_CLI.value:
            return GeminiCliProvider
        if provider_type == ProviderType.KIMI_CLI.value:
            return KimiCliProvider
        raise ValueError(f"Unknown provider type: {provider_type}")

    def provider_supports_resume(self, provider_type: str) -> bool:
        """Return whether a provider supports agent runtime context preservation."""
        return self.runtime_state_capability(provider_type) is not None

    def runtime_state_capability(
        self,
        provider_type: str,
    ) -> Optional[ProviderRuntimeStateCapability]:
        """Return a provider's optional runtime/session capability, if supported."""
        provider_cls = self._provider_class(provider_type)
        capability_factory = getattr(provider_cls, "runtime_state_capability", None)
        if capability_factory is None:
            return None
        capability = capability_factory()
        return cast(ProviderRuntimeStateCapability, capability)

    def prepare_terminal_runtime(
        self,
        provider_type: str,
        *,
        terminal_id: str,
        agent_id: str,
        working_directory: str,
        launch_context: Optional[AgentRuntimeLaunchContext] = None,
    ) -> ProviderRuntimePreparation:
        """Let the provider prepare provider-owned runtime state before tmux launch."""
        provider_cls = self._provider_class(provider_type)
        prepare = getattr(provider_cls, "prepare_terminal_runtime", None)
        if prepare is None:
            return ProviderRuntimePreparation()
        typed_prepare = cast(
            Callable[..., ProviderRuntimePreparation],
            prepare,
        )
        return typed_prepare(
            terminal_id=terminal_id,
            agent_id=agent_id,
            working_directory=working_directory,
            launch_context=launch_context,
        )

    def runtime_fingerprint_contribution(
        self,
        provider_type: str,
        *,
        launch_context: AgentRuntimeLaunchContext,
    ) -> ProviderRuntimeDescriptor:
        """Return provider-owned runtime descriptor material for freshness checks."""
        return self._provider_class(provider_type).runtime_fingerprint_contribution(
            launch_context=launch_context,
        )

    def cleanup_terminal_runtime(self, provider_type: str, terminal_id: str) -> None:
        """Let the provider clean up terminal-scoped runtime state if it owns any."""
        provider_cls = self._provider_class(provider_type)
        cleanup = getattr(provider_cls, "cleanup_terminal_runtime", None)
        if cleanup is not None:
            cleanup(terminal_id)

    def create_provider(
        self,
        provider_type: str,
        terminal_id: str,
        tmux_session: str,
        tmux_window: str,
        agent_id: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        runtime_resume_args: Optional[List[str]] = None,
        provider_data_dir: Optional[str] = None,
    ) -> BaseProvider:
        """Create and store provider instance."""
        try:
            provider: BaseProvider
            if provider_type == ProviderType.Q_CLI.value:
                if not agent_id:
                    raise ValueError("Q CLI provider requires agent_id parameter")
                provider = QCliProvider(
                    terminal_id,
                    tmux_session,
                    tmux_window,
                    agent_id,
                    allowed_tools,
                )
            elif provider_type == ProviderType.KIRO_CLI.value:
                if not agent_id:
                    raise ValueError("Kiro CLI provider requires agent_id parameter")
                provider = KiroCliProvider(
                    terminal_id,
                    tmux_session,
                    tmux_window,
                    agent_id,
                    allowed_tools,
                )
            elif provider_type == ProviderType.CLAUDE_CODE.value:
                provider = ClaudeCodeProvider(
                    terminal_id,
                    tmux_session,
                    tmux_window,
                    agent_id,
                    allowed_tools,
                    provider_data_dir=(
                        None if provider_data_dir is None else Path(provider_data_dir)
                    ),
                    runtime_resume_args=runtime_resume_args,
                )
            elif provider_type == ProviderType.CODEX.value:
                provider = CodexProvider(
                    terminal_id,
                    tmux_session,
                    tmux_window,
                    agent_id,
                    allowed_tools,
                    runtime_resume_args=runtime_resume_args,
                )
            elif provider_type == ProviderType.COPILOT_CLI.value:
                provider = CopilotCliProvider(
                    terminal_id,
                    tmux_session,
                    tmux_window,
                    agent_id,
                    allowed_tools,
                )
            elif provider_type == ProviderType.GEMINI_CLI.value:
                provider = GeminiCliProvider(
                    terminal_id,
                    tmux_session,
                    tmux_window,
                    agent_id,
                    allowed_tools,
                )
            elif provider_type == ProviderType.KIMI_CLI.value:
                provider = KimiCliProvider(
                    terminal_id,
                    tmux_session,
                    tmux_window,
                    agent_id,
                    allowed_tools,
                )
            else:
                raise ValueError(f"Unknown provider type: {provider_type}")

            # Store in direct mapping
            self._providers[terminal_id] = provider
            logger.info(f"Created {provider_type} provider for terminal: {terminal_id}")
            return provider

        except Exception as e:
            logger.error(
                f"Failed to create provider {provider_type} for terminal {terminal_id}: {e}"
            )
            raise

    def get_provider(self, terminal_id: str) -> Optional[BaseProvider]:
        """Get provider instance, creating on-demand if not found.

        Args:
            terminal_id: Terminal ID to get provider for

        Returns:
            Provider instance

        Raises:
            ValueError: If terminal not found in database or provider creation fails
        """
        # Check if already exists
        provider = self._providers.get(terminal_id)
        if provider:
            return provider

        # Try to create on-demand from database metadata
        metadata = get_terminal_metadata(terminal_id)
        if not metadata:
            raise ValueError(f"Terminal {terminal_id} not found in database")

        # Create provider on-demand
        provider = self.create_provider(
            metadata["provider"],
            terminal_id,
            metadata["tmux_session"],
            metadata["tmux_window"],
            metadata["agent_id"],
        )
        logger.info(f"Created provider on-demand for terminal {terminal_id}")
        return provider

    def cleanup_provider(self, terminal_id: str) -> None:
        """Cleanup provider and remove from map (used when terminal is deleted)."""
        try:
            provider = self._providers.pop(terminal_id, None)
            if provider:
                provider.cleanup()
                logger.info(f"Cleaned up provider for terminal: {terminal_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup provider for terminal {terminal_id}: {e}")

    def list_providers(self) -> Dict[str, str]:
        """List all active providers (for debugging)."""
        return {
            terminal_id: provider.__class__.__name__
            for terminal_id, provider in self._providers.items()
        }


# Module-level singleton
provider_manager = ProviderManager()

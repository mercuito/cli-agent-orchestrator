"""Workspace-provider lifecycle and registry support."""

from cli_agent_orchestrator.workspace_providers.registry import (
    WorkspaceProvider,
    WorkspaceProviderConfigError,
    WorkspaceProviderRegistry,
    UnknownWorkspaceProviderError,
    default_workspace_provider_registry,
    initialize_enabled_workspace_providers,
    is_workspace_provider_enabled,
    load_enabled_workspace_providers,
    workspace_provider_config_exists,
)

__all__ = [
    "WorkspaceProvider",
    "WorkspaceProviderConfigError",
    "WorkspaceProviderRegistry",
    "UnknownWorkspaceProviderError",
    "default_workspace_provider_registry",
    "initialize_enabled_workspace_providers",
    "is_workspace_provider_enabled",
    "load_enabled_workspace_providers",
    "workspace_provider_config_exists",
]

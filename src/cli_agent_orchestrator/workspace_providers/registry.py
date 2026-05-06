"""Shared workspace-provider registry and startup path."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol

import tomli

from cli_agent_orchestrator.agent_identity import (
    AgentIdentity,
    AgentIdentityConfigError,
    AgentIdentityRegistry,
    load_agent_identity_registry,
)
from cli_agent_orchestrator.constants import CAO_HOME_DIR

WORKSPACE_PROVIDERS_CONFIG_PATH = CAO_HOME_DIR / "workspace-providers.toml"


class WorkspaceProviderConfigError(ValueError):
    """Raised when workspace-provider configuration is invalid."""


class UnknownWorkspaceProviderError(WorkspaceProviderConfigError):
    """Raised when an enabled workspace provider has no registered factory."""


class WorkspaceProvider(Protocol):
    """Small provider lifecycle boundary used by CAO startup."""

    name: str

    def initialize(self) -> None:
        """Validate and initialize the provider."""


class AgentIdentityWorkspaceProvider(WorkspaceProvider, Protocol):
    """Optional workspace-provider surface for resolving CAO agent identities."""

    def resolve_identity_for_agent_id(self, agent_id: str) -> AgentIdentity:
        """Resolve a durable CAO agent identity through provider-owned mapping."""


WorkspaceProviderFactory = Callable[[AgentIdentityRegistry], WorkspaceProvider]


class WorkspaceProviderRegistry:
    """Maps enabled workspace-provider names to provider factories."""

    def __init__(self, factories: Optional[Mapping[str, WorkspaceProviderFactory]] = None) -> None:
        self._factories = dict(factories or {})

    def register(self, name: str, factory: WorkspaceProviderFactory) -> None:
        normalized = _normalize_provider_name(name)
        self._factories[normalized] = factory

    def create(self, name: str, agent_registry: AgentIdentityRegistry) -> WorkspaceProvider:
        normalized = _normalize_provider_name(name)
        try:
            factory = self._factories[normalized]
        except KeyError as exc:
            raise UnknownWorkspaceProviderError(
                f"Unknown enabled workspace provider: {normalized}"
            ) from exc
        return factory(agent_registry)


def _normalize_provider_name(name: str) -> str:
    normalized = name.strip().lower()
    if not normalized:
        raise WorkspaceProviderConfigError("Workspace provider name must be non-empty")
    return normalized


def load_enabled_workspace_providers(
    config_path: Optional[Path] = None,
) -> list[str]:
    """Load the explicit enabled workspace-provider list."""
    path = WORKSPACE_PROVIDERS_CONFIG_PATH if config_path is None else config_path
    if not path.exists():
        return []

    try:
        data = tomli.loads(path.read_text())
    except tomli.TOMLDecodeError as exc:
        raise WorkspaceProviderConfigError(f"Invalid workspace-providers.toml: {exc}") from exc

    enabled = data.get("enabled", [])
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        raise WorkspaceProviderConfigError("workspace-providers.toml enabled must be a string list")

    return [_normalize_provider_name(item) for item in enabled]


def workspace_provider_config_exists(config_path: Optional[Path] = None) -> bool:
    """Return whether CAO has an explicit workspace-provider config file."""
    path = WORKSPACE_PROVIDERS_CONFIG_PATH if config_path is None else config_path
    return path.exists()


def is_workspace_provider_enabled(
    name: str,
    *,
    config_path: Optional[Path] = None,
    default_when_unconfigured: bool = True,
) -> bool:
    """Return whether a workspace provider is enabled by CAO config."""
    path = WORKSPACE_PROVIDERS_CONFIG_PATH if config_path is None else config_path
    if not path.exists():
        return default_when_unconfigured
    return _normalize_provider_name(name) in set(load_enabled_workspace_providers(path))


def default_workspace_provider_registry() -> WorkspaceProviderRegistry:
    """Return CAO's built-in v1 workspace-provider registry."""
    from cli_agent_orchestrator.linear.workspace_provider import LinearWorkspaceProvider

    registry = WorkspaceProviderRegistry()
    registry.register("linear", lambda agents: LinearWorkspaceProvider(agent_registry=agents))
    return registry


def initialize_enabled_workspace_providers(
    *,
    enabled_config_path: Optional[Path] = None,
    agents_config_path: Optional[Path] = None,
    registry: Optional[WorkspaceProviderRegistry] = None,
) -> list[WorkspaceProvider]:
    """Create and initialize startup workspace providers."""
    enabled = load_enabled_workspace_providers(enabled_config_path)
    agent_registry = load_agent_identity_registry(agents_config_path)
    provider_registry = registry or default_workspace_provider_registry()

    providers: list[WorkspaceProvider] = []
    for name in enabled:
        provider = provider_registry.create(name, agent_registry)
        provider.initialize()
        if name == "linear":
            from cli_agent_orchestrator.linear.workspace_provider import (
                LinearWorkspaceProvider,
                set_default_linear_workspace_provider,
            )

            if isinstance(provider, LinearWorkspaceProvider):
                set_default_linear_workspace_provider(provider)
        providers.append(provider)
    if not workspace_provider_config_exists(enabled_config_path):
        from cli_agent_orchestrator.linear.workspace_provider import (
            LinearWorkspaceProvider,
            has_legacy_linear_provider_config,
            set_default_linear_workspace_provider,
        )

        if has_legacy_linear_provider_config():
            provider = LinearWorkspaceProvider(agent_registry=agent_registry)
            provider.initialize()
            set_default_linear_workspace_provider(provider)
            providers.append(provider)
    return providers


def resolve_agent_identity_for_runtime(
    agent_id: str,
    *,
    agents_config_path: Optional[Path] = None,
) -> AgentIdentity:
    """Resolve a durable CAO agent identity through CAO config or workspace providers."""
    try:
        return load_agent_identity_registry(agents_config_path).get(agent_id)
    except AgentIdentityConfigError as registry_error:
        provider_errors: list[Exception] = []
        for provider in _candidate_identity_workspace_providers():
            resolver = getattr(provider, "resolve_identity_for_agent_id", None)
            if resolver is None:
                continue
            try:
                return resolver(agent_id)
            except Exception as exc:
                provider_errors.append(exc)
        if provider_errors:
            raise AgentIdentityConfigError(str(registry_error)) from provider_errors[-1]
        raise


def _candidate_identity_workspace_providers() -> list[WorkspaceProvider]:
    """Return initialized/lazy workspace providers that may own agent mappings."""
    providers: list[WorkspaceProvider] = []
    if not workspace_provider_config_exists():
        from cli_agent_orchestrator.linear.workspace_provider import (
            LinearWorkspaceProviderConfigError,
            get_linear_workspace_provider,
            has_legacy_linear_provider_config,
        )

        if has_legacy_linear_provider_config():
            try:
                providers.append(get_linear_workspace_provider())
            except LinearWorkspaceProviderConfigError:
                pass
    return providers

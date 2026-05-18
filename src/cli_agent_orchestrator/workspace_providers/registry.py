"""Shared workspace-provider registry and startup path."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol, runtime_checkable

import tomli

from cli_agent_orchestrator.agent import (
    Agent,
    AgentRegistry,
    load_agent_registry,
)
from cli_agent_orchestrator.constants import CAO_HOME_DIR
from cli_agent_orchestrator.events import CaoEvent, default_cao_event_dispatcher
from cli_agent_orchestrator.workspace_providers.events import (
    WorkspaceProviderEvent,
    default_workspace_provider_event_dispatcher,
)
from cli_agent_orchestrator.workspace_providers.tool_access import ProviderToolAccessPolicy

WORKSPACE_PROVIDERS_CONFIG_PATH = CAO_HOME_DIR / "workspace-providers.toml"


class WorkspaceProviderConfigError(ValueError):
    """Raised when workspace-provider configuration is invalid."""


class UnknownWorkspaceProviderError(WorkspaceProviderConfigError):
    """Raised when an enabled workspace provider has no registered factory."""


@runtime_checkable
class WorkspaceProvider(Protocol):
    """Small provider lifecycle boundary used by CAO startup."""

    name: str

    def initialize(self) -> None:
        """Validate and initialize the provider."""


@runtime_checkable
class AgentWorkspaceProvider(WorkspaceProvider, Protocol):
    """Optional workspace-provider surface for resolving CAO agents."""

    def resolve_agent_for_agent_id(self, agent_id: str) -> Agent:
        """Resolve a durable CAO agent through provider-owned mapping."""


@runtime_checkable
class AgentListingWorkspaceProvider(AgentWorkspaceProvider, Protocol):
    """Optional workspace-provider surface for listing provider-backed identities."""

    def list_agents(self) -> tuple[Agent, ...]:
        """Return provider-backed CAO agents known to this provider."""


@runtime_checkable
class ProviderToolAccessWorkspaceProvider(WorkspaceProvider, Protocol):
    """Optional provider surface for CAO-mediated MCP tool access."""

    def provider_tool_access(self) -> ProviderToolAccessPolicy:
        """Return preflighted provider-mediated tool access for CAO consumption."""


@runtime_checkable
class ProviderToolAccessConfigurableWorkspaceProvider(
    ProviderToolAccessWorkspaceProvider, Protocol
):
    """Optional provider hint for avoiding tool-access startup without access config."""

    def has_provider_tool_access_config(self) -> bool:
        """Return whether this provider has configured mediated tool access."""


@runtime_checkable
class EventPublishingWorkspaceProvider(WorkspaceProvider, Protocol):
    """Legacy optional provider surface for declaring non-Linear workspace events."""

    def published_events(self) -> tuple[type[WorkspaceProviderEvent], ...]:
        """Return event types published by this provider."""


@runtime_checkable
class CaoEventPublishingWorkspaceProvider(WorkspaceProvider, Protocol):
    """Optional provider surface for declaring subscribable CAO events."""

    def published_cao_events(self) -> tuple[type[CaoEvent], ...]:
        """Return CAO event types published by this provider."""


WorkspaceProviderFactory = Callable[[AgentRegistry], WorkspaceProvider]


class WorkspaceProviderRegistry:
    """Maps enabled workspace-provider names to provider factories."""

    def __init__(self, factories: Optional[Mapping[str, WorkspaceProviderFactory]] = None) -> None:
        self._factories = dict(factories or {})

    def register(self, name: str, factory: WorkspaceProviderFactory) -> None:
        normalized = _normalize_provider_name(name)
        self._factories[normalized] = factory

    def create(self, name: str, agent_registry: AgentRegistry) -> WorkspaceProvider:
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
    registry.register(
        "linear",
        lambda agents: LinearWorkspaceProvider(
            agent_registry=agents,
            preflight_credentials=False,
        ),
    )
    return registry


def initialize_enabled_workspace_providers(
    *,
    enabled_config_path: Optional[Path] = None,
    agents_config_path: Optional[Path] = None,
    registry: Optional[WorkspaceProviderRegistry] = None,
) -> list[WorkspaceProvider]:
    """Create and initialize startup workspace providers."""
    enabled = load_enabled_workspace_providers(enabled_config_path)
    agent_registry = load_agent_registry(agents_config_path)
    provider_registry = registry or default_workspace_provider_registry()

    providers: list[WorkspaceProvider] = []
    for name in enabled:
        provider = provider_registry.create(name, agent_registry)
        provider.initialize()
        _register_provider_events(provider)
        if name == "linear":
            from cli_agent_orchestrator.linear.workspace_provider import (
                LinearWorkspaceProvider,
                set_default_linear_workspace_provider,
            )

            if isinstance(provider, LinearWorkspaceProvider):
                set_default_linear_workspace_provider(provider)
        providers.append(provider)
    return providers


def load_provider_tool_access_policies(
    providers: list[WorkspaceProvider],
) -> dict[str, ProviderToolAccessPolicy]:
    """Ask initialized providers for CAO-mediated tool access policies."""
    policies: dict[str, ProviderToolAccessPolicy] = {}
    for provider in providers:
        if not isinstance(provider, ProviderToolAccessWorkspaceProvider):
            continue
        policy = provider.provider_tool_access()
        if policy.provider_name in policies:
            raise WorkspaceProviderConfigError(
                f"Duplicate provider tool access policy: {policy.provider_name}"
            )
        policies[policy.provider_name] = policy
    return policies


def load_enabled_provider_tool_access_policies(
    *,
    enabled_config_path: Optional[Path] = None,
    agents_config_path: Optional[Path] = None,
    registry: Optional[WorkspaceProviderRegistry] = None,
    agent_registry: Optional[AgentRegistry] = None,
) -> dict[str, ProviderToolAccessPolicy]:
    """Load provider-mediated tool access without initializing unrelated providers."""
    enabled = load_enabled_workspace_providers(enabled_config_path)
    agents = agent_registry or load_agent_registry(agents_config_path)
    provider_registry = registry or default_workspace_provider_registry()

    providers_with_tools: list[WorkspaceProvider] = []
    for name in enabled:
        provider = provider_registry.create(name, agents)
        if not isinstance(provider, ProviderToolAccessWorkspaceProvider):
            continue
        if (
            isinstance(provider, ProviderToolAccessConfigurableWorkspaceProvider)
            and not provider.has_provider_tool_access_config()
        ):
            continue
        provider.initialize()
        _register_provider_events(provider)
        providers_with_tools.append(provider)
    policies = load_provider_tool_access_policies(providers_with_tools)
    from cli_agent_orchestrator.workspace_setups import default_workspace_collaboration_manager

    return default_workspace_collaboration_manager(
        agent_registry=agents,
    ).team_bound_provider_tool_access_policies(policies)


def resolve_agent_for_runtime(
    agent_id: str,
    *,
    agents_config_path: Optional[Path] = None,
) -> Agent:
    """Resolve a durable CAO agent through the central manager."""
    from cli_agent_orchestrator.services.agent_manager import (
        create_default_agent_manager,
    )

    return create_default_agent_manager(
        agents_root=agents_config_path,
    ).resolve_agent(agent_id)


def candidate_agent_workspace_providers() -> list[WorkspaceProvider]:
    """Return initialized/lazy workspace providers that may own agent mappings."""
    return []


def _register_provider_events(provider: WorkspaceProvider) -> None:
    if isinstance(provider, CaoEventPublishingWorkspaceProvider):
        default_cao_event_dispatcher().register_events(provider.published_cao_events())
    if not isinstance(provider, EventPublishingWorkspaceProvider):
        return
    default_workspace_provider_event_dispatcher().register_events(provider.published_events())

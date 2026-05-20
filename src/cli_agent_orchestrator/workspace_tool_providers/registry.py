"""Shared workspace-tool-provider registry and startup path."""

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
from cli_agent_orchestrator.workspace_tool_providers.events import (
    WorkspaceToolProviderEvent,
    default_workspace_tool_provider_event_dispatcher,
)
from cli_agent_orchestrator.workspace_tool_providers.tool_access import (
    ProviderConversationAccessRequirement,
    ProviderRoleToolAccessGrant,
    ProviderToolAccessPolicy,
)

WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH = CAO_HOME_DIR / "workspace-tool-providers.toml"
_OLD_WORKSPACE_PROVIDERS_CONFIG_PATH = CAO_HOME_DIR / "workspace-providers.toml"


class WorkspaceToolProviderConfigError(ValueError):
    """Raised when workspace-tool-provider configuration is invalid."""


class UnknownWorkspaceToolProviderError(WorkspaceToolProviderConfigError):
    """Raised when an enabled workspace tool provider has no registered factory."""


@runtime_checkable
class WorkspaceToolProvider(Protocol):
    """Small provider lifecycle boundary used by CAO startup."""

    name: str

    def initialize(self) -> None:
        """Validate and initialize the provider."""


@runtime_checkable
class AgentWorkspaceToolProvider(WorkspaceToolProvider, Protocol):
    """Optional workspace-tool-provider surface for resolving CAO agents."""

    def resolve_agent_for_agent_id(self, agent_id: str) -> Agent:
        """Resolve a durable CAO agent through provider-owned mapping."""


@runtime_checkable
class AgentListingWorkspaceToolProvider(AgentWorkspaceToolProvider, Protocol):
    """Optional workspace-tool-provider surface for listing provider-backed identities."""

    def list_agents(self) -> tuple[Agent, ...]:
        """Return provider-backed CAO agents known to this provider."""


@runtime_checkable
class ProviderToolAccessWorkspaceToolProvider(WorkspaceToolProvider, Protocol):
    """Optional provider surface for CAO-mediated MCP tool access."""

    def provider_tool_access(self) -> ProviderToolAccessPolicy:
        """Return preflighted provider-mediated tool access for CAO consumption."""


@runtime_checkable
class ProviderToolAccessConfigurableWorkspaceToolProvider(
    ProviderToolAccessWorkspaceToolProvider, Protocol
):
    """Optional provider hint for avoiding tool-access startup without access config."""

    def has_provider_tool_access_config(self) -> bool:
        """Return whether this provider has configured mediated tool access."""


@runtime_checkable
class ProviderRoleToolAccessWorkspaceToolProvider(WorkspaceToolProvider, Protocol):
    """Optional provider surface for validating team-role-owned access grants."""

    def provider_role_tool_access(
        self, grants: tuple[ProviderRoleToolAccessGrant, ...]
    ) -> ProviderToolAccessPolicy:
        """Return provider-mediated access converted from role-owned grants."""


@runtime_checkable
class ProviderConversationAccessWorkspaceToolProvider(WorkspaceToolProvider, Protocol):
    """Optional provider surface for provider-conversation access descriptors."""

    def provider_conversation_access(self) -> tuple[ProviderConversationAccessRequirement, ...]:
        """Return provider-owned provider-conversation access requirements."""


@runtime_checkable
class EventPublishingWorkspaceToolProvider(WorkspaceToolProvider, Protocol):
    """Optional workspace tool provider surface for declaring typed events."""

    def published_events(self) -> tuple[type[WorkspaceToolProviderEvent], ...]:
        """Return event types published by this provider."""


@runtime_checkable
class CaoEventPublishingWorkspaceToolProvider(WorkspaceToolProvider, Protocol):
    """Optional provider surface for declaring subscribable CAO events."""

    def published_cao_events(self) -> tuple[type[CaoEvent], ...]:
        """Return CAO event types published by this provider."""


WorkspaceToolProviderFactory = Callable[[AgentRegistry], WorkspaceToolProvider]


class WorkspaceToolProviderRegistry:
    """Maps enabled workspace-tool-provider names to provider factories."""

    def __init__(
        self, factories: Optional[Mapping[str, WorkspaceToolProviderFactory]] = None
    ) -> None:
        self._factories = dict(factories or {})

    def register(self, name: str, factory: WorkspaceToolProviderFactory) -> None:
        normalized = _normalize_provider_name(name)
        self._factories[normalized] = factory

    def create(self, name: str, agent_registry: AgentRegistry) -> WorkspaceToolProvider:
        normalized = _normalize_provider_name(name)
        try:
            factory = self._factories[normalized]
        except KeyError as exc:
            raise UnknownWorkspaceToolProviderError(
                f"Unknown enabled workspace tool provider: {normalized}"
            ) from exc
        return factory(agent_registry)


def _normalize_provider_name(name: str) -> str:
    normalized = name.strip().lower()
    if not normalized:
        raise WorkspaceToolProviderConfigError("Workspace tool provider name must be non-empty")
    return normalized


def load_enabled_workspace_tool_providers(
    config_path: Optional[Path] = None,
) -> list[str]:
    """Load the explicit enabled workspace-tool-provider list."""
    path = _workspace_tool_providers_config_path(config_path)
    if not path.exists():
        return []

    try:
        data = tomli.loads(path.read_text())
    except tomli.TOMLDecodeError as exc:
        raise WorkspaceToolProviderConfigError(
            f"Invalid workspace-tool-providers.toml: {exc}"
        ) from exc

    enabled = data.get("enabled", [])
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        raise WorkspaceToolProviderConfigError(
            "workspace-tool-providers.toml enabled must be a string list"
        )

    return [_normalize_provider_name(item) for item in enabled]


def workspace_tool_provider_config_exists(config_path: Optional[Path] = None) -> bool:
    """Return whether CAO has an explicit workspace-tool-provider config file."""
    path = _workspace_tool_providers_config_path(config_path)
    return path.exists()


def is_workspace_tool_provider_enabled(
    name: str,
    *,
    config_path: Optional[Path] = None,
    default_when_unconfigured: bool = True,
) -> bool:
    """Return whether a workspace tool provider is enabled by CAO config."""
    path = _workspace_tool_providers_config_path(config_path)
    if not path.exists():
        return default_when_unconfigured
    return _normalize_provider_name(name) in set(load_enabled_workspace_tool_providers(path))


def _workspace_tool_providers_config_path(config_path: Optional[Path]) -> Path:
    if config_path is not None:
        return config_path
    return _migrate_default_workspace_tool_providers_config_path()


def _migrate_default_workspace_tool_providers_config_path() -> Path:
    old_path = _OLD_WORKSPACE_PROVIDERS_CONFIG_PATH
    new_path = WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH
    if old_path.exists():
        if new_path.exists():
            raise WorkspaceToolProviderConfigError(
                "Both default workspace tool provider config files exist: "
                f"{old_path} and {new_path}. Keep only workspace-tool-providers.toml."
            )
        old_path.replace(new_path)
    return new_path


def default_workspace_tool_provider_registry() -> WorkspaceToolProviderRegistry:
    """Return CAO's built-in v1 workspace-tool-provider registry."""
    from cli_agent_orchestrator.linear.workspace_tool_provider import LinearWorkspaceToolProvider

    registry = WorkspaceToolProviderRegistry()
    registry.register(
        "linear",
        lambda agents: LinearWorkspaceToolProvider(
            agent_registry=agents,
            preflight_credentials=False,
        ),
    )
    return registry


def initialize_enabled_workspace_tool_providers(
    *,
    enabled_config_path: Optional[Path] = None,
    agents_config_path: Optional[Path] = None,
    registry: Optional[WorkspaceToolProviderRegistry] = None,
) -> list[WorkspaceToolProvider]:
    """Create and initialize startup workspace tool providers."""
    enabled = load_enabled_workspace_tool_providers(enabled_config_path)
    agent_registry = load_agent_registry(agents_config_path)
    provider_registry = registry or default_workspace_tool_provider_registry()

    providers: list[WorkspaceToolProvider] = []
    for name in enabled:
        provider = provider_registry.create(name, agent_registry)
        provider.initialize()
        _register_provider_events(provider)
        if name == "linear":
            from cli_agent_orchestrator.linear.workspace_tool_provider import (
                LinearWorkspaceToolProvider,
                set_default_linear_workspace_tool_provider,
            )

            if isinstance(provider, LinearWorkspaceToolProvider):
                set_default_linear_workspace_tool_provider(provider)
        providers.append(provider)
    return providers


def load_enabled_provider_tool_access_policies(
    *,
    enabled_config_path: Optional[Path] = None,
    agents_config_path: Optional[Path] = None,
    registry: Optional[WorkspaceToolProviderRegistry] = None,
    agent_registry: Optional[AgentRegistry] = None,
) -> dict[str, ProviderToolAccessPolicy]:
    """Load provider-mediated tool access through ToolService authority."""
    agents = agent_registry or load_agent_registry(agents_config_path)
    from cli_agent_orchestrator.services.agent_manager import AgentManager
    from cli_agent_orchestrator.services.tool_service import (
        ToolService,
        _load_raw_enabled_provider_tool_access_policies,
    )

    return dict(
        ToolService(
            agent_manager=AgentManager(configured_agents=agents),
            provider_policy_loader=lambda registry_arg: _load_raw_enabled_provider_tool_access_policies(
                agent_registry=registry_arg,
                enabled_config_path=enabled_config_path,
                registry=registry,
            ),
        ).provider_policies()
    )


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


def candidate_agent_workspace_tool_providers() -> list[WorkspaceToolProvider]:
    """Return initialized/lazy workspace tool providers that may own agent mappings."""
    return []


def _register_provider_events(provider: WorkspaceToolProvider) -> None:
    if isinstance(provider, CaoEventPublishingWorkspaceToolProvider):
        default_cao_event_dispatcher().register_events(provider.published_cao_events())
    if not isinstance(provider, EventPublishingWorkspaceToolProvider):
        return
    default_workspace_tool_provider_event_dispatcher().register_events(provider.published_events())

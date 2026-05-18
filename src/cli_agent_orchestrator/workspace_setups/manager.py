"""Workspace setup registry, authorization, diagnostics, and routing."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Optional, Protocol

from cli_agent_orchestrator.agent import Agent, AgentRegistry, load_agent_registry
from cli_agent_orchestrator.events import CaoEvent
from cli_agent_orchestrator.workspace_contexts import WorkspaceContextResolution


class WorkspaceSetupConfigError(ValueError):
    """Raised when workspace setup membership or routing fails closed."""


class WorkspaceSetupResolver(Protocol):
    """Resolve one provider/runtime event into one authoritative workspace context."""

    def __call__(self, event: CaoEvent) -> WorkspaceContextResolution | None:
        """Return the resolved workspace context for ``event``."""


@dataclass(frozen=True)
class WorkspaceSetup:
    """Code-owned definition of one CAO workspace setup."""

    id: str
    display_name: str
    providers: tuple[str, ...]
    resolver: WorkspaceSetupResolver

    def __post_init__(self) -> None:
        _required_token(self.id, "workspace setup id")
        _required_token(self.display_name, "workspace setup display name")
        if not self.providers:
            raise WorkspaceSetupConfigError(f"Workspace setup {self.id} must declare providers")
        normalized = tuple(_normalize_provider(provider) for provider in self.providers)
        if len(set(normalized)) != len(normalized):
            raise WorkspaceSetupConfigError(f"Workspace setup {self.id} declares duplicate providers")
        if isinstance(self.resolver, (tuple, list)):
            raise WorkspaceSetupConfigError(
                f"Workspace setup {self.id} must own exactly one resolver"
            )
        if not callable(self.resolver):
            raise WorkspaceSetupConfigError(f"Workspace setup {self.id} resolver must be callable")
        object.__setattr__(self, "providers", normalized)


@dataclass(frozen=True)
class WorkspaceProviderCandidateMapping:
    """Provider-owned candidate mapping before setup authorization."""

    provider_name: str
    agent_id: str
    mapping_kind: str
    provider_identity: str
    provider_value: str
    payload: Any


@dataclass(frozen=True)
class WorkspaceSetupAuthorizedMapping:
    """Setup-owned authorization decision for one provider candidate."""

    setup_id: str
    provider_name: str
    agent_id: str
    mapping_kind: str
    provider_identity: str
    provider_value: str
    payload: Any


@dataclass(frozen=True)
class WorkspaceProviderView:
    """Setup-filtered projection built by a provider adapter."""

    setup_id: str
    provider_name: str
    value: Any


@dataclass(frozen=True)
class WorkspaceProviderEventResolution:
    """Resolved setup-bound provider event identity."""

    setup: WorkspaceSetup
    agent: Agent
    provider_name: str
    provider_view: WorkspaceProviderView
    provider_payload: Any


@dataclass(frozen=True)
class WorkspaceSetupDiagnostic:
    """User-visible workspace setup diagnostic."""

    code: str
    message: str
    setup_id: str | None = None
    agent_id: str | None = None
    provider_name: str | None = None


class WorkspaceSetupProviderAdapter(Protocol):
    """Provider-owned adapter for setup candidate mappings and views."""

    provider_name: str

    def build_candidate_mappings(
        self, agent_registry: AgentRegistry
    ) -> tuple[WorkspaceProviderCandidateMapping, ...]:
        """Return provider-native candidate mappings for all configured agents."""

    def build_provider_view(
        self,
        *,
        setup: WorkspaceSetup,
        authorized_mappings: tuple[WorkspaceSetupAuthorizedMapping, ...],
        agent_registry: AgentRegistry,
    ) -> WorkspaceProviderView:
        """Return a setup-filtered provider-native view."""

    def resolve_event_agent_id(
        self,
        *,
        provider_view: WorkspaceProviderView,
        event: CaoEvent,
    ) -> tuple[str, Any]:
        """Return the setup-addressable agent id and provider payload for an event."""

    def describe_event_identity(self, event: CaoEvent) -> str:
        """Return a concise provider-native event identity for diagnostics."""


class WorkspaceSetupRegistry:
    """Code-owned lookup of workspace setup definitions."""

    def __init__(self, setups: tuple[WorkspaceSetup, ...] = ()) -> None:
        self._setups: dict[str, WorkspaceSetup] = {}
        for setup in setups:
            self.register(setup)

    def register(self, setup: WorkspaceSetup) -> None:
        if setup.id in self._setups:
            raise WorkspaceSetupConfigError(f"Duplicate workspace setup: {setup.id}")
        self._setups[setup.id] = setup

    def get(self, setup_id: str) -> WorkspaceSetup:
        normalized = _required_token(setup_id, "workspace setup id")
        try:
            return self._setups[normalized]
        except KeyError as exc:
            raise WorkspaceSetupConfigError(f"Unknown workspace setup: {normalized}") from exc

    def all(self) -> tuple[WorkspaceSetup, ...]:
        return tuple(self._setups[key] for key in sorted(self._setups))


class WorkspaceSetupManager:
    """Authoritative runtime service for workspace setup membership."""

    def __init__(
        self,
        *,
        setup_registry: WorkspaceSetupRegistry,
        agent_registry: AgentRegistry,
        provider_adapters: Mapping[str, WorkspaceSetupProviderAdapter],
        available_providers: tuple[str, ...] | None = None,
    ) -> None:
        self._setup_registry = setup_registry
        self._agent_registry = agent_registry
        self._provider_adapters = {
            _normalize_provider(name): adapter for name, adapter in provider_adapters.items()
        }
        self._available_providers = (
            set(self._provider_adapters) if available_providers is None else set(available_providers)
        )
        if available_providers is not None:
            self._available_providers = {
                _normalize_provider(provider_name) for provider_name in available_providers
            }

    @property
    def agent_registry(self) -> AgentRegistry:
        return self._agent_registry

    def setup_for_agent(self, agent: Agent) -> WorkspaceSetup | None:
        if agent.workspace.setup is None:
            return None
        return self._setup_registry.get(agent.workspace.setup)

    def diagnostics(self) -> tuple[WorkspaceSetupDiagnostic, ...]:
        diagnostics: list[WorkspaceSetupDiagnostic] = []
        for agent in self._agent_registry.all().values():
            for message in agent.workspace.diagnostics:
                diagnostics.append(
                    WorkspaceSetupDiagnostic(
                        code="legacy_workspace_config",
                        message=message,
                        agent_id=agent.id,
                        setup_id=agent.workspace.setup,
                    )
                )
            setup_id = agent.workspace.setup
            if setup_id is None:
                continue
            try:
                self._setup_registry.get(setup_id)
            except WorkspaceSetupConfigError as exc:
                diagnostics.append(
                    WorkspaceSetupDiagnostic(
                        code="unknown_setup",
                        message=str(exc),
                        agent_id=agent.id,
                        setup_id=setup_id,
                    )
                )
        for setup in self._setup_registry.all():
            for provider_name in setup.providers:
                if provider_name not in self._available_providers:
                    diagnostics.append(
                        WorkspaceSetupDiagnostic(
                            code="unavailable_provider",
                            message=(
                                f"Workspace setup {setup.id} requires unavailable provider "
                                f"{provider_name}"
                            ),
                            setup_id=setup.id,
                            provider_name=provider_name,
                        )
                    )
            diagnostics.extend(self._pruned_mapping_diagnostics(setup))
        return tuple(diagnostics)

    def provider_view(self, setup_id: str, provider_name: str) -> WorkspaceProviderView:
        setup = self._setup_registry.get(setup_id)
        normalized_provider = _normalize_provider(provider_name)
        if normalized_provider not in setup.providers:
            raise WorkspaceSetupConfigError(
                f"Workspace setup {setup.id} does not include provider {normalized_provider}"
            )
        if normalized_provider not in self._available_providers:
            raise WorkspaceSetupConfigError(
                f"Workspace setup {setup.id} requires unavailable provider {normalized_provider}"
            )
        adapter = self._adapter(normalized_provider)
        return adapter.build_provider_view(
            setup=setup,
            authorized_mappings=self.authorized_mappings(setup.id, normalized_provider),
            agent_registry=self._agent_registry,
        )

    def authorized_mappings(
        self, setup_id: str, provider_name: str
    ) -> tuple[WorkspaceSetupAuthorizedMapping, ...]:
        setup = self._setup_registry.get(setup_id)
        normalized_provider = _normalize_provider(provider_name)
        if normalized_provider not in setup.providers:
            raise WorkspaceSetupConfigError(
                f"Workspace setup {setup.id} does not include provider {normalized_provider}"
            )
        members = self._setup_member_ids(setup.id)
        adapter = self._adapter(normalized_provider)
        authorized: list[WorkspaceSetupAuthorizedMapping] = []
        for candidate in adapter.build_candidate_mappings(self._agent_registry):
            if candidate.agent_id not in members:
                continue
            authorized.append(
                WorkspaceSetupAuthorizedMapping(
                    setup_id=setup.id,
                    provider_name=normalized_provider,
                    agent_id=candidate.agent_id,
                    mapping_kind=candidate.mapping_kind,
                    provider_identity=candidate.provider_identity,
                    provider_value=candidate.provider_value,
                    payload=candidate.payload,
                )
            )
        return tuple(authorized)

    def authorized_tool_access_locations(self, provider_name: str) -> frozenset[str]:
        normalized_provider = _normalize_provider(provider_name)
        if normalized_provider not in self._provider_adapters:
            return frozenset()
        locations: set[str] = set()
        for setup in self._setup_registry.all():
            if normalized_provider not in setup.providers:
                continue
            for mapping in self.authorized_mappings(setup.id, normalized_provider):
                if mapping.mapping_kind == "tool_access":
                    locations.add(mapping.provider_value)
        return frozenset(locations)

    def setup_bound_provider_tool_access_policies(self, policies):
        """Prune provider tool policies to setup-authorized access mappings."""
        bound = {}
        for provider_name, policy in policies.items():
            normalized_provider = _normalize_provider(provider_name)
            if normalized_provider not in self._provider_adapters:
                bound[provider_name] = policy
                continue
            authorized_locations = self.authorized_tool_access_locations(normalized_provider)
            bound[provider_name] = replace(
                policy,
                access=tuple(
                    entry
                    for entry in policy.access
                    if entry.source_location in authorized_locations
                ),
            )
        return bound

    def resolve_event_context(
        self, agent: Agent, event: CaoEvent
    ) -> WorkspaceContextResolution | None:
        setup = self.setup_for_agent(agent)
        if setup is None:
            return None
        return setup.resolver(event)

    def resolve_provider_event(
        self, provider_name: str, event: CaoEvent
    ) -> WorkspaceProviderEventResolution:
        normalized_provider = _normalize_provider(provider_name)
        adapter = self._adapter(normalized_provider)
        matches: list[WorkspaceProviderEventResolution] = []
        errors: list[str] = []
        for setup in self._setup_registry.all():
            if normalized_provider not in setup.providers:
                continue
            try:
                view = self.provider_view(setup.id, normalized_provider)
                agent_id, payload = adapter.resolve_event_agent_id(
                    provider_view=view,
                    event=event,
                )
                matches.append(
                    WorkspaceProviderEventResolution(
                        setup=setup,
                        agent=self._agent_registry.get(agent_id),
                        provider_name=normalized_provider,
                        provider_view=view,
                        provider_payload=payload,
                    )
                )
            except WorkspaceSetupConfigError as exc:
                errors.append(str(exc))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise WorkspaceSetupConfigError(
                f"Provider event resolved in multiple workspace setups: {normalized_provider}"
            )
        identity = adapter.describe_event_identity(event)
        detail = "; ".join(errors) if errors else "no setup-authorized mapping"
        raise WorkspaceSetupConfigError(
            f"{normalized_provider} provider identity {identity} is not CAO-addressable "
            f"in any workspace setup: {detail}"
        )

    def require_same_setup_collaboration(
        self,
        *,
        sender: Agent,
        receiver: Agent,
    ) -> None:
        sender_setup = sender.workspace.setup
        receiver_setup = receiver.workspace.setup
        if sender_setup and receiver_setup and sender_setup == receiver_setup:
            self._setup_registry.get(sender_setup)
            return
        raise WorkspaceSetupConfigError(
            f"Workspace setup collaboration rejected: sender {sender.id} setup "
            f"{sender_setup or 'none'} cannot collaborate with receiver {receiver.id} setup "
            f"{receiver_setup or 'none'}"
        )

    def _setup_member_ids(self, setup_id: str) -> set[str]:
        return {
            agent.id
            for agent in self._agent_registry.all().values()
            if agent.workspace.setup == setup_id
        }

    def _adapter(self, provider_name: str) -> WorkspaceSetupProviderAdapter:
        try:
            return self._provider_adapters[provider_name]
        except KeyError as exc:
            raise WorkspaceSetupConfigError(f"Unavailable workspace provider: {provider_name}") from exc

    def _pruned_mapping_diagnostics(
        self, setup: WorkspaceSetup
    ) -> tuple[WorkspaceSetupDiagnostic, ...]:
        diagnostics: list[WorkspaceSetupDiagnostic] = []
        member_ids = self._setup_member_ids(setup.id)
        for provider_name in setup.providers:
            if provider_name not in self._provider_adapters:
                continue
            for candidate in self._provider_adapters[provider_name].build_candidate_mappings(
                self._agent_registry
            ):
                if candidate.agent_id in member_ids:
                    continue
                diagnostics.append(
                    WorkspaceSetupDiagnostic(
                        code="pruned_provider_identity",
                        message=(
                            f"Workspace setup {setup.id} pruned {provider_name} "
                            f"{candidate.provider_identity} {candidate.provider_value} for "
                            f"out-of-setup agent {candidate.agent_id}"
                        ),
                        setup_id=setup.id,
                        agent_id=candidate.agent_id,
                        provider_name=provider_name,
                    )
                )
        return tuple(diagnostics)


def default_workspace_setup_registry() -> WorkspaceSetupRegistry:
    from cli_agent_orchestrator.linear.workspace_context_resolver import (
        resolve_linear_workspace_event,
    )

    return WorkspaceSetupRegistry(
        (
            WorkspaceSetup(
                id="cao_delivery",
                display_name="CAO Delivery",
                providers=("linear",),
                resolver=resolve_linear_workspace_event,
            ),
        )
    )


def default_workspace_setup_manager(
    *,
    agent_registry: AgentRegistry | None = None,
) -> WorkspaceSetupManager:
    from cli_agent_orchestrator.linear.workspace_setup_adapter import LinearWorkspaceSetupAdapter

    registry = agent_registry or load_agent_registry()
    return WorkspaceSetupManager(
        setup_registry=default_workspace_setup_registry(),
        agent_registry=registry,
        provider_adapters={"linear": LinearWorkspaceSetupAdapter()},
    )


def _required_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceSetupConfigError(f"{label} must be a non-empty string")
    return value.strip()


def _normalize_provider(value: str) -> str:
    return _required_token(value, "workspace provider name").lower()

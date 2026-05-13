"""Central CAO agent identity manager and read surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Protocol, cast

from cli_agent_orchestrator.agent_identity import (
    AgentIdentity,
    AgentIdentityConfigError,
    AgentIdentityPathError,
    AgentIdentityRegistry,
    AgentWorkspaceContextConfig,
    load_agent_identity_registry,
    workspace_context_data_dir,
)
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile


class AgentIdentityProvider(Protocol):
    """Provider-owned identity resolution surface used through the manager."""

    def resolve_identity_for_agent_id(self, agent_id: str) -> AgentIdentity:
        """Resolve a CAO identity from provider-owned mappings."""


class AgentIdentityListingProvider(AgentIdentityProvider, Protocol):
    """Optional provider-owned identity listing surface."""

    def list_agent_identities(self) -> tuple[AgentIdentity, ...]:
        """Return provider-backed CAO identities known to the provider."""


TerminalMetadataResolver = Callable[[str], Mapping[str, object] | None]
TerminalListResolver = Callable[[], list[dict[str, object]]]


@dataclass(frozen=True)
class AgentIdentityStatus:
    """Stable CAO identity summary/status for API consumers."""

    agent_identity_id: str
    display_name: str
    agent_profile: str
    cli_provider: str
    active: bool
    active_terminal_id: Optional[str] = None
    active_workspace_context_id: Optional[str] = None
    last_active_at: Optional[datetime] = None

    @classmethod
    def inactive(cls, identity: AgentIdentity) -> "AgentIdentityStatus":
        return cls(
            agent_identity_id=identity.id,
            display_name=identity.display_name,
            agent_profile=identity.agent_profile,
            cli_provider=identity.cli_provider,
            active=False,
        )


@dataclass(frozen=True)
class OrphanedAgentTerminalReference:
    """Terminal row that points at an identity the manager cannot resolve."""

    terminal_id: str
    agent_identity_id: str
    workspace_context_id: Optional[str]
    last_active_at: Optional[datetime]
    reason: str = "unknown_agent_identity"


class AgentIdentityManager:
    """Authoritative CAO surface for identity registration, resolution, and status."""

    def __init__(
        self,
        *,
        configured_identities: Optional[AgentIdentityRegistry] = None,
        identity_providers: Iterable[AgentIdentityProvider] = (),
        terminal_lister: TerminalListResolver = db_module.list_all_terminals,
        terminal_metadata_resolver: TerminalMetadataResolver = db_module.get_terminal_metadata,
        profile_loader: Callable[[str], object] = load_agent_profile,
    ) -> None:
        self._configured_identities = configured_identities or load_agent_identity_registry()
        self._identity_providers = tuple(identity_providers)
        self._terminal_lister = terminal_lister
        self._terminal_metadata_resolver = terminal_metadata_resolver
        self._profile_loader = profile_loader
        self._registered_identities: dict[str, AgentIdentity] = {}

    def register_identity(self, identity: AgentIdentity) -> AgentIdentity:
        """Validate and register a CAO identity through the manager boundary."""
        validated = self._validate_identity(identity).without_runtime_context()
        registered = self._registered_identities.get(validated.id)
        if registered is not None and registered != validated:
            raise AgentIdentityConfigError(f"Conflicting CAO agent identity: {validated.id}")
        self._registered_identities[validated.id] = validated
        return validated

    def resolve_identity(self, agent_id: str) -> AgentIdentity:
        """Resolve one CAO identity from registered, configured, or provider-owned state."""
        normalized = _required_token(agent_id, "agent_identity_id")
        registered = self._registered_identities.get(normalized)
        if registered is not None:
            return registered
        try:
            return self._configured_identities.get(normalized)
        except AgentIdentityConfigError as registry_error:
            try:
                return self.resolve_provider_identity(normalized)
            except AgentIdentityConfigError as provider_error:
                raise AgentIdentityConfigError(str(registry_error)) from provider_error

    def require_registered_identity(self, identity: AgentIdentity) -> AgentIdentity:
        """Return the manager-known identity matching ``identity`` or fail closed."""
        resolved = self.resolve_identity(identity.id)
        if resolved.without_runtime_context() != identity.without_runtime_context():
            raise AgentIdentityConfigError(
                f"CAO agent identity {identity.id!r} does not match the manager-owned identity"
            )
        return resolved

    def resolve_provider_identity(self, agent_id: str) -> AgentIdentity:
        """Resolve and register a provider-backed identity through the manager."""
        normalized = _required_token(agent_id, "agent_identity_id")
        provider_errors: list[Exception] = []
        for provider in self._identity_providers:
            try:
                return self.register_identity(provider.resolve_identity_for_agent_id(normalized))
            except Exception as exc:
                provider_errors.append(exc)
        if provider_errors:
            raise AgentIdentityConfigError(
                f"Unknown provider-backed CAO agent identity: {normalized}"
            ) from provider_errors[-1]
        raise AgentIdentityConfigError(f"Unknown provider-backed CAO agent identity: {normalized}")

    def identity_for_terminal(self, terminal_id: str) -> AgentIdentity:
        """Resolve a terminal's manager-owned CAO identity or fail clearly."""
        metadata = self._terminal_metadata_resolver(_required_token(terminal_id, "terminal_id"))
        if metadata is None:
            raise AgentIdentityConfigError(f"Unknown terminal: {terminal_id}")
        identity_id = metadata.get("agent_identity_id")
        if not isinstance(identity_id, str) or not identity_id.strip():
            raise AgentIdentityConfigError(f"Terminal {terminal_id!r} is not identity-managed")
        try:
            return self.resolve_identity(identity_id)
        except AgentIdentityConfigError as exc:
            raise AgentIdentityConfigError(
                f"Terminal {terminal_id!r} references unknown CAO agent identity: "
                f"{identity_id.strip()}"
            ) from exc

    def list_identities(self) -> tuple[AgentIdentity, ...]:
        """List configured/registered identities plus provider-listed identities when available."""
        identities = self._configured_identities.all()
        identities.update(self._registered_identities)
        for provider in self._identity_providers:
            list_identities = getattr(provider, "list_agent_identities", None)
            if not callable(list_identities):
                continue
            for identity in list_identities():
                validated = self.register_identity(identity)
                identities.setdefault(validated.id, validated)
        return tuple(identities[key] for key in sorted(identities))

    def status_for_identity(self, agent_id: str) -> AgentIdentityStatus:
        """Return current status for one manager-resolvable identity."""
        identity = self.resolve_identity(agent_id)
        return self._status_for(identity)

    def list_statuses(self, *, active: Optional[bool] = None) -> tuple[AgentIdentityStatus, ...]:
        """Return stable status summaries for known identities."""
        statuses = tuple(self._status_for(identity) for identity in self.list_identities())
        if active is None:
            return statuses
        return tuple(status for status in statuses if status.active is active)

    def orphaned_terminal_references(self) -> tuple[OrphanedAgentTerminalReference, ...]:
        """Return terminal identity references that cannot be manager-resolved."""
        orphans: list[OrphanedAgentTerminalReference] = []
        for terminal in self._terminal_lister():
            raw_identity_id = terminal.get("agent_identity_id")
            if not isinstance(raw_identity_id, str) or not raw_identity_id.strip():
                continue
            identity_id = raw_identity_id.strip()
            try:
                self.resolve_identity(identity_id)
            except AgentIdentityConfigError:
                orphans.append(
                    OrphanedAgentTerminalReference(
                        terminal_id=str(terminal.get("id")),
                        agent_identity_id=identity_id,
                        workspace_context_id=_optional_str(terminal.get("workspace_context_id")),
                        last_active_at=_optional_datetime(terminal.get("last_active")),
                    )
                )
        return tuple(orphans)

    def _status_for(self, identity: AgentIdentity) -> AgentIdentityStatus:
        terminals = [
            terminal
            for terminal in self._terminal_lister()
            if terminal.get("agent_identity_id") == identity.id
        ]
        if not terminals:
            return AgentIdentityStatus.inactive(identity)
        terminal = max(
            terminals,
            key=lambda item: _optional_datetime(item.get("last_active")) or datetime.min,
        )
        return AgentIdentityStatus(
            agent_identity_id=identity.id,
            display_name=identity.display_name,
            agent_profile=identity.agent_profile,
            cli_provider=identity.cli_provider,
            active=True,
            active_terminal_id=_optional_str(terminal.get("id")),
            active_workspace_context_id=_optional_str(terminal.get("workspace_context_id")),
            last_active_at=_optional_datetime(terminal.get("last_active")),
        )

    def _validate_identity(self, identity: AgentIdentity) -> AgentIdentity:
        _required_token(identity.id, "agent_identity_id")
        try:
            workspace_context_data_dir(identity, "validation")
        except AgentIdentityPathError as exc:
            raise AgentIdentityConfigError(str(exc)) from exc
        _required_token(identity.display_name, f"agents.{identity.id}.display_name")
        _required_token(identity.agent_profile, f"agents.{identity.id}.agent_profile")
        _required_token(identity.cli_provider, f"agents.{identity.id}.cli_provider")
        _required_token(identity.workdir, f"agents.{identity.id}.workdir")
        _required_token(identity.session_name, f"agents.{identity.id}.session_name")
        try:
            ProviderType(identity.cli_provider)
        except ValueError as exc:
            raise AgentIdentityConfigError(
                f"agents.{identity.id}.cli_provider is not a supported provider: "
                f"{identity.cli_provider}"
            ) from exc
        try:
            self._profile_loader(identity.agent_profile)
        except Exception as exc:
            raise AgentIdentityConfigError(
                f"agents.{identity.id}.agent_profile is not available: {identity.agent_profile}"
            ) from exc
        if not isinstance(identity.workspace_context, AgentWorkspaceContextConfig):
            raise AgentIdentityConfigError(
                f"agents.{identity.id}.workspace_context must be AgentWorkspaceContextConfig"
            )
        if identity.workspace_context.enabled and not identity.workspace_context.resolver_id:
            raise AgentIdentityConfigError(
                f"agents.{identity.id}.workspace_context.resolver_id is required when enabled"
            )
        if identity.workspace_context.resolver_id is not None:
            _required_token(
                identity.workspace_context.resolver_id,
                f"agents.{identity.id}.workspace_context.resolver_id",
            )
        return identity


def create_default_agent_identity_manager(
    *,
    agents_config_path: Optional[Path] = None,
) -> AgentIdentityManager:
    """Create a manager wired to configured identities and lazy provider mappings."""
    from cli_agent_orchestrator.workspace_providers.registry import (
        candidate_identity_workspace_providers,
    )

    return AgentIdentityManager(
        configured_identities=load_agent_identity_registry(agents_config_path),
        identity_providers=cast(
            Iterable[AgentIdentityProvider],
            candidate_identity_workspace_providers(),
        ),
    )


def default_agent_identity_manager() -> AgentIdentityManager:
    """Return a fresh default manager for current config/runtime reads."""
    return create_default_agent_identity_manager()


def _required_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentIdentityConfigError(f"{label} must be a non-empty string")
    return value.strip()


def _optional_str(value: object) -> Optional[str]:
    return value if isinstance(value, str) and value.strip() else None


def _optional_datetime(value: object) -> Optional[datetime]:
    return value if isinstance(value, datetime) else None

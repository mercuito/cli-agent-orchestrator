"""Workspace setup definitions, team ownership, diagnostics, and routing."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol

from cli_agent_orchestrator.agent import Agent, AgentConfigError, AgentRegistry, load_agent_registry
from cli_agent_orchestrator.constants import CAO_HOME_DIR
from cli_agent_orchestrator.events import CaoEvent
from cli_agent_orchestrator.workspace_contexts import WorkspaceContextResolution

DEFAULT_WORKSPACE_SETUP_ID = "linear_delivery_setup"
DEFAULT_WORKSPACE_TEAM_ID = "cao_delivery"
WORKSPACE_TEAMS_FILENAME = "workspace-teams.json"
DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE = "member"
DEFAULT_WORKSPACE_TEAM_MEMBER_TOOLS = ("send_message", "handoff")


class WorkspaceSetupConfigError(ValueError):
    """Raised when workspace setup/team membership or routing fails closed."""


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
            raise WorkspaceSetupConfigError(
                f"Workspace setup {self.id} declares duplicate providers"
            )
        if isinstance(self.resolver, (tuple, list)):
            raise WorkspaceSetupConfigError(
                f"Workspace setup {self.id} must own exactly one resolver"
            )
        if not callable(self.resolver):
            raise WorkspaceSetupConfigError(f"Workspace setup {self.id} resolver must be callable")
        object.__setattr__(self, "providers", normalized)


@dataclass(frozen=True)
class WorkspaceTeamRole:
    """Persisted team-owned tool access policy for one role."""

    display_name: str
    cao_tools: tuple[str, ...] = DEFAULT_WORKSPACE_TEAM_MEMBER_TOOLS
    mcp_servers: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    providers: Mapping[str, Mapping[str, Mapping[str, Any]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required_token(self.display_name, "workspace team role display name")
        object.__setattr__(self, "cao_tools", _str_tuple(self.cao_tools, "role cao_tools"))
        object.__setattr__(
            self,
            "mcp_servers",
            {
                _required_token(name, "role mcp server name"): dict(config)
                for name, config in self.mcp_servers.items()
                if isinstance(config, Mapping)
            },
        )
        normalized_providers: dict[str, dict[str, Mapping[str, Any]]] = {}
        for provider_name, grants in self.providers.items():
            normalized_provider = _normalize_provider(provider_name)
            if not isinstance(grants, Mapping):
                raise WorkspaceSetupConfigError(
                    f"workspace team role provider {normalized_provider} grants must be an object"
                )
            normalized_providers[normalized_provider] = {
                _required_token(access_id, "role provider access id"): dict(spec)
                for access_id, spec in grants.items()
                if isinstance(spec, Mapping)
            }
        object.__setattr__(self, "providers", normalized_providers)


@dataclass(frozen=True)
class WorkspaceTeam:
    """Persisted definition of one CAO workspace team."""

    id: str
    display_name: str
    workspace_setup: str
    roles: Mapping[str, WorkspaceTeamRole] = field(default_factory=dict)
    role_assignments: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required_token(self.id, "workspace team id")
        _required_token(self.display_name, "workspace team display name")
        _required_token(self.workspace_setup, "workspace team setup id")
        roles = {
            _required_token(role_id, "workspace team role id"): role
            for role_id, role in self.roles.items()
        }
        if DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE not in roles:
            roles[DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE] = WorkspaceTeamRole(
                display_name="Member",
                cao_tools=DEFAULT_WORKSPACE_TEAM_MEMBER_TOOLS,
                mcp_servers={},
                providers={},
            )
        assignments = {
            _required_token(agent_id, "workspace team role assignment agent id"): _required_token(
                role_id,
                "workspace team role assignment role id",
            )
            for agent_id, role_id in self.role_assignments.items()
        }
        object.__setattr__(self, "roles", roles)
        object.__setattr__(self, "role_assignments", assignments)

    def role_for_member(self, agent_id: str) -> tuple[str, WorkspaceTeamRole]:
        """Return the assigned role, falling back to member for missing/deleted roles."""
        assigned = self.role_assignments.get(agent_id, DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE)
        if assigned not in self.roles:
            assigned = DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE
        return assigned, self.roles[assigned]

    def without_role(self, role_id: str) -> "WorkspaceTeam":
        """Return this team after deleting one role and moving assignments to member."""
        normalized = _required_token(role_id, "workspace team role id")
        if normalized == DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE:
            raise WorkspaceSetupConfigError("Workspace team member role cannot be deleted")
        roles = dict(self.roles)
        roles.pop(normalized, None)
        assignments = {
            agent_id: (
                DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE if assigned == normalized else assigned
            )
            for agent_id, assigned in self.role_assignments.items()
        }
        return WorkspaceTeam(
            id=self.id,
            display_name=self.display_name,
            workspace_setup=self.workspace_setup,
            roles=roles,
            role_assignments=assignments,
        )


@dataclass(frozen=True)
class WorkspaceProviderCandidateMapping:
    """Provider-owned candidate mapping before team authorization."""

    provider_name: str
    agent_id: str
    mapping_kind: str
    provider_identity: str
    provider_value: str
    payload: Any


@dataclass(frozen=True)
class WorkspaceTeamAuthorizedMapping:
    """Team-owned authorization decision for one provider candidate."""

    team_id: str
    setup_id: str
    provider_name: str
    agent_id: str
    mapping_kind: str
    provider_identity: str
    provider_value: str
    payload: Any


@dataclass(frozen=True)
class WorkspaceProviderView:
    """Team-filtered projection built by a provider adapter."""

    team_id: str
    setup_id: str
    provider_name: str
    value: Any


@dataclass(frozen=True)
class WorkspaceProviderEventResolution:
    """Resolved team-bound provider event identity."""

    team: WorkspaceTeam
    setup: WorkspaceSetup
    agent: Agent
    provider_name: str
    provider_view: WorkspaceProviderView
    provider_payload: Any


@dataclass(frozen=True)
class WorkspaceSetupDiagnostic:
    """User-visible workspace setup/team diagnostic."""

    code: str
    message: str
    team_id: str | None = None
    setup_id: str | None = None
    agent_id: str | None = None
    provider_name: str | None = None


class WorkspaceSetupProviderAdapter(Protocol):
    """Provider-owned adapter for candidate mappings and team-bound views."""

    provider_name: str

    def build_candidate_mappings(
        self, agent_registry: AgentRegistry
    ) -> tuple[WorkspaceProviderCandidateMapping, ...]:
        """Return provider-native candidate mappings for all configured agents."""

    def build_provider_view(
        self,
        *,
        team: WorkspaceTeam,
        setup: WorkspaceSetup,
        authorized_mappings: tuple[WorkspaceTeamAuthorizedMapping, ...],
        agent_registry: AgentRegistry,
    ) -> WorkspaceProviderView:
        """Return a team-filtered provider-native view."""

    def resolve_event_agent_id(
        self,
        *,
        provider_view: WorkspaceProviderView,
        event: CaoEvent,
    ) -> tuple[str, Any]:
        """Return the team-addressable agent id and provider payload for an event."""

    def describe_event_identity(self, event: CaoEvent) -> str:
        """Return a concise provider-native event identity for diagnostics."""

    def candidate_mappings_for_event(
        self,
        *,
        event: CaoEvent,
        candidates: tuple[WorkspaceProviderCandidateMapping, ...],
    ) -> tuple[WorkspaceProviderCandidateMapping, ...]:
        """Return candidate mappings that match the provider-native event identity."""


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


class WorkspaceTeamStore:
    """Localized persisted owner for dashboard-managed workspace teams."""

    def __init__(
        self,
        path: str | Path,
        *,
        bootstrap_teams: tuple[WorkspaceTeam, ...] = (),
    ) -> None:
        self._path = Path(path)
        self._bootstrap_teams = bootstrap_teams

    @property
    def path(self) -> Path:
        return self._path

    def list(self) -> tuple[WorkspaceTeam, ...]:
        self._ensure_seeded()
        return tuple(sorted(self._read().values(), key=lambda team: team.id))

    def get(self, team_id: str) -> WorkspaceTeam:
        normalized = _required_token(team_id, "workspace team id")
        teams = self._read_after_seed()
        try:
            return teams[normalized]
        except KeyError as exc:
            raise WorkspaceSetupConfigError(f"Unknown workspace team: {normalized}") from exc

    def upsert(self, team: WorkspaceTeam) -> WorkspaceTeam:
        teams = self._read_after_seed()
        teams[team.id] = team
        self._write(teams)
        return team

    def _read_after_seed(self) -> dict[str, WorkspaceTeam]:
        self._ensure_seeded()
        return self._read()

    def _ensure_seeded(self) -> None:
        teams = self._read()
        changed = False
        for team in self._bootstrap_teams:
            if team.id not in teams:
                teams[team.id] = team
                changed = True
        if changed:
            self._write(teams)

    def _read(self) -> dict[str, WorkspaceTeam]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text())
        except json.JSONDecodeError as exc:
            raise WorkspaceSetupConfigError(
                f"Invalid workspace team store {self._path}: {exc}"
            ) from exc
        if not isinstance(raw, Mapping):
            raise WorkspaceSetupConfigError(f"Workspace team store {self._path} must be an object")
        raw_teams = raw.get("teams", [])
        if not isinstance(raw_teams, list):
            raise WorkspaceSetupConfigError(
                f"Workspace team store {self._path} field teams must be a list"
            )
        teams: dict[str, WorkspaceTeam] = {}
        for raw_team in raw_teams:
            if not isinstance(raw_team, Mapping):
                raise WorkspaceSetupConfigError("Workspace team entries must be objects")
            team = WorkspaceTeam(
                id=_required_json_token(raw_team, "id", "workspace team id"),
                display_name=_required_json_token(
                    raw_team,
                    "display_name",
                    "workspace team display name",
                ),
                workspace_setup=_required_json_token(
                    raw_team,
                    "workspace_setup",
                    "workspace team setup id",
                ),
                roles=_roles_from_json(raw_team.get("roles", {})),
                role_assignments=_str_mapping(
                    raw_team.get("role_assignments", {}),
                    "workspace team role_assignments",
                ),
            )
            if team.id in teams:
                raise WorkspaceSetupConfigError(f"Duplicate workspace team: {team.id}")
            teams[team.id] = team
        return teams

    def _write(self, teams: Mapping[str, WorkspaceTeam]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "teams": [
                {
                    "id": team.id,
                    "display_name": team.display_name,
                    "workspace_setup": team.workspace_setup,
                    "roles": {
                        role_id: _role_to_json(role)
                        for role_id, role in sorted(team.roles.items())
                    },
                    "role_assignments": dict(sorted(team.role_assignments.items())),
                }
                for team in sorted(teams.values(), key=lambda item: item.id)
            ]
        }
        with tempfile.NamedTemporaryFile(
            "w",
            dir=self._path.parent,
            prefix=f"{self._path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            json.dump(payload, tmp_file, indent=2, sort_keys=True)
            tmp_file.write("\n")
            tmp_path = Path(tmp_file.name)
        tmp_path.replace(self._path)


class WorkspaceTeamRegistry:
    """Read-through lookup over the localized team store."""

    def __init__(self, store: WorkspaceTeamStore) -> None:
        self._store = store

    def get(self, team_id: str) -> WorkspaceTeam:
        return self._store.get(team_id)

    def all(self) -> tuple[WorkspaceTeam, ...]:
        return self._store.list()


class WorkspaceTeamService:
    """Public create, update, list, validate, and diagnostic API for teams."""

    def __init__(
        self,
        *,
        setup_registry: WorkspaceSetupRegistry,
        team_store: WorkspaceTeamStore,
        agent_registry: AgentRegistry,
        available_providers: tuple[str, ...],
    ) -> None:
        self._setup_registry = setup_registry
        self._team_store = team_store
        self._team_registry = WorkspaceTeamRegistry(team_store)
        self._agent_registry = agent_registry
        self._available_providers = {
            _normalize_provider(provider) for provider in available_providers
        }

    @property
    def team_registry(self) -> WorkspaceTeamRegistry:
        return self._team_registry

    def list_teams(self) -> tuple[WorkspaceTeam, ...]:
        return self._team_registry.all()

    def create_or_update_team(
        self,
        *,
        team_id: str,
        display_name: str,
        workspace_setup: str,
        roles: Mapping[str, WorkspaceTeamRole] | None = None,
        role_assignments: Mapping[str, str] | None = None,
    ) -> WorkspaceTeam:
        try:
            existing = self._team_registry.get(team_id)
        except WorkspaceSetupConfigError:
            existing = None
        team = WorkspaceTeam(
            id=team_id,
            display_name=display_name,
            workspace_setup=workspace_setup,
            roles=roles if roles is not None else (existing.roles if existing else {}),
            role_assignments=(
                role_assignments
                if role_assignments is not None
                else (existing.role_assignments if existing else {})
            ),
        )
        self._setup_registry.get(team.workspace_setup)
        return self._team_store.upsert(team)

    def assign_role(self, *, team_id: str, agent_id: str, role_id: str) -> WorkspaceTeam:
        team = self._team_registry.get(team_id)
        normalized_role = _required_token(role_id, "workspace team role id")
        if normalized_role not in team.roles:
            raise WorkspaceSetupConfigError(
                f"Unknown workspace team role {normalized_role} for team {team.id}"
            )
        assignments = dict(team.role_assignments)
        assignments[_required_token(agent_id, "agent id")] = normalized_role
        return self._team_store.upsert(
            WorkspaceTeam(
                id=team.id,
                display_name=team.display_name,
                workspace_setup=team.workspace_setup,
                roles=team.roles,
                role_assignments=assignments,
            )
        )

    def delete_role_assignment(self, *, team_id: str, agent_id: str) -> WorkspaceTeam:
        team = self._team_registry.get(team_id)
        assignments = dict(team.role_assignments)
        assignments.pop(_required_token(agent_id, "agent id"), None)
        return self._team_store.upsert(
            WorkspaceTeam(
                id=team.id,
                display_name=team.display_name,
                workspace_setup=team.workspace_setup,
                roles=team.roles,
                role_assignments=assignments,
            )
        )

    def delete_role(self, *, team_id: str, role_id: str) -> WorkspaceTeam:
        team = self._team_registry.get(team_id)
        return self._team_store.upsert(team.without_role(role_id))

    def setup_for_team(self, team_id: str) -> WorkspaceSetup:
        team = self._team_registry.get(team_id)
        return self._setup_registry.get(team.workspace_setup)

    def diagnostics(self) -> tuple[WorkspaceSetupDiagnostic, ...]:
        diagnostics: list[WorkspaceSetupDiagnostic] = []
        for team in self._team_registry.all():
            try:
                setup = self._setup_registry.get(team.workspace_setup)
            except WorkspaceSetupConfigError as exc:
                diagnostics.append(
                    WorkspaceSetupDiagnostic(
                        code="unknown_setup",
                        message=str(exc),
                        team_id=team.id,
                        setup_id=team.workspace_setup,
                    )
                )
                continue
            for provider_name in setup.providers:
                if provider_name not in self._available_providers:
                    diagnostics.append(
                        WorkspaceSetupDiagnostic(
                            code="unavailable_provider",
                            message=(
                                f"Workspace team {team.id} setup {setup.id} requires "
                                f"unavailable provider {provider_name}"
                            ),
                            team_id=team.id,
                            setup_id=setup.id,
                            provider_name=provider_name,
                        )
                    )
        for agent in self._agent_registry.all().values():
            for message in agent.workspace.diagnostics:
                diagnostics.append(
                    WorkspaceSetupDiagnostic(
                        code="legacy_workspace_config",
                        message=message,
                        team_id=agent.workspace.team,
                        agent_id=agent.id,
                    )
                )
            team_id = agent.workspace.team
            if team_id is None:
                continue
            try:
                team = self._team_registry.get(team_id)
                self._setup_registry.get(team.workspace_setup)
            except WorkspaceSetupConfigError as exc:
                diagnostics.append(
                    WorkspaceSetupDiagnostic(
                        code="unknown_team",
                        message=str(exc),
                        team_id=team_id,
                        agent_id=agent.id,
                    )
                )
        return tuple(diagnostics)


class WorkspaceCollaborationManager:
    """Authoritative runtime service for team membership and collaboration."""

    def __init__(
        self,
        *,
        setup_registry: WorkspaceSetupRegistry,
        team_registry: WorkspaceTeamRegistry,
        agent_registry: AgentRegistry,
        provider_adapters: Mapping[str, WorkspaceSetupProviderAdapter],
        available_providers: tuple[str, ...] | None = None,
    ) -> None:
        self._setup_registry = setup_registry
        self._team_registry = team_registry
        self._agent_registry = agent_registry
        self._provider_adapters = {
            _normalize_provider(name): adapter for name, adapter in provider_adapters.items()
        }
        self._available_providers = (
            set(self._provider_adapters)
            if available_providers is None
            else set(available_providers)
        )
        if available_providers is not None:
            self._available_providers = {
                _normalize_provider(provider_name) for provider_name in available_providers
            }

    @property
    def agent_registry(self) -> AgentRegistry:
        return self._agent_registry

    def team_for_agent(self, agent: Agent) -> WorkspaceTeam | None:
        if agent.workspace.team is None:
            return None
        return self._team_registry.get(agent.workspace.team)

    def setup_for_agent(self, agent: Agent) -> WorkspaceSetup | None:
        team = self.team_for_agent(agent)
        if team is None:
            return None
        return self._setup_registry.get(team.workspace_setup)

    def diagnostics(self) -> tuple[WorkspaceSetupDiagnostic, ...]:
        service = WorkspaceTeamService(
            setup_registry=self._setup_registry,
            team_store=_ReadOnlyTeamStore(self._team_registry.all()),
            agent_registry=self._agent_registry,
            available_providers=tuple(self._available_providers),
        )
        diagnostics = list(service.diagnostics())
        for team in self._team_registry.all():
            try:
                setup = self._setup_registry.get(team.workspace_setup)
            except WorkspaceSetupConfigError:
                continue
            diagnostics.extend(self._pruned_mapping_diagnostics(team, setup))
        return tuple(diagnostics)

    def provider_view(self, team_id: str, provider_name: str) -> WorkspaceProviderView:
        team = self._team_registry.get(team_id)
        setup = self._setup_registry.get(team.workspace_setup)
        normalized_provider = _normalize_provider(provider_name)
        if normalized_provider not in setup.providers:
            raise WorkspaceSetupConfigError(
                f"Workspace team {team.id} setup {setup.id} does not include provider "
                f"{normalized_provider}"
            )
        if normalized_provider not in self._available_providers:
            raise WorkspaceSetupConfigError(
                f"Workspace team {team.id} setup {setup.id} requires unavailable provider "
                f"{normalized_provider}"
            )
        adapter = self._adapter(normalized_provider)
        return adapter.build_provider_view(
            team=team,
            setup=setup,
            authorized_mappings=self.authorized_mappings(team.id, normalized_provider),
            agent_registry=self._agent_registry,
        )

    def authorized_mappings(
        self, team_id: str, provider_name: str
    ) -> tuple[WorkspaceTeamAuthorizedMapping, ...]:
        team = self._team_registry.get(team_id)
        setup = self._setup_registry.get(team.workspace_setup)
        normalized_provider = _normalize_provider(provider_name)
        if normalized_provider not in setup.providers:
            raise WorkspaceSetupConfigError(
                f"Workspace team {team.id} setup {setup.id} does not include provider "
                f"{normalized_provider}"
            )
        members = self._team_member_ids(team.id)
        adapter = self._adapter(normalized_provider)
        authorized: list[WorkspaceTeamAuthorizedMapping] = []
        for candidate in adapter.build_candidate_mappings(self._agent_registry):
            if candidate.agent_id not in members:
                continue
            authorized.append(
                WorkspaceTeamAuthorizedMapping(
                    team_id=team.id,
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
        _normalize_provider(provider_name)
        return frozenset()

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
        for team in self._team_registry.all():
            try:
                setup = self._setup_registry.get(team.workspace_setup)
            except WorkspaceSetupConfigError as exc:
                errors.append(str(exc))
                continue
            if normalized_provider not in setup.providers:
                continue
            try:
                view = self.provider_view(team.id, normalized_provider)
                agent_id, payload = adapter.resolve_event_agent_id(
                    provider_view=view,
                    event=event,
                )
                matches.append(
                    WorkspaceProviderEventResolution(
                        team=team,
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
            teams = ", ".join(match.team.id for match in matches)
            raise WorkspaceSetupConfigError(
                f"Provider event resolved in multiple workspace teams for "
                f"{normalized_provider}: {teams}"
            )
        identity = adapter.describe_event_identity(event)
        detail = "; ".join(errors) if errors else "no team-authorized mapping"
        candidate_detail = self._provider_event_candidate_detail(
            adapter=adapter,
            provider_name=normalized_provider,
            event=event,
        )
        if candidate_detail:
            detail = f"{detail}; {candidate_detail}"
        raise WorkspaceSetupConfigError(
            f"{normalized_provider} provider identity {identity} is authenticated but not "
            f"CAO-addressable in any workspace team: {detail}"
        )

    def require_same_team_collaboration(
        self,
        *,
        sender: Agent,
        receiver: Agent,
    ) -> None:
        sender_team = sender.workspace.team
        receiver_team = receiver.workspace.team
        if sender_team and receiver_team and sender_team == receiver_team:
            team = self._team_registry.get(sender_team)
            self._setup_registry.get(team.workspace_setup)
            return
        raise WorkspaceSetupConfigError(
            f"Workspace team collaboration rejected: sender {sender.id} team "
            f"{sender_team or 'none'} cannot collaborate with receiver {receiver.id} team "
            f"{receiver_team or 'none'}"
        )

    def _team_member_ids(self, team_id: str) -> set[str]:
        return {
            agent.id
            for agent in self._agent_registry.all().values()
            if agent.workspace.team == team_id
        }

    def _adapter(self, provider_name: str) -> WorkspaceSetupProviderAdapter:
        try:
            return self._provider_adapters[provider_name]
        except KeyError as exc:
            raise WorkspaceSetupConfigError(
                f"Unavailable workspace provider: {provider_name}"
            ) from exc

    def _pruned_mapping_diagnostics(
        self, team: WorkspaceTeam, setup: WorkspaceSetup
    ) -> tuple[WorkspaceSetupDiagnostic, ...]:
        diagnostics: list[WorkspaceSetupDiagnostic] = []
        member_ids = self._team_member_ids(team.id)
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
                            f"Workspace team {team.id} pruned {provider_name} "
                            f"{candidate.provider_identity} {candidate.provider_value} for "
                            f"out-of-team agent {candidate.agent_id}"
                        ),
                        team_id=team.id,
                        setup_id=setup.id,
                        agent_id=candidate.agent_id,
                        provider_name=provider_name,
                    )
                )
        return tuple(diagnostics)

    def _provider_event_candidate_detail(
        self,
        *,
        adapter: WorkspaceSetupProviderAdapter,
        provider_name: str,
        event: CaoEvent,
    ) -> str | None:
        candidates = adapter.candidate_mappings_for_event(
            event=event,
            candidates=adapter.build_candidate_mappings(self._agent_registry),
        )
        if not candidates:
            return None
        details: list[str] = []
        seen_agent_ids: set[str] = set()
        for candidate in candidates:
            if candidate.agent_id in seen_agent_ids:
                continue
            seen_agent_ids.add(candidate.agent_id)
            details.append(
                self._provider_event_candidate_agent_detail(
                    provider_name=provider_name,
                    candidate=candidate,
                )
            )
        return "; ".join(details)

    def _provider_event_candidate_agent_detail(
        self,
        *,
        provider_name: str,
        candidate: WorkspaceProviderCandidateMapping,
    ) -> str:
        try:
            agent = self._agent_registry.get(candidate.agent_id)
        except AgentConfigError as exc:
            return (
                f"{provider_name} {candidate.provider_identity} {candidate.provider_value} "
                f"maps to unknown CAO agent {candidate.agent_id}: {exc}"
            )
        team_id = agent.workspace.team
        if team_id is None:
            return (
                f"{provider_name} {candidate.provider_identity} {candidate.provider_value} "
                f"maps to agent {agent.id}, but that agent has no workspace team"
            )
        try:
            team = self._team_registry.get(team_id)
            setup = self._setup_registry.get(team.workspace_setup)
        except WorkspaceSetupConfigError as exc:
            return (
                f"{provider_name} {candidate.provider_identity} {candidate.provider_value} "
                f"maps to agent {agent.id} in workspace team {team_id}, but {exc}"
            )
        if provider_name not in setup.providers:
            return (
                f"{provider_name} {candidate.provider_identity} {candidate.provider_value} "
                f"maps to agent {agent.id} in workspace team {team.id}, but setup {setup.id} "
                f"does not include provider {provider_name}"
            )
        return (
            f"{provider_name} {candidate.provider_identity} {candidate.provider_value} maps to "
            f"agent {agent.id} in workspace team {team.id}, but that team's provider view did "
            "not authorize the identity"
        )


class _ReadOnlyTeamStore(WorkspaceTeamStore):
    def __init__(self, teams: tuple[WorkspaceTeam, ...]) -> None:
        self._teams = {team.id: team for team in teams}

    def list(self) -> tuple[WorkspaceTeam, ...]:
        return tuple(sorted(self._teams.values(), key=lambda team: team.id))

    def get(self, team_id: str) -> WorkspaceTeam:
        normalized = _required_token(team_id, "workspace team id")
        try:
            return self._teams[normalized]
        except KeyError as exc:
            raise WorkspaceSetupConfigError(f"Unknown workspace team: {normalized}") from exc

    def upsert(self, team: WorkspaceTeam) -> WorkspaceTeam:
        raise WorkspaceSetupConfigError("read-only workspace team store")


def default_workspace_setup_registry() -> WorkspaceSetupRegistry:
    from cli_agent_orchestrator.linear.workspace_context_resolver import (
        resolve_linear_workspace_event,
    )

    return WorkspaceSetupRegistry(
        (
            WorkspaceSetup(
                id=DEFAULT_WORKSPACE_SETUP_ID,
                display_name="Linear Delivery Setup",
                providers=("linear",),
                resolver=resolve_linear_workspace_event,
            ),
        )
    )


def default_workspace_team_store(
    *,
    path: str | Path | None = None,
) -> WorkspaceTeamStore:
    return WorkspaceTeamStore(
        path or (CAO_HOME_DIR / WORKSPACE_TEAMS_FILENAME),
        bootstrap_teams=(
            WorkspaceTeam(
                id=DEFAULT_WORKSPACE_TEAM_ID,
                display_name="CAO Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
            ),
        ),
    )


def default_workspace_team_service(
    *,
    agent_registry: AgentRegistry | None = None,
    team_store_path: str | Path | None = None,
) -> WorkspaceTeamService:
    from cli_agent_orchestrator.linear.workspace_setup_adapter import LinearWorkspaceSetupAdapter

    registry = agent_registry or load_agent_registry()
    setup_registry = default_workspace_setup_registry()
    adapters = {"linear": LinearWorkspaceSetupAdapter()}
    return WorkspaceTeamService(
        setup_registry=setup_registry,
        team_store=default_workspace_team_store(path=team_store_path),
        agent_registry=registry,
        available_providers=tuple(adapters),
    )


def default_workspace_collaboration_manager(
    *,
    agent_registry: AgentRegistry | None = None,
    team_store_path: str | Path | None = None,
) -> WorkspaceCollaborationManager:
    from cli_agent_orchestrator.linear.workspace_setup_adapter import LinearWorkspaceSetupAdapter

    registry = agent_registry or load_agent_registry()
    setup_registry = default_workspace_setup_registry()
    team_store = default_workspace_team_store(path=team_store_path)
    return WorkspaceCollaborationManager(
        setup_registry=setup_registry,
        team_registry=WorkspaceTeamRegistry(team_store),
        agent_registry=registry,
        provider_adapters={"linear": LinearWorkspaceSetupAdapter()},
    )


def _required_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceSetupConfigError(f"{label} must be a non-empty string")
    return value.strip()


def _required_json_token(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise WorkspaceSetupConfigError(f"{label} must be a non-empty string")
    return _required_token(value, label)


def _normalize_provider(value: str) -> str:
    return _required_token(value, "workspace provider name").lower()


def _str_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise WorkspaceSetupConfigError(f"{label} must be a string list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise WorkspaceSetupConfigError(f"{label} must contain only non-empty strings")
        result.append(item.strip())
    return tuple(dict.fromkeys(result))


def _str_mapping(value: Any, label: str) -> Mapping[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise WorkspaceSetupConfigError(f"{label} must be an object")
    return {
        _required_token(str(key), f"{label} key"): _required_token(str(item), f"{label} value")
        for key, item in value.items()
    }


def _roles_from_json(value: Any) -> Mapping[str, WorkspaceTeamRole]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise WorkspaceSetupConfigError("workspace team roles must be an object")
    roles: dict[str, WorkspaceTeamRole] = {}
    for role_id, role_value in value.items():
        if not isinstance(role_value, Mapping):
            raise WorkspaceSetupConfigError("workspace team role entries must be objects")
        roles[_required_token(str(role_id), "workspace team role id")] = WorkspaceTeamRole(
            display_name=_required_json_token(
                role_value,
                "display_name",
                "workspace team role display name",
            ),
            cao_tools=_str_tuple(role_value.get("cao_tools", []), "workspace team role cao_tools"),
            mcp_servers={
                str(name): dict(config)
                for name, config in (
                    role_value.get("mcp_servers", {}) if isinstance(role_value, Mapping) else {}
                ).items()
                if isinstance(config, Mapping)
            },
            providers={
                str(provider_name): {
                    str(access_id): dict(spec)
                    for access_id, spec in grants.items()
                    if isinstance(spec, Mapping)
                }
                for provider_name, grants in (
                    role_value.get("providers", {}) if isinstance(role_value, Mapping) else {}
                ).items()
                if isinstance(grants, Mapping)
            },
        )
    return roles


def _role_to_json(role: WorkspaceTeamRole) -> Mapping[str, Any]:
    return {
        "display_name": role.display_name,
        "cao_tools": list(role.cao_tools),
        "mcp_servers": dict(role.mcp_servers),
        "providers": {
            provider_name: {access_id: dict(spec) for access_id, spec in grants.items()}
            for provider_name, grants in role.providers.items()
        },
    }

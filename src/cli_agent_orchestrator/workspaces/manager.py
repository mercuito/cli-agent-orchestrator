"""Workspace definitions, team ownership, diagnostics, and routing."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Protocol

import cli_agent_orchestrator.agent as agent_config
from cli_agent_orchestrator.agent import (
    Agent,
    AgentConfigError,
    AgentRegistry,
    AgentWorkspaceConfig,
    load_agent,
    load_agent_registry,
    patch_agent_config,
)
from cli_agent_orchestrator.constants import CAO_HOME_DIR
from cli_agent_orchestrator.events import CaoEvent
from cli_agent_orchestrator.workspace_contexts import WorkspaceContextResolution

DEFAULT_WORKSPACE_ID = "linear_delivery"
LEGACY_WORKSPACE_IDS = {"linear_delivery_setup": DEFAULT_WORKSPACE_ID}
DEFAULT_WORKSPACE_TEAM_ID = "cao_delivery"
WORKSPACE_TEAMS_FILENAME = "workspace-teams.json"
DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE = "member"
DEFAULT_WORKSPACE_TEAM_MEMBER_TOOLS = ("send_message", "handoff")


class WorkspaceConfigError(ValueError):
    """Raised when workspace/team membership or routing fails closed."""


class WorkspaceContextResolver(Protocol):
    """Resolve one provider/runtime event into one authoritative workspace context."""

    def __call__(self, event: CaoEvent) -> WorkspaceContextResolution | None:
        """Return the resolved workspace context for ``event``."""


@dataclass(frozen=True)
class Workspace:
    """Code-owned definition of one CAO workspace."""

    id: str
    display_name: str
    providers: tuple[str, ...]
    resolver: WorkspaceContextResolver

    def __post_init__(self) -> None:
        _required_token(self.id, "workspace id")
        _required_token(self.display_name, "workspace display name")
        if not self.providers:
            raise WorkspaceConfigError(f"Workspace {self.id} must declare providers")
        normalized = tuple(_normalize_provider(provider) for provider in self.providers)
        if len(set(normalized)) != len(normalized):
            raise WorkspaceConfigError(
                f"Workspace {self.id} declares duplicate providers"
            )
        if isinstance(self.resolver, (tuple, list)):
            raise WorkspaceConfigError(
                f"Workspace {self.id} must own exactly one resolver"
            )
        if not callable(self.resolver):
            raise WorkspaceConfigError(f"Workspace {self.id} resolver must be callable")
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
                raise WorkspaceConfigError(
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
    workspace: str
    roles: Mapping[str, WorkspaceTeamRole] = field(default_factory=dict)
    role_assignments: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required_token(self.id, "workspace team id")
        _required_token(self.display_name, "workspace team display name")
        _required_token(self.workspace, "workspace team workspace id")
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
            raise WorkspaceConfigError("Workspace team member role cannot be deleted")
        roles = dict(self.roles)
        roles.pop(normalized, None)
        assignments = {
            agent_id: (DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE if assigned == normalized else assigned)
            for agent_id, assigned in self.role_assignments.items()
        }
        return WorkspaceTeam(
            id=self.id,
            display_name=self.display_name,
            workspace=self.workspace,
            roles=roles,
            role_assignments=assignments,
        )


@dataclass(frozen=True)
class WorkspaceToolProviderCandidateMapping:
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
    workspace_id: str
    provider_name: str
    agent_id: str
    mapping_kind: str
    provider_identity: str
    provider_value: str
    payload: Any


@dataclass(frozen=True)
class WorkspaceToolProviderView:
    """Team-filtered projection built by a provider adapter."""

    team_id: str
    workspace_id: str
    provider_name: str
    value: Any


@dataclass(frozen=True)
class WorkspaceToolProviderEventResolution:
    """Resolved team-bound provider event identity."""

    team: WorkspaceTeam
    workspace: Workspace
    agent: Agent
    provider_name: str
    provider_view: WorkspaceToolProviderView
    provider_payload: Any


@dataclass(frozen=True)
class WorkspaceDiagnostic:
    """User-visible workspace/team diagnostic."""

    code: str
    message: str
    team_id: str | None = None
    workspace_id: str | None = None
    agent_id: str | None = None
    provider_name: str | None = None


class WorkspaceToolProviderAdapter(Protocol):
    """Provider-owned adapter for candidate mappings and team-bound views."""

    provider_name: str

    def build_candidate_mappings(
        self, agent_registry: AgentRegistry
    ) -> tuple[WorkspaceToolProviderCandidateMapping, ...]:
        """Return provider-native candidate mappings for all configured agents."""

    def build_provider_view(
        self,
        *,
        team: WorkspaceTeam,
        workspace: Workspace,
        authorized_mappings: tuple[WorkspaceTeamAuthorizedMapping, ...],
        agent_registry: AgentRegistry,
    ) -> WorkspaceToolProviderView:
        """Return a team-filtered provider-native view."""

    def resolve_event_agent_id(
        self,
        *,
        provider_view: WorkspaceToolProviderView,
        event: CaoEvent,
    ) -> tuple[str, Any]:
        """Return the team-addressable agent id and provider payload for an event."""

    def describe_event_identity(self, event: CaoEvent) -> str:
        """Return a concise provider-native event identity for diagnostics."""

    def candidate_mappings_for_event(
        self,
        *,
        event: CaoEvent,
        candidates: tuple[WorkspaceToolProviderCandidateMapping, ...],
    ) -> tuple[WorkspaceToolProviderCandidateMapping, ...]:
        """Return candidate mappings that match the provider-native event identity."""


class WorkspaceRegistry:
    """Code-owned lookup of workspace definitions."""

    def __init__(self, workspaces: tuple[Workspace, ...] = ()) -> None:
        self._workspaces: dict[str, Workspace] = {}
        for workspace in workspaces:
            self.register(workspace)

    def register(self, workspace: Workspace) -> None:
        if workspace.id in self._workspaces:
            raise WorkspaceConfigError(f"Duplicate workspace: {workspace.id}")
        self._workspaces[workspace.id] = workspace

    def get(self, workspace_id: str) -> Workspace:
        normalized = _required_token(workspace_id, "workspace id")
        try:
            return self._workspaces[normalized]
        except KeyError as exc:
            raise WorkspaceConfigError(f"Unknown workspace: {normalized}") from exc

    def all(self) -> tuple[Workspace, ...]:
        return tuple(self._workspaces[key] for key in sorted(self._workspaces))


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
            raise WorkspaceConfigError(f"Unknown workspace team: {normalized}") from exc

    def upsert(self, team: WorkspaceTeam) -> WorkspaceTeam:
        teams = self._read_after_seed()
        teams[team.id] = team
        self._write(teams)
        return team

    def update_many(
        self,
        *,
        upsert_teams: Iterable[WorkspaceTeam] = (),
        delete_team_ids: Iterable[str] = (),
    ) -> dict[str, WorkspaceTeam]:
        teams = self._read_after_seed()
        deleted: set[str] = set()
        for team_id in delete_team_ids:
            normalized = _required_token(team_id, "workspace team id")
            if normalized not in teams:
                raise WorkspaceConfigError(f"Unknown workspace team: {normalized}")
            teams.pop(normalized)
            deleted.add(normalized)
        changed: dict[str, WorkspaceTeam] = {}
        for team in upsert_teams:
            if team.id in deleted:
                raise WorkspaceConfigError(
                    f"Workspace team {team.id} cannot be upserted and deleted together"
                )
            teams[team.id] = team
            changed[team.id] = team
        self._write(teams)
        return changed

    def delete(self, team_id: str) -> WorkspaceTeam:
        team = self.get(team_id)
        self.update_many(delete_team_ids=(team.id,))
        return team

    def _read_after_seed(self) -> dict[str, WorkspaceTeam]:
        self._ensure_seeded()
        return self._read()

    def _ensure_seeded(self) -> None:
        if self._path.exists():
            return
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
            raise WorkspaceConfigError(
                f"Invalid workspace team store {self._path}: {exc}"
            ) from exc
        if not isinstance(raw, Mapping):
            raise WorkspaceConfigError(f"Workspace team store {self._path} must be an object")
        raw_teams = raw.get("teams", [])
        if not isinstance(raw_teams, list):
            raise WorkspaceConfigError(
                f"Workspace team store {self._path} field teams must be a list"
            )
        teams: dict[str, WorkspaceTeam] = {}
        needs_migration = False
        for raw_team in raw_teams:
            if not isinstance(raw_team, Mapping):
                raise WorkspaceConfigError("Workspace team entries must be objects")
            workspace_id, migrated = _workspace_from_json(raw_team)
            needs_migration = needs_migration or migrated
            team = WorkspaceTeam(
                id=_required_json_token(raw_team, "id", "workspace team id"),
                display_name=_required_json_token(
                    raw_team,
                    "display_name",
                    "workspace team display name",
                ),
                workspace=workspace_id,
                roles=_roles_from_json(raw_team.get("roles", {})),
                role_assignments=_str_mapping(
                    raw_team.get("role_assignments", {}),
                    "workspace team role_assignments",
                ),
            )
            if team.id in teams:
                raise WorkspaceConfigError(f"Duplicate workspace team: {team.id}")
            teams[team.id] = team
        if needs_migration:
            self._write(teams)
        return teams

    def _write(self, teams: Mapping[str, WorkspaceTeam]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "teams": [
                {
                    "id": team.id,
                    "display_name": team.display_name,
                    "workspace": team.workspace,
                    "roles": {
                        role_id: _role_to_json(role) for role_id, role in sorted(team.roles.items())
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
        workspace_registry: WorkspaceRegistry,
        team_store: WorkspaceTeamStore,
        agent_registry: AgentRegistry,
        available_providers: tuple[str, ...],
        agents_root: str | Path | None = None,
    ) -> None:
        self._workspace_registry = workspace_registry
        self._team_store = team_store
        self._team_registry = WorkspaceTeamRegistry(team_store)
        self._agent_registry = agent_registry
        self._agents_root = Path(agents_root) if agents_root is not None else None
        self._agent_registry_file_backed = self._agents_root is not None
        self._available_providers = {
            _normalize_provider(provider) for provider in available_providers
        }

    @property
    def team_registry(self) -> WorkspaceTeamRegistry:
        return self._team_registry

    def list_teams(self) -> tuple[WorkspaceTeam, ...]:
        return self._team_registry.all()

    def get_team(self, team_id: str) -> WorkspaceTeam:
        return self._team_registry.get(team_id)

    def create_team(
        self,
        *,
        team_id: str,
        display_name: str,
        workspace: str,
    ) -> WorkspaceTeam:
        normalized = _required_token(team_id, "workspace team id")
        try:
            self._team_registry.get(normalized)
        except WorkspaceConfigError:
            pass
        else:
            raise WorkspaceConfigError(f"Workspace team already exists: {normalized}")
        team = WorkspaceTeam(
            id=normalized,
            display_name=display_name,
            workspace=workspace,
        )
        self._workspace_registry.get(team.workspace)
        return self._team_store.upsert(team)

    def update_team_metadata(
        self,
        *,
        team_id: str,
        display_name: str,
        workspace: str,
    ) -> WorkspaceTeam:
        existing = self._team_registry.get(team_id)
        team = WorkspaceTeam(
            id=existing.id,
            display_name=display_name,
            workspace=workspace,
            roles=existing.roles,
            role_assignments=existing.role_assignments,
        )
        self._workspace_registry.get(team.workspace)
        return self._team_store.upsert(team)

    def delete_team(self, team_id: str) -> WorkspaceTeam:
        team = self._team_registry.get(team_id)
        members = self._member_ids_for_team(team.id)
        if members:
            raise WorkspaceConfigError(
                f"Workspace team {team.id} cannot be deleted while members exist: "
                f"{', '.join(sorted(members))}"
            )
        return self._team_store.delete(team.id)

    def create_or_update_team(
        self,
        *,
        team_id: str,
        display_name: str,
        workspace: str,
        roles: Mapping[str, WorkspaceTeamRole] | None = None,
        role_assignments: Mapping[str, str] | None = None,
    ) -> WorkspaceTeam:
        try:
            existing = self._team_registry.get(team_id)
        except WorkspaceConfigError:
            existing = None
        team = WorkspaceTeam(
            id=team_id,
            display_name=display_name,
            workspace=workspace,
            roles=roles if roles is not None else (existing.roles if existing else {}),
            role_assignments=(
                role_assignments
                if role_assignments is not None
                else (existing.role_assignments if existing else {})
            ),
        )
        self._workspace_registry.get(team.workspace)
        self._validate_role_assignments(team)
        return self._team_store.upsert(team)

    def put_role(
        self,
        *,
        team_id: str,
        role_id: str,
        role: WorkspaceTeamRole,
    ) -> WorkspaceTeam:
        team = self._team_registry.get(team_id)
        normalized_role = _required_token(role_id, "workspace team role id")
        roles = dict(team.roles)
        roles[normalized_role] = role
        updated = WorkspaceTeam(
            id=team.id,
            display_name=team.display_name,
            workspace=team.workspace,
            roles=roles,
            role_assignments=team.role_assignments,
        )
        self._validate_role_assignments(updated)
        return self._team_store.upsert(updated)

    def assign_role(self, *, team_id: str, agent_id: str, role_id: str) -> WorkspaceTeam:
        team = self._team_registry.get(team_id)
        normalized_role = _required_token(role_id, "workspace team role id")
        if normalized_role not in team.roles:
            raise WorkspaceConfigError(
                f"Unknown workspace team role {normalized_role} for team {team.id}"
            )
        assignments = dict(team.role_assignments)
        assignments[_required_token(agent_id, "agent id")] = normalized_role
        return self._team_store.upsert(
            WorkspaceTeam(
                id=team.id,
                display_name=team.display_name,
                workspace=team.workspace,
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
                workspace=team.workspace,
                roles=team.roles,
                role_assignments=assignments,
            )
        )

    def delete_role(self, *, team_id: str, role_id: str) -> WorkspaceTeam:
        team = self._team_registry.get(team_id)
        return self._team_store.upsert(team.without_role(role_id))

    def assign_member(
        self,
        *,
        team_id: str,
        agent_id: str,
        role_id: str | None = None,
    ) -> WorkspaceTeam:
        team = self._team_registry.get(team_id)
        self._workspace_registry.get(team.workspace)
        agent = self._load_agent_for_update(agent_id)
        normalized_role = (
            DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE
            if role_id is None
            else _required_token(role_id, "workspace team role id")
        )
        if normalized_role not in team.roles:
            raise WorkspaceConfigError(
                f"Unknown workspace team role {normalized_role} for team {team.id}"
            )

        old_team = self._existing_team_or_none(agent.workspace.team)
        updated_target = _team_with_role_assignment(team, agent.id, normalized_role)
        updated_teams = [updated_target]
        originals = {team.id: team}
        if old_team is not None and old_team.id != team.id:
            updated_old = _team_without_role_assignment(old_team, agent.id)
            updated_teams.append(updated_old)
            originals[old_team.id] = old_team

        self._upsert_teams_then_patch_agent(
            updated_teams=tuple(updated_teams),
            rollback_teams=tuple(originals.values()),
            agent=agent,
            team_id=team.id,
            patch_needed=agent.workspace.team != team.id,
        )
        return self._team_registry.get(team.id)

    def remove_member(self, *, team_id: str, agent_id: str) -> WorkspaceTeam:
        team = self._team_registry.get(team_id)
        agent = self._load_agent_for_update(agent_id)
        updated = _team_without_role_assignment(team, agent.id)
        self._upsert_teams_then_patch_agent(
            updated_teams=(updated,),
            rollback_teams=(team,),
            agent=agent,
            team_id=None,
            patch_needed=agent.workspace.team == team.id,
        )
        return self._team_registry.get(team.id)

    def workspace_for_team(self, team_id: str) -> Workspace:
        team = self._team_registry.get(team_id)
        return self._workspace_registry.get(team.workspace)

    def diagnostics(self) -> tuple[WorkspaceDiagnostic, ...]:
        diagnostics: list[WorkspaceDiagnostic] = []
        for team in self._team_registry.all():
            try:
                workspace = self._workspace_registry.get(team.workspace)
            except WorkspaceConfigError as exc:
                diagnostics.append(
                    WorkspaceDiagnostic(
                        code="unknown_workspace",
                        message=str(exc),
                        team_id=team.id,
                        workspace_id=team.workspace,
                    )
                )
                continue
            for provider_name in workspace.providers:
                if provider_name not in self._available_providers:
                    diagnostics.append(
                        WorkspaceDiagnostic(
                            code="unavailable_provider",
                            message=(
                                f"Workspace team {team.id} workspace {workspace.id} requires "
                                f"unavailable provider {provider_name}"
                            ),
                            team_id=team.id,
                            workspace_id=workspace.id,
                            provider_name=provider_name,
                        )
                    )
        for agent in self._agent_registry.all().values():
            for message in agent.workspace.diagnostics:
                diagnostics.append(
                    WorkspaceDiagnostic(
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
                self._workspace_registry.get(team.workspace)
            except WorkspaceConfigError as exc:
                diagnostics.append(
                    WorkspaceDiagnostic(
                        code="unknown_team",
                        message=str(exc),
                        team_id=team_id,
                        agent_id=agent.id,
                    )
                )
        return tuple(diagnostics)

    def _validate_role_assignments(self, team: WorkspaceTeam) -> None:
        for agent_id, role_id in team.role_assignments.items():
            if role_id not in team.roles:
                raise WorkspaceConfigError(
                    f"Unknown workspace team role {role_id} for team {team.id} "
                    f"assignment {agent_id}"
                )

    def _member_ids_for_team(self, team_id: str) -> set[str]:
        self._refresh_agent_registry()
        return {
            agent.id
            for agent in self._agent_registry.all().values()
            if agent.workspace.team == team_id
        }

    def _load_agent_for_update(self, agent_id: str) -> Agent:
        normalized = _required_token(agent_id, "agent id")
        if self._agents_root is None:
            raise WorkspaceConfigError("WorkspaceTeamService requires agents_root")
        agent = load_agent(normalized, agents_root=self._agents_root)
        self._agent_registry_file_backed = True
        return agent

    def _existing_team_or_none(self, team_id: str | None) -> WorkspaceTeam | None:
        if team_id is None:
            return None
        try:
            return self._team_registry.get(team_id)
        except WorkspaceConfigError:
            return None

    def _upsert_teams_then_patch_agent(
        self,
        *,
        updated_teams: tuple[WorkspaceTeam, ...],
        rollback_teams: tuple[WorkspaceTeam, ...],
        agent: Agent,
        team_id: str | None,
        patch_needed: bool,
    ) -> None:
        self._team_store.update_many(upsert_teams=updated_teams)
        if not patch_needed:
            return
        try:
            updated_agent = replace(agent, workspace=AgentWorkspaceConfig(team=team_id))
            patch_agent_config(
                updated_agent,
                changed_fields={"workspace"},
                agents_root=self._agents_root,
            )
        except Exception:
            self._team_store.update_many(upsert_teams=rollback_teams)
            raise
        self._refresh_agent_registry()

    def _refresh_agent_registry(self) -> None:
        if self._agent_registry_file_backed:
            self._agent_registry = load_agent_registry(agents_root=self._agents_root)


class WorkspaceCollaborationManager:
    """Authoritative runtime service for team membership and collaboration."""

    def __init__(
        self,
        *,
        workspace_registry: WorkspaceRegistry,
        team_registry: WorkspaceTeamRegistry,
        agent_registry: AgentRegistry,
        provider_adapters: Mapping[str, WorkspaceToolProviderAdapter],
        available_providers: tuple[str, ...] | None = None,
    ) -> None:
        self._workspace_registry = workspace_registry
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

    def workspace_for_agent(self, agent: Agent) -> Workspace | None:
        team = self.team_for_agent(agent)
        if team is None:
            return None
        return self._workspace_registry.get(team.workspace)

    def diagnostics(self) -> tuple[WorkspaceDiagnostic, ...]:
        service = WorkspaceTeamService(
            workspace_registry=self._workspace_registry,
            team_store=_ReadOnlyTeamStore(self._team_registry.all()),
            agent_registry=self._agent_registry,
            available_providers=tuple(self._available_providers),
        )
        diagnostics = list(service.diagnostics())
        for team in self._team_registry.all():
            try:
                workspace = self._workspace_registry.get(team.workspace)
            except WorkspaceConfigError:
                continue
            diagnostics.extend(self._pruned_mapping_diagnostics(team, workspace))
        return tuple(diagnostics)

    def provider_view(self, team_id: str, provider_name: str) -> WorkspaceToolProviderView:
        team = self._team_registry.get(team_id)
        workspace = self._workspace_registry.get(team.workspace)
        normalized_provider = _normalize_provider(provider_name)
        if normalized_provider not in workspace.providers:
            raise WorkspaceConfigError(
                f"Workspace team {team.id} workspace {workspace.id} does not include provider "
                f"{normalized_provider}"
            )
        if normalized_provider not in self._available_providers:
            raise WorkspaceConfigError(
                f"Workspace team {team.id} workspace {workspace.id} requires unavailable provider "
                f"{normalized_provider}"
            )
        adapter = self._adapter(normalized_provider)
        return adapter.build_provider_view(
            team=team,
            workspace=workspace,
            authorized_mappings=self.authorized_mappings(team.id, normalized_provider),
            agent_registry=self._agent_registry,
        )

    def authorized_mappings(
        self, team_id: str, provider_name: str
    ) -> tuple[WorkspaceTeamAuthorizedMapping, ...]:
        team = self._team_registry.get(team_id)
        workspace = self._workspace_registry.get(team.workspace)
        normalized_provider = _normalize_provider(provider_name)
        if normalized_provider not in workspace.providers:
            raise WorkspaceConfigError(
                f"Workspace team {team.id} workspace {workspace.id} does not include provider "
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
                    workspace_id=workspace.id,
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
        workspace = self.workspace_for_agent(agent)
        if workspace is None:
            return None
        return workspace.resolver(event)

    def resolve_provider_event(
        self, provider_name: str, event: CaoEvent
    ) -> WorkspaceToolProviderEventResolution:
        normalized_provider = _normalize_provider(provider_name)
        adapter = self._adapter(normalized_provider)
        matches: list[WorkspaceToolProviderEventResolution] = []
        errors: list[str] = []
        for team in self._team_registry.all():
            try:
                workspace = self._workspace_registry.get(team.workspace)
            except WorkspaceConfigError as exc:
                errors.append(str(exc))
                continue
            if normalized_provider not in workspace.providers:
                continue
            try:
                view = self.provider_view(team.id, normalized_provider)
                agent_id, payload = adapter.resolve_event_agent_id(
                    provider_view=view,
                    event=event,
                )
                matches.append(
                    WorkspaceToolProviderEventResolution(
                        team=team,
                        workspace=workspace,
                        agent=self._agent_registry.get(agent_id),
                        provider_name=normalized_provider,
                        provider_view=view,
                        provider_payload=payload,
                    )
                )
            except WorkspaceConfigError as exc:
                errors.append(str(exc))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            teams = ", ".join(match.team.id for match in matches)
            raise WorkspaceConfigError(
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
        raise WorkspaceConfigError(
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
            self._workspace_registry.get(team.workspace)
            return
        raise WorkspaceConfigError(
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

    def _adapter(self, provider_name: str) -> WorkspaceToolProviderAdapter:
        try:
            return self._provider_adapters[provider_name]
        except KeyError as exc:
            raise WorkspaceConfigError(
                f"Unavailable workspace tool provider: {provider_name}"
            ) from exc

    def _pruned_mapping_diagnostics(
        self, team: WorkspaceTeam, workspace: Workspace
    ) -> tuple[WorkspaceDiagnostic, ...]:
        diagnostics: list[WorkspaceDiagnostic] = []
        member_ids = self._team_member_ids(team.id)
        for provider_name in workspace.providers:
            if provider_name not in self._provider_adapters:
                continue
            for candidate in self._provider_adapters[provider_name].build_candidate_mappings(
                self._agent_registry
            ):
                if candidate.agent_id in member_ids:
                    continue
                diagnostics.append(
                    WorkspaceDiagnostic(
                        code="pruned_provider_identity",
                        message=(
                            f"Workspace team {team.id} pruned {provider_name} "
                            f"{candidate.provider_identity} {candidate.provider_value} for "
                            f"out-of-team agent {candidate.agent_id}"
                        ),
                        team_id=team.id,
                        workspace_id=workspace.id,
                        agent_id=candidate.agent_id,
                        provider_name=provider_name,
                    )
                )
        return tuple(diagnostics)

    def _provider_event_candidate_detail(
        self,
        *,
        adapter: WorkspaceToolProviderAdapter,
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
        candidate: WorkspaceToolProviderCandidateMapping,
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
            workspace = self._workspace_registry.get(team.workspace)
        except WorkspaceConfigError as exc:
            return (
                f"{provider_name} {candidate.provider_identity} {candidate.provider_value} "
                f"maps to agent {agent.id} in workspace team {team_id}, but {exc}"
            )
        if provider_name not in workspace.providers:
            return (
                f"{provider_name} {candidate.provider_identity} {candidate.provider_value} "
                f"maps to agent {agent.id} in workspace team {team.id}, but workspace {workspace.id} "
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
            raise WorkspaceConfigError(f"Unknown workspace team: {normalized}") from exc

    def upsert(self, team: WorkspaceTeam) -> WorkspaceTeam:
        raise WorkspaceConfigError("read-only workspace team store")


def default_workspace_registry() -> WorkspaceRegistry:
    from cli_agent_orchestrator.linear.workspace_context_resolver import (
        resolve_linear_workspace_event,
    )

    return WorkspaceRegistry(
        (
            Workspace(
                id=DEFAULT_WORKSPACE_ID,
                display_name="Linear Delivery",
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
                workspace=DEFAULT_WORKSPACE_ID,
            ),
        ),
    )


def default_workspace_team_service(
    *,
    agent_registry: AgentRegistry | None = None,
    agents_root: str | Path | None = None,
    team_store_path: str | Path | None = None,
) -> WorkspaceTeamService:
    from cli_agent_orchestrator.linear.workspace_adapter import LinearWorkspaceAdapter

    resolved_agents_root = (
        Path(agents_root) if agents_root is not None else agent_config.AGENTS_ROOT
    )
    registry = agent_registry or load_agent_registry(agents_root=resolved_agents_root)
    workspace_registry = default_workspace_registry()
    adapters = {"linear": LinearWorkspaceAdapter()}
    return WorkspaceTeamService(
        workspace_registry=workspace_registry,
        team_store=default_workspace_team_store(path=team_store_path),
        agent_registry=registry,
        available_providers=tuple(adapters),
        agents_root=resolved_agents_root,
    )


def default_workspace_collaboration_manager(
    *,
    agent_registry: AgentRegistry | None = None,
    team_store_path: str | Path | None = None,
) -> WorkspaceCollaborationManager:
    from cli_agent_orchestrator.linear.workspace_adapter import LinearWorkspaceAdapter

    registry = agent_registry or load_agent_registry()
    workspace_registry = default_workspace_registry()
    team_store = default_workspace_team_store(path=team_store_path)
    return WorkspaceCollaborationManager(
        workspace_registry=workspace_registry,
        team_registry=WorkspaceTeamRegistry(team_store),
        agent_registry=registry,
        provider_adapters={"linear": LinearWorkspaceAdapter()},
    )


def _required_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceConfigError(f"{label} must be a non-empty string")
    return value.strip()


def _required_json_token(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise WorkspaceConfigError(f"{label} must be a non-empty string")
    return _required_token(value, label)


def _workspace_from_json(raw_team: Mapping[str, Any]) -> tuple[str, bool]:
    has_workspace = "workspace" in raw_team
    has_legacy_workspace = "workspace_setup" in raw_team
    if not has_workspace and not has_legacy_workspace:
        raise WorkspaceConfigError("workspace team workspace id must be a non-empty string")
    if has_workspace and has_legacy_workspace:
        workspace = _required_json_token(raw_team, "workspace", "workspace team workspace id")
        legacy_workspace = _required_json_token(
            raw_team,
            "workspace_setup",
            "legacy workspace team workspace id",
        )
        if workspace != legacy_workspace:
            raise WorkspaceConfigError(
                "Workspace team entry has conflicting workspace and workspace_setup values"
            )
        return _canonical_workspace_id(workspace), True
    if has_legacy_workspace:
        legacy_workspace = _required_json_token(
            raw_team,
            "workspace_setup",
            "legacy workspace team workspace id",
        )
        return _canonical_workspace_id(legacy_workspace), True
    workspace = _required_json_token(raw_team, "workspace", "workspace team workspace id")
    canonical = _canonical_workspace_id(workspace)
    return canonical, canonical != workspace


def _canonical_workspace_id(workspace_id: str) -> str:
    return LEGACY_WORKSPACE_IDS.get(_required_token(workspace_id, "workspace id"), workspace_id)


def _normalize_provider(value: str) -> str:
    return _required_token(value, "workspace tool provider name").lower()


def _str_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise WorkspaceConfigError(f"{label} must be a string list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise WorkspaceConfigError(f"{label} must contain only non-empty strings")
        result.append(item.strip())
    return tuple(dict.fromkeys(result))


def _str_mapping(value: Any, label: str) -> Mapping[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise WorkspaceConfigError(f"{label} must be an object")
    return {
        _required_token(str(key), f"{label} key"): _required_token(str(item), f"{label} value")
        for key, item in value.items()
    }


def _roles_from_json(value: Any) -> Mapping[str, WorkspaceTeamRole]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise WorkspaceConfigError("workspace team roles must be an object")
    roles: dict[str, WorkspaceTeamRole] = {}
    for role_id, role_value in value.items():
        if not isinstance(role_value, Mapping):
            raise WorkspaceConfigError("workspace team role entries must be objects")
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


def _team_with_role_assignment(
    team: WorkspaceTeam,
    agent_id: str,
    role_id: str,
) -> WorkspaceTeam:
    assignments = dict(team.role_assignments)
    assignments[_required_token(agent_id, "agent id")] = _required_token(
        role_id,
        "workspace team role id",
    )
    return WorkspaceTeam(
        id=team.id,
        display_name=team.display_name,
        workspace=team.workspace,
        roles=team.roles,
        role_assignments=assignments,
    )


def _team_without_role_assignment(team: WorkspaceTeam, agent_id: str) -> WorkspaceTeam:
    assignments = dict(team.role_assignments)
    assignments.pop(_required_token(agent_id, "agent id"), None)
    return WorkspaceTeam(
        id=team.id,
        display_name=team.display_name,
        workspace=team.workspace,
        roles=team.roles,
        role_assignments=assignments,
    )


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

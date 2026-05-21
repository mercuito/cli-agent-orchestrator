"""Authoritative CAO tool registration, access, and materialization service."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Literal, Mapping, Optional

from cli_agent_orchestrator.agent import Agent, AgentRegistry, load_agent_registry
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.services.agent_manager import AgentManager, default_agent_manager
from cli_agent_orchestrator.utils.tool_mapping import resolve_runtime_capabilities
from cli_agent_orchestrator.workspaces import (
    DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE,
    WorkspaceCollaborationManager,
    WorkspaceConfigError,
    default_workspace_collaboration_manager,
)
from cli_agent_orchestrator.workspace_tool_providers.registry import (
    WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH,
    ProviderRoleToolAccessWorkspaceToolProvider,
    ProviderToolAccessConfigurableWorkspaceToolProvider,
    ProviderToolAccessWorkspaceToolProvider,
    WorkspaceToolProviderConfigError,
    WorkspaceToolProviderRegistry,
    default_workspace_tool_provider_registry,
    load_enabled_workspace_tool_providers,
)
from cli_agent_orchestrator.workspace_tool_providers.tool_access import (
    ProviderMediatedToolDefinition,
    ProviderRoleToolAccessGrant,
    ProviderToolAccess,
    ProviderToolAccessConfigError,
    ProviderToolAccessPolicy,
)

logger = logging.getLogger(__name__)

TerminalMetadataResolver = Callable[[str], Mapping[str, Any] | None]
ProviderPolicyLoader = Callable[[AgentRegistry], Mapping[str, ProviderToolAccessPolicy]]
CollaborationManagerFactory = Callable[[AgentRegistry], WorkspaceCollaborationManager]

MANAGED_CAO_MCP_SERVER = "cao-mcp-server"


@dataclass(frozen=True)
class ToolAccessDiagnostic:
    """One user-facing diagnostic emitted by ToolService."""

    code: str
    message: str
    source: str


@dataclass(frozen=True)
class ToolAccessDecision:
    """Allow/deny result for one tool operation."""

    allowed: bool
    reason: str = ""
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(
        cls, *, reason: str = "allowed", diagnostics: Mapping[str, Any] | None = None
    ) -> "ToolAccessDecision":
        return cls(allowed=True, reason=reason, diagnostics=dict(diagnostics or {}))

    @classmethod
    def deny(
        cls, reason: str, *, diagnostics: Mapping[str, Any] | None = None
    ) -> "ToolAccessDecision":
        return cls(allowed=False, reason=reason, diagnostics=dict(diagnostics or {}))


@dataclass(frozen=True)
class AgentToolAccess:
    """Effective ToolService access projection for one CAO agent."""

    agent_id: str
    team_id: str | None
    role_id: str | None
    registered_tools: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    blocked_tools: tuple[str, ...]
    built_in_cao_tools: tuple[str, ...]
    provider_mediated_tools: Mapping[str, tuple[str, ...]]
    provider_access: tuple[ProviderToolAccess, ...]
    direct_mcp_servers: Mapping[str, Mapping[str, Any]]
    materialized_mcp_servers: Mapping[str, Mapping[str, Any]]
    runtime_capabilities: tuple[str, ...] | None
    source_markers: Mapping[str, str]
    inactive_local_grants: Mapping[str, Any]
    diagnostics: tuple[ToolAccessDiagnostic, ...]


@dataclass(frozen=True)
class AgentToolView:
    """Dashboard/API tool metadata projection owned by ToolService."""

    agent_id: str
    effective_access: AgentToolAccess
    mcp_surface_descriptor: Mapping[str, Any]


@dataclass(frozen=True)
class ToolRegistration:
    """Effective MCP registration for one terminal."""

    terminal_id: str
    agent_id: str
    built_in_tools: tuple[str, ...]
    provider_mediated_tools: tuple[tuple[str, ProviderMediatedToolDefinition], ...]
    registered_tools: tuple[str, ...]
    diagnostics: tuple[ToolAccessDiagnostic, ...]


@dataclass(frozen=True)
class ToolAccessSourceResult:
    """Normalized grant material from exactly one active access source."""

    agent_id: str
    team_id: str | None
    role_id: str | None
    source_name: str
    provider_access_source: Literal["standalone_local", "team_role"]
    local_cao_tools: tuple[str, ...] | None
    direct_mcp_servers: Mapping[str, Mapping[str, Any]]
    provider_role_grants: tuple[ProviderRoleToolAccessGrant, ...]
    runtime_capabilities: tuple[str, ...] | None
    source_markers: Mapping[str, str]
    inactive_local_grants: Mapping[str, Any]
    diagnostics: tuple[ToolAccessDiagnostic, ...]


class StandaloneAgentToolAccessSource:
    """Active grant source for agents without a workspace team."""

    source_name = "agent-local standalone policy"

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    def resolve(self) -> ToolAccessSourceResult:
        return ToolAccessSourceResult(
            agent_id=self._agent.id,
            team_id=None,
            role_id=None,
            source_name=self.source_name,
            provider_access_source="standalone_local",
            local_cao_tools=(
                None if self._agent.cao_tools is None else tuple(self._agent.cao_tools)
            ),
            direct_mcp_servers=_local_mcp_servers_from_agent(self._agent),
            provider_role_grants=(),
            runtime_capabilities=_runtime_capabilities_input(self._agent),
            source_markers={
                **{name: "agent_config:cao_tools" for name in tuple(self._agent.cao_tools or ())},
                **{
                    f"@{name}": "agent_config:mcp_servers"
                    for name in _local_mcp_servers_from_agent(self._agent)
                },
            },
            inactive_local_grants={},
            diagnostics=(),
        )


class TeamRoleToolAccessSource:
    """Active grant source for agents that belong to a workspace team."""

    source_name = "team role policy"

    def __init__(
        self,
        agent: Agent,
        *,
        collaboration_manager: WorkspaceCollaborationManager,
        inactive_local_grants: Mapping[str, Any],
    ) -> None:
        self._agent = agent
        self._collaboration_manager = collaboration_manager
        self._inactive_local_grants = inactive_local_grants

    def resolve(self) -> ToolAccessSourceResult:
        diagnostics: list[ToolAccessDiagnostic] = []
        if self._inactive_local_grants:
            diagnostics.append(
                ToolAccessDiagnostic(
                    code="inactive_teamed_local_tool_access",
                    message=(
                        f"Agent {self._agent.id} belongs to workspace team "
                        f"{self._agent.workspace.team}; agent-local tool grants are retained "
                        "for diagnostics only."
                    ),
                    source="agent_config",
                )
            )
        try:
            team = self._collaboration_manager.team_for_agent(self._agent)
            if team is None:
                raise WorkspaceConfigError(
                    f"caller agent {self._agent.id} has no workspace team"
                )
            workspace = self._collaboration_manager.workspace_for_agent(self._agent)
            if workspace is None:
                raise WorkspaceConfigError(f"workspace team {team.id} has no workspace")
        except Exception as exc:
            diagnostics.append(
                ToolAccessDiagnostic(
                    code="invalid_workspace_team",
                    message=str(exc),
                    source="workspace_team",
                )
            )
            return ToolAccessSourceResult(
                agent_id=self._agent.id,
                team_id=self._agent.workspace.team,
                role_id=None,
                source_name=self.source_name,
                provider_access_source="team_role",
                local_cao_tools=(),
                direct_mcp_servers={},
                provider_role_grants=(),
                runtime_capabilities=_runtime_capabilities_input(self._agent),
                source_markers={},
                inactive_local_grants=self._inactive_local_grants,
                diagnostics=tuple(diagnostics),
            )

        assigned_role_id = team.role_assignments.get(
            self._agent.id,
            DEFAULT_WORKSPACE_TEAM_MEMBER_ROLE,
        )
        if assigned_role_id not in team.roles:
            diagnostics.append(
                ToolAccessDiagnostic(
                    code="invalid_team_role_assignment",
                    message=(
                        f"Workspace team {team.id} assigns agent {self._agent.id} "
                        f"to missing role {assigned_role_id}; using member."
                    ),
                    source="workspace_team.role_assignments",
                )
            )
        role_id, role = team.role_for_member(self._agent.id)
        member_ids = {
            agent.id
            for agent in self._collaboration_manager.agent_registry.all().values()
            if agent.workspace.team == team.id
        }
        for assigned_agent_id in sorted(set(team.role_assignments) - member_ids):
            diagnostics.append(
                ToolAccessDiagnostic(
                    code="inactive_non_member_role_assignment",
                    message=(
                        f"Workspace team {team.id} assigns role "
                        f"{team.role_assignments[assigned_agent_id]} to non-member "
                        f"{assigned_agent_id}; assignment is inactive."
                    ),
                    source="workspace_team.role_assignments",
                )
            )
        direct_mcp_servers = {
            name: _copy_jsonish_mapping(config)
            for name, config in role.mcp_servers.items()
            if name != MANAGED_CAO_MCP_SERVER
        }
        if MANAGED_CAO_MCP_SERVER in role.mcp_servers:
            diagnostics.append(
                ToolAccessDiagnostic(
                    code="managed_mcp_server_shadow_rejected",
                    message=(
                        f"Workspace team {team.id} role {role_id} declares "
                        f"{MANAGED_CAO_MCP_SERVER}, which is CAO-managed and cannot be "
                        "overridden."
                    ),
                    source=f"workspace_team.{team.id}.roles.{role_id}.mcp_servers",
                )
            )
        workspace_providers = {provider.strip().lower() for provider in workspace.providers}
        provider_grants: list[ProviderRoleToolAccessGrant] = []
        for provider_name, grants in role.providers.items():
            if provider_name not in workspace_providers:
                diagnostics.append(
                    ToolAccessDiagnostic(
                        code="role_provider_not_in_workspace",
                        message=(
                            f"Workspace team {team.id} role {role_id} grants provider "
                            f"{provider_name}, but workspace {workspace.id} does not include it."
                        ),
                        source=f"workspace_team.{team.id}.roles.{role_id}.providers.{provider_name}",
                    )
                )
                continue
            for access_id, spec in grants.items():
                provider_grants.append(
                    ProviderRoleToolAccessGrant(
                        provider_name=provider_name,
                        access_id=access_id,
                        agent_id=self._agent.id,
                        source_location=(
                            f"workspace_team.{team.id}.roles.{role_id}."
                            f"providers.{provider_name}.{access_id}"
                        ),
                        spec=spec,
                    )
                )
        return ToolAccessSourceResult(
            agent_id=self._agent.id,
            team_id=team.id,
            role_id=role_id,
            source_name=self.source_name,
            provider_access_source="team_role",
            local_cao_tools=tuple(role.cao_tools),
            direct_mcp_servers=direct_mcp_servers,
            provider_role_grants=tuple(provider_grants),
            runtime_capabilities=_runtime_capabilities_input(self._agent),
            source_markers={
                **{
                    name: f"workspace_team.{team.id}.roles.{role_id}.cao_tools"
                    for name in role.cao_tools
                },
                **{
                    f"@{name}": f"workspace_team.{team.id}.roles.{role_id}.mcp_servers.{name}"
                    for name in direct_mcp_servers
                },
            },
            inactive_local_grants=self._inactive_local_grants,
            diagnostics=tuple(diagnostics),
        )


class ToolAccessResolver:
    """Choose the single active tool access source for one agent."""

    def __init__(
        self,
        *,
        collaboration_manager_factory: CollaborationManagerFactory,
    ) -> None:
        self._collaboration_manager_factory = collaboration_manager_factory

    def resolve(
        self,
        agent: Agent,
        agent_registry: AgentRegistry,
    ) -> ToolAccessSourceResult:
        if agent.workspace.team is None:
            return StandaloneAgentToolAccessSource(agent).resolve()
        return TeamRoleToolAccessSource(
            agent,
            collaboration_manager=self._collaboration_manager_factory(agent_registry),
            inactive_local_grants=_inactive_local_grants(agent),
        ).resolve()


class ToolService:
    """Single production authority for effective CAO tool access."""

    def __init__(
        self,
        *,
        agent_manager: AgentManager | None = None,
        terminal_metadata_resolver: TerminalMetadataResolver = db_module.get_terminal_metadata,
        provider_policy_loader: ProviderPolicyLoader | None = None,
        collaboration_manager_factory: CollaborationManagerFactory | None = None,
    ) -> None:
        self._agent_manager = agent_manager or default_agent_manager()
        self._terminal_metadata_resolver = terminal_metadata_resolver
        self._provider_policy_loader = provider_policy_loader
        self._collaboration_manager_factory = collaboration_manager_factory or (
            lambda registry: default_workspace_collaboration_manager(agent_registry=registry)
        )
        self._resolver = ToolAccessResolver(
            collaboration_manager_factory=self._collaboration_manager_factory
        )
        self._raw_provider_policies_cache: dict[
            tuple[Any, ...], Mapping[str, ProviderToolAccessPolicy]
        ] = {}
        self._role_provider_policy_cache: dict[
            tuple[Any, ...],
            tuple[Mapping[str, ProviderToolAccessPolicy], tuple[ToolAccessDiagnostic, ...]],
        ] = {}

    def agent_tool_view(
        self,
        agent_id: str,
        *,
        built_in_tools: Iterable[tuple[str, Callable[..., Any], Mapping[str, Any]]],
        built_in_tool_names: Iterable[str],
        baton_enabled: bool = True,
    ) -> AgentToolView:
        """Return the API-facing tool view for one agent through ToolService."""
        access = self.tools_for_agent(agent_id, built_in_tool_names=built_in_tool_names)
        descriptor = self.mcp_surface_descriptor_for_agent(
            agent_id,
            built_in_tools=built_in_tools,
            built_in_tool_names=built_in_tool_names,
            baton_enabled=baton_enabled,
            access=access,
        )
        return AgentToolView(
            agent_id=agent_id,
            effective_access=access,
            mcp_surface_descriptor=descriptor,
        )

    def mcp_surface_descriptor_for_agent(
        self,
        agent_id: str,
        *,
        built_in_tools: Iterable[tuple[str, Callable[..., Any], Mapping[str, Any]]],
        built_in_tool_names: Iterable[str],
        baton_enabled: bool = True,
        access: AgentToolAccess | None = None,
    ) -> Mapping[str, Any]:
        """Build one agent's visible MCP tool surface from ToolService decisions."""
        from cli_agent_orchestrator.mcp_server.freshness import (
            build_agent_mcp_surface_descriptor,
        )

        agent = self._agent_manager.resolve_agent(agent_id)
        effective_access = access or self.tools_for_agent(
            agent.id,
            built_in_tool_names=built_in_tool_names,
        )
        provider_policies = self.provider_policies_for_agent(agent.id)
        return build_agent_mcp_surface_descriptor(
            agent=agent,
            built_in_tools=tuple(built_in_tools),
            built_in_tool_allowlist=list(effective_access.built_in_cao_tools),
            provider_policies=provider_policies,
            baton_enabled=baton_enabled,
            provider_tool_allowlist=effective_access.provider_mediated_tools,
        )

    def mcp_runtime_generation_descriptor_for_agent(
        self,
        agent_id: str,
        *,
        built_in_tools: Iterable[tuple[str, Callable[..., Any], Mapping[str, Any]]],
        built_in_tool_names: Iterable[str],
        built_in_runtime_generation: Mapping[str, Any],
        baton_enabled: bool = True,
    ) -> Mapping[str, Any]:
        """Build runtime-generation material from ToolService access decisions."""
        from cli_agent_orchestrator.mcp_server.freshness import (
            build_agent_mcp_runtime_generation_descriptor,
        )

        agent = self._agent_manager.resolve_agent(agent_id)
        access = self.tools_for_agent(agent.id, built_in_tool_names=built_in_tool_names)
        provider_policies = self.provider_policies_for_agent(agent.id)
        return build_agent_mcp_runtime_generation_descriptor(
            agent=agent,
            built_in_tools=tuple(built_in_tools),
            built_in_tool_allowlist=list(access.built_in_cao_tools),
            provider_policies=provider_policies,
            baton_enabled=baton_enabled,
            built_in_runtime_generation=built_in_runtime_generation,
            provider_tool_allowlist=access.provider_mediated_tools,
        )

    def tools_for_agent(
        self,
        agent_id: str,
        *,
        built_in_tool_names: Iterable[str] = (),
    ) -> AgentToolAccess:
        """Return effective access for one agent through the owner boundary."""
        agent = self._agent_manager.resolve_agent(agent_id)
        agent_registry = self._agent_registry()
        built_in_names = tuple(dict.fromkeys(name for name in built_in_tool_names if name))
        source_result = self._resolver.resolve(agent, agent_registry)
        provider_policies, provider_diagnostics = self._provider_policies_for_source(
            agent,
            source_result,
        )
        provider_access = tuple(
            access for policy in provider_policies.values() for access in policy.access
        )
        built_in_effective = self._effective_built_in_tools(
            built_in_names=built_in_names,
            local_cao_tools=source_result.local_cao_tools,
        )
        provider_tool_entries = self._provider_mediated_tools_for_agent_from_policies(
            agent.id,
            provider_policies,
            reserved_tool_names=built_in_names,
        )
        mapped_provider_tools = self._provider_tool_mapping(provider_tool_entries)
        provider_tools = {
            provider_name: mapped_provider_tools.get(provider_name, ())
            for provider_name in sorted(provider_policies)
        }
        provider_tool_names = tuple(
            tool_name
            for provider_name in sorted(provider_tools)
            for tool_name in provider_tools[provider_name]
        )
        effective_provider_names = {
            (provider_name, tool.name) for provider_name, tool in provider_tool_entries
        }
        provider_access = tuple(
            access
            for access in provider_access
            if (access.provider_name, access.tool_name) in effective_provider_names
        )
        direct_mcp_servers = source_result.direct_mcp_servers
        materialized_mcp_servers = self.materialized_mcp_servers_for_agent(agent.id)
        runtime_capabilities = tuple(
            resolve_runtime_capabilities(
                None
                if source_result.runtime_capabilities is None
                else list(source_result.runtime_capabilities),
                list(materialized_mcp_servers),
            )
        )
        allowed = tuple(dict.fromkeys((*built_in_effective, *provider_tool_names)))
        registered = tuple(
            dict.fromkeys((*allowed, *(f"@{name}" for name in materialized_mcp_servers)))
        )
        source_markers = {
            **source_result.source_markers,
            **{
                name: source_result.source_markers.get(name, self._built_in_source(agent))
                for name in built_in_effective
            },
            **{
                access.tool_name: f"{access.provider_name}:{access.source_location}"
                for access in provider_access
            },
            **{
                f"@{name}": source_result.source_markers.get(
                    f"@{name}", self._mcp_source(agent, name)
                )
                for name in materialized_mcp_servers
            },
        }
        return AgentToolAccess(
            agent_id=agent.id,
            team_id=source_result.team_id,
            role_id=source_result.role_id,
            registered_tools=registered,
            allowed_tools=allowed,
            blocked_tools=(),
            built_in_cao_tools=built_in_effective,
            provider_mediated_tools=provider_tools,
            provider_access=provider_access,
            direct_mcp_servers=direct_mcp_servers,
            materialized_mcp_servers=materialized_mcp_servers,
            runtime_capabilities=runtime_capabilities,
            source_markers=source_markers,
            inactive_local_grants=source_result.inactive_local_grants,
            diagnostics=(*source_result.diagnostics, *provider_diagnostics),
        )

    def registered_tools_for_terminal(
        self,
        terminal_id: str,
        *,
        built_in_tool_names: Iterable[str] = (),
    ) -> ToolRegistration:
        """Return the effective MCP registration for a terminal."""
        agent = self.agent_for_terminal(terminal_id)
        access = self.tools_for_agent(agent.id, built_in_tool_names=built_in_tool_names)
        provider_tools = self.provider_mediated_tools_for_agent(
            agent.id,
            built_in_tool_names=built_in_tool_names,
        )
        return ToolRegistration(
            terminal_id=terminal_id,
            agent_id=agent.id,
            built_in_tools=access.built_in_cao_tools,
            provider_mediated_tools=provider_tools,
            registered_tools=tuple(
                dict.fromkeys(
                    (*access.built_in_cao_tools, *(tool.name for _, tool in provider_tools))
                )
            ),
            diagnostics=access.diagnostics,
        )

    def provider_policy(self, provider_name: str) -> ProviderToolAccessPolicy | None:
        """Return the current effective provider policy for all agents."""
        return self.provider_policies().get(provider_name.strip().lower())

    def provider_policies(self) -> Mapping[str, ProviderToolAccessPolicy]:
        """Return provider policies filtered through ToolService authority."""
        agents = self._agent_registry()
        effective: dict[str, ProviderToolAccessPolicy] = {}
        for agent in agents.all().values():
            for provider_name, policy in self.provider_policies_for_agent(agent.id).items():
                existing = effective.get(provider_name)
                merged_access = tuple(
                    sorted(
                        {
                            self._access_key(entry): entry
                            for entry in (
                                *(existing.access if existing is not None else ()),
                                *policy.access,
                            )
                        }.values(),
                        key=lambda item: (item.agent_id, item.tool_name, item.source_location),
                    )
                )
                effective[provider_name] = replace(policy, access=merged_access)
        return effective

    def provider_policies_for_agent(self, agent_id: str) -> Mapping[str, ProviderToolAccessPolicy]:
        """Return provider policies scoped to one agent's effective access."""
        agent = self._agent_manager.resolve_agent(agent_id)
        source_result = self._resolver.resolve(agent, self._agent_registry())
        policies, _diagnostics = self._provider_policies_for_source(agent, source_result)
        return policies

    def provider_mediated_tools_for_agent(
        self,
        agent_id: str,
        *,
        built_in_tool_names: Iterable[str] = (),
    ) -> tuple[tuple[str, ProviderMediatedToolDefinition], ...]:
        """Return visible provider-mediated MCP tool definitions for an agent."""
        policies = self.provider_policies_for_agent(agent_id)
        return self._provider_mediated_tools_for_agent_from_policies(
            agent_id,
            policies,
            reserved_tool_names=tuple(dict.fromkeys(name for name in built_in_tool_names if name)),
        )

    def can_invoke(
        self,
        agent_id: str,
        tool_ref: str,
        *,
        provider_name: str | None = None,
        built_in_tool_names: Iterable[str] = (),
        context: Mapping[str, Any] | None = None,
    ) -> ToolAccessDecision:
        """Return whether an agent can currently invoke a tool."""
        if provider_name:
            policy = self.provider_policies_for_agent(agent_id).get(provider_name)
            visible_provider_tools = self.provider_mediated_tools_for_agent(
                agent_id,
                built_in_tool_names=built_in_tool_names,
            )
            if policy is not None and any(
                name == provider_name and tool.name == tool_ref
                for name, tool in visible_provider_tools
            ):
                return ToolAccessDecision.allow(
                    reason="provider_tool_allowed",
                    diagnostics={"provider_name": provider_name, "tool_name": tool_ref},
                )
            return ToolAccessDecision.deny(
                "provider_tool_denied",
                diagnostics={
                    "agent_id": agent_id,
                    "provider_name": provider_name,
                    "tool_name": tool_ref,
                    **dict(context or {}),
                },
            )
        access = self.tools_for_agent(agent_id, built_in_tool_names=built_in_tool_names)
        if tool_ref in access.built_in_cao_tools:
            return ToolAccessDecision.allow(
                reason="built_in_tool_allowed",
                diagnostics={"tool_name": tool_ref},
            )
        return ToolAccessDecision.deny(
            "built_in_tool_denied",
            diagnostics={"agent_id": agent_id, "tool_name": tool_ref, **dict(context or {})},
        )

    def can_invoke_for_terminal(
        self,
        terminal_id: str,
        tool_ref: str,
        *,
        provider_name: str | None = None,
        built_in_tool_names: Iterable[str] = (),
        context: Mapping[str, Any] | None = None,
    ) -> ToolAccessDecision:
        """Return whether a terminal's current agent can invoke a tool."""
        agent = self.agent_for_terminal(terminal_id)
        return self.can_invoke(
            agent.id,
            tool_ref,
            provider_name=provider_name,
            built_in_tool_names=built_in_tool_names,
            context={"terminal_id": terminal_id, **dict(context or {})},
        )

    def can_invoke_for_terminal_target(
        self,
        terminal_id: str,
        tool_ref: str,
        *,
        target_terminal_id: str,
        provider_name: str | None = None,
        built_in_tool_names: Iterable[str] = (),
        context: Mapping[str, Any] | None = None,
    ) -> ToolAccessDecision:
        """Return whether a terminal's agent may target a terminal process."""
        decision = self.can_invoke_for_terminal(
            terminal_id,
            tool_ref,
            provider_name=provider_name,
            built_in_tool_names=built_in_tool_names,
            context={"target_terminal_id": target_terminal_id, **dict(context or {})},
        )
        if not decision.allowed or tool_ref != "terminate":
            return decision
        try:
            caller = self.agent_for_terminal(terminal_id)
            target = self.agent_for_terminal(target_terminal_id)
        except Exception as exc:
            return ToolAccessDecision.deny(
                "target_terminal_unresolved",
                diagnostics={
                    "terminal_id": terminal_id,
                    "target_terminal_id": target_terminal_id,
                    "error": str(exc),
                },
            )
        if caller.workspace.team is None or caller.workspace.team != target.workspace.team:
            return ToolAccessDecision.deny(
                "target_terminal_not_same_workspace_team",
                diagnostics={
                    "terminal_id": terminal_id,
                    "agent_id": caller.id,
                    "agent_team": caller.workspace.team,
                    "target_terminal_id": target_terminal_id,
                    "target_agent_id": target.id,
                    "target_agent_team": target.workspace.team,
                },
            )
        return ToolAccessDecision.allow(
            reason="target_terminal_same_workspace_team",
            diagnostics={
                "terminal_id": terminal_id,
                "target_terminal_id": target_terminal_id,
                "tool_name": tool_ref,
            },
        )

    def materialized_mcp_servers_for_agent(self, agent_id: str) -> Mapping[str, Mapping[str, Any]]:
        """Return effective direct/custom MCP servers to materialize."""
        agent = self._agent_manager.resolve_agent(agent_id)
        source_result = self._resolver.resolve(agent, self._agent_registry())
        servers: dict[str, Mapping[str, Any]] = {}
        servers.update(source_result.direct_mcp_servers)
        managed = self._managed_cao_mcp_server(agent)
        existing = servers.get(MANAGED_CAO_MCP_SERVER)
        if isinstance(existing, Mapping):
            managed = {
                **managed,
                **{key: existing[key] for key in ("env", "cwd") if key in existing},
            }
        servers[MANAGED_CAO_MCP_SERVER] = managed
        return {name: _copy_jsonish_mapping(config) for name, config in sorted(servers.items())}

    def runtime_capabilities_for_agent(self, agent_id: str) -> tuple[str, ...]:
        """Return effective runtime capabilities, including MCP server markers."""
        agent = self._agent_manager.resolve_agent(agent_id)
        source_result = self._resolver.resolve(agent, self._agent_registry())
        return tuple(
            resolve_runtime_capabilities(
                None
                if source_result.runtime_capabilities is None
                else list(source_result.runtime_capabilities),
                list(self.materialized_mcp_servers_for_agent(agent.id)),
            )
        )

    def codex_config_for_agent(self, agent_id: str) -> Mapping[str, Any]:
        """Return agent Codex config with MCP server authority removed."""
        agent = self._agent_manager.resolve_agent(agent_id)
        config = dict(agent.codex_config)
        config.pop("mcp_servers", None)
        return config

    def agent_for_terminal(self, terminal_id: str) -> Agent:
        """Resolve the current agent for a terminal through ToolService dependencies."""
        metadata = self._terminal_metadata_resolver(terminal_id)
        if metadata is None:
            raise ValueError(f"Unknown terminal: {terminal_id}")
        agent_id = metadata.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError(f"Terminal {terminal_id!r} is not attached to an agent")
        return self._agent_manager.resolve_agent(agent_id.strip())

    def _effective_built_in_tools(
        self,
        *,
        built_in_names: tuple[str, ...],
        local_cao_tools: tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        if local_cao_tools is None:
            return built_in_names
        return tuple(name for name in built_in_names if name in set(local_cao_tools))

    def _effective_runtime_capabilities_input(self, agent: Agent) -> list[str] | None:
        return None if agent.runtime_capabilities is None else list(agent.runtime_capabilities)

    def _provider_mediated_tools_for_agent_from_policies(
        self,
        agent_id: str,
        policies: Mapping[str, ProviderToolAccessPolicy],
        *,
        reserved_tool_names: Iterable[str] = (),
    ) -> tuple[tuple[str, ProviderMediatedToolDefinition], ...]:
        reserved = set(reserved_tool_names)
        seen_tool_names: set[str] = set()
        candidates: list[tuple[str, ProviderMediatedToolDefinition]] = []
        for provider_name, policy in sorted(policies.items()):
            for access in policy.access:
                if access.agent_id != agent_id:
                    continue
                tool = policy.tools.get(access.tool_name)
                if tool is None or tool.name in reserved:
                    continue
                candidates.append((provider_name, tool))
        visible: list[tuple[str, ProviderMediatedToolDefinition]] = []
        for provider_name, tool in sorted(candidates, key=lambda item: (item[0], item[1].name)):
            if tool.name in seen_tool_names:
                continue
            seen_tool_names.add(tool.name)
            visible.append((provider_name, tool))
        return tuple(visible)

    def _provider_tool_mapping(
        self, entries: Iterable[tuple[str, ProviderMediatedToolDefinition]]
    ) -> Mapping[str, tuple[str, ...]]:
        mapped: dict[str, list[str]] = {}
        for provider_name, tool in entries:
            mapped.setdefault(provider_name, []).append(tool.name)
        return {
            provider_name: tuple(sorted(tool_names))
            for provider_name, tool_names in sorted(mapped.items())
        }

    def _managed_cao_mcp_server(self, agent: Agent) -> Mapping[str, Any]:
        return {"command": MANAGED_CAO_MCP_SERVER, "enabled": True}

    def _built_in_source(self, agent: Agent) -> str:
        if agent.workspace.team is not None:
            return "workspace_team:managed_cao_tools"
        if agent.cao_tools is not None:
            return "agent_config:cao_tools"
        return "cao_default:all_built_in_tools"

    def _mcp_source(self, agent: Agent, server_name: str) -> str:
        if server_name == MANAGED_CAO_MCP_SERVER:
            return "cao_managed_mcp_server"
        if agent.workspace.team is not None:
            return "workspace_team:materialized_mcp"
        return "agent_config:mcp_servers"

    def _policy_for_agent(
        self, policy: ProviderToolAccessPolicy, agent: Agent
    ) -> ProviderToolAccessPolicy:
        access = tuple(entry for entry in policy.access if entry.agent_id == agent.id)
        return replace(policy, access=access)

    def _provider_policies_for_source(
        self,
        agent: Agent,
        source_result: ToolAccessSourceResult,
    ) -> tuple[Mapping[str, ProviderToolAccessPolicy], tuple[ToolAccessDiagnostic, ...]]:
        if source_result.provider_access_source == "standalone_local":
            return (
                {
                    provider_name: self._policy_for_agent(policy, agent)
                    for provider_name, policy in self._raw_provider_policies().items()
                },
                (),
            )
        return self._role_provider_policy_resolution(agent, source_result)

    def _role_provider_policy_resolution(
        self,
        agent: Agent,
        source_result: ToolAccessSourceResult,
    ) -> tuple[Mapping[str, ProviderToolAccessPolicy], tuple[ToolAccessDiagnostic, ...]]:
        cache_key = (
            "role_provider_policy",
            _agent_cache_token(agent),
            _source_result_cache_token(source_result),
            _agent_registry_cache_token(self._agent_registry()),
            _workspace_tool_provider_config_cache_token(),
        )
        if cache_key in self._role_provider_policy_cache:
            return self._role_provider_policy_cache[cache_key]
        grants_by_provider: dict[str, list[ProviderRoleToolAccessGrant]] = {}
        for grant in source_result.provider_role_grants:
            grants_by_provider.setdefault(grant.provider_name, []).append(grant)
        if not grants_by_provider:
            return {}, ()

        provider_registry = default_workspace_tool_provider_registry()
        policies: dict[str, ProviderToolAccessPolicy] = {}
        diagnostics: list[ToolAccessDiagnostic] = []
        for provider_name, grants in sorted(grants_by_provider.items()):
            try:
                provider = provider_registry.create(provider_name, self._agent_registry())
                if not isinstance(provider, ProviderRoleToolAccessWorkspaceToolProvider):
                    diagnostics.append(
                        ToolAccessDiagnostic(
                            code="provider_role_access_unsupported",
                            message=(
                                f"Workspace tool provider {provider_name} does not support "
                                "team-role-owned tool access."
                            ),
                            source=f"workspace_team.providers.{provider_name}",
                        )
                    )
                    continue
                policies[provider_name] = provider.provider_role_tool_access(tuple(grants))
            except Exception as exc:
                diagnostics.append(
                    ToolAccessDiagnostic(
                        code="provider_role_access_invalid",
                        message=(
                            f"Workspace tool provider {provider_name} rejected team role tool "
                            f"access for agent {agent.id}: {exc}"
                        ),
                        source=f"workspace_team.providers.{provider_name}",
                    )
                )
        result = (policies, tuple(diagnostics))
        self._role_provider_policy_cache[cache_key] = result
        return result

    def _raw_provider_policies(self) -> Mapping[str, ProviderToolAccessPolicy]:
        cache_key = (
            "raw_provider_policies",
            _agent_registry_cache_token(self._standalone_provider_agent_registry()),
            _workspace_tool_provider_config_cache_token(),
        )
        if cache_key in self._raw_provider_policies_cache:
            return self._raw_provider_policies_cache[cache_key]
        if self._provider_policy_loader is not None:
            policies = self._provider_policy_loader(self._agent_registry())
            self._raw_provider_policies_cache[cache_key] = policies
            return policies
        try:
            policies = _load_raw_enabled_provider_tool_access_policies(
                agent_registry=self._standalone_provider_agent_registry()
            )
            self._raw_provider_policies_cache[cache_key] = policies
            return policies
        except (ProviderToolAccessConfigError, WorkspaceToolProviderConfigError):
            raise
        except Exception:
            logger.exception("Provider-mediated tool access loading failed")
            return {}

    def _agent_registry(self) -> AgentRegistry:
        return AgentRegistry({agent.id: agent for agent in self._agent_manager.list_agents()})

    def _standalone_provider_agent_registry(self) -> AgentRegistry:
        agents: dict[str, Agent] = {}
        registry = self._agent_registry()
        for agent in registry.all().values():
            source_result = self._resolver.resolve(agent, registry)
            if source_result.provider_access_source == "standalone_local":
                agents[agent.id] = agent
        return AgentRegistry(agents)

    def _collaboration_manager(self) -> WorkspaceCollaborationManager:
        return self._collaboration_manager_factory(self._agent_registry())

    @staticmethod
    def _access_key(entry: ProviderToolAccess) -> tuple[str, str, str, str]:
        return (entry.provider_name, entry.agent_id, entry.tool_name, entry.source_location)


def _load_raw_enabled_provider_tool_access_policies(
    *,
    agent_registry: AgentRegistry | None = None,
    enabled_config_path: Any = None,
    registry: WorkspaceToolProviderRegistry | None = None,
) -> Mapping[str, ProviderToolAccessPolicy]:
    """Load provider-owned tool definitions/access as ToolService input."""
    enabled = load_enabled_workspace_tool_providers(enabled_config_path)
    agents = agent_registry or load_agent_registry()
    provider_registry = registry or default_workspace_tool_provider_registry()
    policies: dict[str, ProviderToolAccessPolicy] = {}
    for name in enabled:
        provider = provider_registry.create(name, agents)
        if not isinstance(provider, ProviderToolAccessWorkspaceToolProvider):
            continue
        if (
            isinstance(provider, ProviderToolAccessConfigurableWorkspaceToolProvider)
            and not provider.has_provider_tool_access_config()
        ):
            continue
        provider.initialize()
        policy = provider.provider_tool_access()
        if policy.provider_name in policies:
            raise WorkspaceToolProviderConfigError(
                f"Duplicate provider tool access policy: {policy.provider_name}"
            )
        policies[policy.provider_name] = policy
    return policies


def default_tool_service() -> ToolService:
    """Return a fresh ToolService wired to current production state."""
    return ToolService()


def tool_service_for_loaded_agent(
    agent: Any,
    *,
    fallback_agent_id: str,
    cli_provider: str,
) -> ToolService:
    """Return ToolService using a caller-loaded agent as an input adapter."""
    if isinstance(agent, Agent):
        resolved = agent
    else:
        resolved = Agent(
            id=fallback_agent_id,
            display_name=str(
                getattr(agent, "display_name", fallback_agent_id) or fallback_agent_id
            ),
            cli_provider=cli_provider,
            workdir=str(getattr(agent, "workdir", "/tmp") or "/tmp"),
            session_name=str(
                getattr(agent, "session_name", fallback_agent_id) or fallback_agent_id
            ),
            prompt=str(getattr(agent, "prompt", "") or ""),
            mcp_servers=_mapping_or_empty(getattr(agent, "mcp_servers", {})),
            cao_tools=_optional_tuple(getattr(agent, "cao_tools", None)),
            runtime_capabilities=_optional_tuple(getattr(agent, "runtime_capabilities", None)),
            codex_config=_mapping_or_empty(getattr(agent, "codex_config", {})),
        )
    try:
        agents = dict(load_agent_registry().all())
    except Exception:
        agents = {}
    agents[resolved.id] = resolved
    if fallback_agent_id and fallback_agent_id != resolved.id:
        agents[fallback_agent_id] = resolved
    return ToolService(agent_manager=AgentManager(configured_agents=AgentRegistry(agents)))


def _runtime_capabilities_input(agent: Agent) -> tuple[str, ...] | None:
    if agent.runtime_capabilities is None:
        return None
    return tuple(agent.runtime_capabilities)


def _local_mcp_servers_from_agent(agent: Agent) -> Mapping[str, Mapping[str, Any]]:
    servers: dict[str, Mapping[str, Any]] = {}
    for name, server in agent.mcp_servers.items():
        entry = _mcp_server_entry(server)
        if entry is not None:
            servers[name] = entry
    nested = agent.codex_config.get("mcp_servers")
    if isinstance(nested, Mapping):
        for name, server in nested.items():
            entry = _mcp_server_entry(server)
            if isinstance(name, str) and entry is not None:
                servers[name] = entry
    return servers


def _inactive_local_grants(agent: Agent) -> Mapping[str, Any]:
    if agent.workspace.team is None:
        return {}
    inactive: dict[str, Any] = {}
    if agent.cao_tools is not None:
        inactive["cao_tools"] = list(agent.cao_tools)
    if agent.mcp_servers:
        inactive["mcp_servers"] = dict(agent.mcp_servers)
    nested_mcp = agent.codex_config.get("mcp_servers")
    if isinstance(nested_mcp, Mapping):
        inactive["codex_config.mcp_servers"] = dict(nested_mcp)
    return inactive


def _agent_registry_cache_token(registry: AgentRegistry) -> tuple[Any, ...]:
    return tuple(
        _agent_cache_token(agent)
        for agent in sorted(registry.all().values(), key=lambda item: item.id)
    )


def _agent_cache_token(agent: Agent) -> tuple[Any, ...]:
    return (
        agent.id,
        agent.cli_provider,
        agent.workdir,
        agent.session_name,
        _cache_token(agent.cao_tools),
        _cache_token(agent.mcp_servers),
        _cache_token(agent.codex_config),
        _cache_token(agent.runtime_capabilities),
        _cache_token(agent.workspace.team),
    )


def _source_result_cache_token(source_result: ToolAccessSourceResult) -> tuple[Any, ...]:
    return (
        source_result.agent_id,
        source_result.team_id,
        source_result.role_id,
        source_result.provider_access_source,
        _cache_token(source_result.local_cao_tools),
        _cache_token(source_result.direct_mcp_servers),
        _cache_token(source_result.provider_role_grants),
        _cache_token(source_result.runtime_capabilities),
        _cache_token(source_result.source_markers),
        _cache_token(source_result.inactive_local_grants),
    )


def _workspace_tool_provider_config_cache_token() -> tuple[str, int | None, int | None]:
    path = WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH
    try:
        stat = path.stat()
    except OSError:
        return (str(path), None, None)
    return (str(path), stat.st_mtime_ns, stat.st_size)


def _cache_token(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _cache_token(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, tuple):
        return tuple(_cache_token(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_cache_token(item) for item in value)
    if hasattr(value, "__dataclass_fields__"):
        return tuple(
            (field_name, _cache_token(getattr(value, field_name)))
            for field_name in sorted(value.__dataclass_fields__)
        )
    return repr(value)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        entry = _mcp_server_entry(item)
        result[str(key)] = entry if entry is not None else item
    return result


def _mcp_server_entry(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return _copy_jsonish_mapping(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, Mapping):
            return _copy_jsonish_mapping(dumped)
    return None


def _copy_jsonish_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            copied[str(key)] = _copy_jsonish_mapping(item)
        elif isinstance(item, (list, tuple)):
            copied[str(key)] = [
                _copy_jsonish_mapping(child) if isinstance(child, Mapping) else child
                for child in item
            ]
        else:
            copied[str(key)] = item
    return copied


def _optional_tuple(value: Any) -> tuple[str, ...] | None:
    if value is None or not isinstance(value, (list, tuple)):
        return None
    return tuple(str(item) for item in value)


def _is_team_owned_provider_access(entry: ProviderToolAccess) -> bool:
    source = entry.source_location.strip().lower()
    return source.startswith("workspace_team.") or source.startswith("team_role.")


__all__ = [
    "AgentToolAccess",
    "AgentToolView",
    "MANAGED_CAO_MCP_SERVER",
    "ToolAccessDecision",
    "ToolAccessDiagnostic",
    "ToolAccessResolver",
    "ToolRegistration",
    "ToolService",
    "StandaloneAgentToolAccessSource",
    "TeamRoleToolAccessSource",
    "default_tool_service",
    "tool_service_for_loaded_agent",
]

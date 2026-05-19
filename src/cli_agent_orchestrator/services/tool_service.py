"""Authoritative CAO tool registration, access, and materialization service."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping, Optional

from cli_agent_orchestrator.agent import Agent, AgentRegistry, load_agent_registry
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxDelivery
from cli_agent_orchestrator.services.agent_manager import AgentManager, default_agent_manager
from cli_agent_orchestrator.utils.tool_mapping import resolve_runtime_capabilities
from cli_agent_orchestrator.workspace_providers.registry import (
    ProviderConversationAccessWorkspaceProvider,
    ProviderToolAccessConfigurableWorkspaceProvider,
    ProviderToolAccessWorkspaceProvider,
    WorkspaceProviderConfigError,
    WorkspaceProviderRegistry,
    default_workspace_provider_registry,
    load_enabled_workspace_providers,
    workspace_provider_config_exists,
)
from cli_agent_orchestrator.workspace_providers.tool_access import (
    ProviderConversationAccessRequirement,
    ProviderMediatedToolDefinition,
    ProviderToolAccess,
    ProviderToolAccessConfigError,
    ProviderToolAccessPolicy,
)
from cli_agent_orchestrator.workspace_setups import (
    WorkspaceCollaborationManager,
    WorkspaceSetupConfigError,
    default_workspace_collaboration_manager,
)

logger = logging.getLogger(__name__)

TerminalMetadataResolver = Callable[[str], Mapping[str, Any] | None]
ProviderPolicyLoader = Callable[[AgentRegistry], Mapping[str, ProviderToolAccessPolicy]]
ProviderConversationRequirementLoader = Callable[
    [AgentRegistry], Mapping[str, tuple[ProviderConversationAccessRequirement, ...]]
]
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
    def allow(cls, *, reason: str = "allowed", diagnostics: Mapping[str, Any] | None = None):
        return cls(allowed=True, reason=reason, diagnostics=dict(diagnostics or {}))

    @classmethod
    def deny(cls, reason: str, *, diagnostics: Mapping[str, Any] | None = None):
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
    runtime_capabilities: tuple[str, ...]
    source_markers: Mapping[str, str]
    inactive_local_grants: Mapping[str, Any]
    provider_conversation_requirements: tuple[ProviderConversationAccessRequirement, ...]
    diagnostics: tuple[ToolAccessDiagnostic, ...]


@dataclass(frozen=True)
class ToolRegistration:
    """Effective MCP registration for one terminal."""

    terminal_id: str
    agent_id: str
    built_in_tools: tuple[str, ...]
    provider_mediated_tools: tuple[tuple[str, ProviderMediatedToolDefinition], ...]
    registered_tools: tuple[str, ...]
    diagnostics: tuple[ToolAccessDiagnostic, ...]


class ToolService:
    """Single production authority for effective CAO tool access."""

    def __init__(
        self,
        *,
        agent_manager: AgentManager | None = None,
        terminal_metadata_resolver: TerminalMetadataResolver = db_module.get_terminal_metadata,
        provider_policy_loader: ProviderPolicyLoader | None = None,
        provider_conversation_requirement_loader: (
            ProviderConversationRequirementLoader | None
        ) = None,
        collaboration_manager_factory: CollaborationManagerFactory | None = None,
    ) -> None:
        self._agent_manager = agent_manager or default_agent_manager()
        self._terminal_metadata_resolver = terminal_metadata_resolver
        self._provider_policy_loader = provider_policy_loader
        self._provider_conversation_requirement_loader = provider_conversation_requirement_loader
        self._collaboration_manager_factory = collaboration_manager_factory or (
            lambda registry: default_workspace_collaboration_manager(agent_registry=registry)
        )

    def tools_for_agent(
        self,
        agent_id: str,
        *,
        built_in_tool_names: Iterable[str] = (),
    ) -> AgentToolAccess:
        """Return effective access for one agent through the owner boundary."""
        agent = self._agent_manager.resolve_agent(agent_id)
        built_in_names = tuple(dict.fromkeys(name for name in built_in_tool_names if name))
        team_id = agent.workspace.team
        diagnostics: list[ToolAccessDiagnostic] = []
        inactive_local = self._inactive_local_grants(agent)
        if team_id is not None and inactive_local:
            diagnostics.append(
                ToolAccessDiagnostic(
                    code="inactive_teamed_local_tool_access",
                    message=(
                        f"Agent {agent.id} belongs to workspace team {team_id}; "
                        "agent-local tool grants are retained for diagnostics only."
                    ),
                    source="agent_config",
                )
            )

        local_cao_tools = self._effective_local_cao_tools(agent, built_in_names)
        provider_policies = self.provider_policies_for_agent(agent.id)
        provider_access = tuple(
            access for policy in provider_policies.values() for access in policy.access
        )
        built_in_effective = self._effective_built_in_tools(
            built_in_names=built_in_names,
            local_cao_tools=local_cao_tools,
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
        direct_mcp_servers = self._effective_direct_mcp_servers(agent)
        materialized_mcp_servers = self.materialized_mcp_servers_for_agent(agent.id)
        runtime_capabilities = tuple(
            resolve_runtime_capabilities(
                self._effective_runtime_capabilities_input(agent),
                list(materialized_mcp_servers),
            )
        )
        allowed = tuple(dict.fromkeys((*built_in_effective, *provider_tool_names)))
        registered = tuple(dict.fromkeys((*allowed, *(f"@{name}" for name in materialized_mcp_servers))))
        source_markers = {
            **{name: self._built_in_source(agent) for name in built_in_effective},
            **{
                access.tool_name: f"{access.provider_name}:{access.source_location}"
                for access in provider_access
            },
            **{f"@{name}": self._mcp_source(agent, name) for name in materialized_mcp_servers},
        }
        return AgentToolAccess(
            agent_id=agent.id,
            team_id=team_id,
            role_id=None,
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
            inactive_local_grants=inactive_local,
            provider_conversation_requirements=self.provider_conversation_requirements_for_agent(
                agent.id
            ),
            diagnostics=tuple(diagnostics),
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
                dict.fromkeys((*access.built_in_cao_tools, *(tool.name for _, tool in provider_tools)))
            ),
            diagnostics=access.diagnostics,
        )

    def provider_policy(self, provider_name: str) -> ProviderToolAccessPolicy | None:
        """Return the current effective provider policy for all agents."""
        return self.provider_policies().get(provider_name.strip().lower())

    def provider_policies(self) -> Mapping[str, ProviderToolAccessPolicy]:
        """Return provider policies filtered through ToolService authority."""
        raw = self._raw_provider_policies()
        agents = self._agent_registry()
        effective: dict[str, ProviderToolAccessPolicy] = {}
        for provider_name, policy in raw.items():
            entries: list[ProviderToolAccess] = []
            for agent in agents.all().values():
                agent_policy = self._policy_for_agent(policy, agent)
                entries.extend(agent_policy.access)
            effective[provider_name] = replace(
                policy,
                access=tuple(
                    sorted(
                        {self._access_key(entry): entry for entry in entries}.values(),
                        key=lambda item: (item.agent_id, item.tool_name, item.source_location),
                    )
                ),
            )
        return effective

    def provider_policies_for_agent(
        self, agent_id: str
    ) -> Mapping[str, ProviderToolAccessPolicy]:
        """Return provider policies scoped to one agent's effective access."""
        agent = self._agent_manager.resolve_agent(agent_id)
        return {
            provider_name: self._policy_for_agent(policy, agent)
            for provider_name, policy in self._raw_provider_policies().items()
        }

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

    def materialized_mcp_servers_for_agent(
        self, agent_id: str
    ) -> Mapping[str, Mapping[str, Any]]:
        """Return effective direct/custom MCP servers to materialize."""
        agent = self._agent_manager.resolve_agent(agent_id)
        servers: dict[str, Mapping[str, Any]] = {}
        servers.update(self._effective_direct_mcp_servers(agent))
        managed = self._managed_cao_mcp_server(agent)
        existing = servers.get(MANAGED_CAO_MCP_SERVER)
        if isinstance(existing, Mapping):
            managed = {**managed, **{key: existing[key] for key in ("env", "cwd") if key in existing}}
        servers[MANAGED_CAO_MCP_SERVER] = managed
        return {name: _copy_jsonish_mapping(config) for name, config in sorted(servers.items())}

    def runtime_capabilities_for_agent(self, agent_id: str) -> tuple[str, ...]:
        """Return effective runtime capabilities, including MCP server markers."""
        agent = self._agent_manager.resolve_agent(agent_id)
        return tuple(
            resolve_runtime_capabilities(
                self._effective_runtime_capabilities_input(agent),
                list(self.materialized_mcp_servers_for_agent(agent.id)),
            )
        )

    def codex_config_for_agent(self, agent_id: str) -> Mapping[str, Any]:
        """Return agent Codex config with MCP server authority removed."""
        agent = self._agent_manager.resolve_agent(agent_id)
        config = dict(agent.codex_config)
        config.pop("mcp_servers", None)
        return config

    def provider_conversation_requirements_for_agent(
        self, agent_id: str
    ) -> tuple[ProviderConversationAccessRequirement, ...]:
        """Return provider-conversation operations ToolService can decide."""
        agent = self._agent_manager.resolve_agent(agent_id)
        if agent.workspace.team is None:
            return ()
        try:
            manager = self._collaboration_manager()
            setup = manager.setup_for_agent(agent)
            if setup is None:
                return ()
            setup_providers = {provider.strip().lower() for provider in setup.providers}
        except Exception:
            logger.exception("Failed to resolve team providers for agent %s", agent.id)
            return ()

        requirements: list[ProviderConversationAccessRequirement] = []
        for provider_name, provider_requirements in self._provider_conversation_requirements().items():
            if provider_name not in setup_providers:
                continue
            requirements.extend(provider_requirements)
        return tuple(
            sorted(
                {
                    (
                        item.provider_name.strip().lower(),
                        item.operation.strip().lower(),
                        item.required_identity.strip().lower(),
                    ): ProviderConversationAccessRequirement(
                        provider_name=item.provider_name.strip().lower(),
                        operation=item.operation.strip().lower(),
                        required_identity=item.required_identity.strip().lower(),
                    )
                    for item in requirements
                    if item.provider_name.strip() and item.operation.strip()
                }.values(),
                key=lambda item: (item.provider_name, item.operation, item.required_identity),
            )
        )

    def provider_conversation_decision(
        self,
        agent_id: str,
        *,
        provider: str,
        operation: str,
        source: str,
        provider_identity: str | None = None,
    ) -> ToolAccessDecision:
        """Return a provider-conversation allow/deny decision."""
        normalized_provider = provider.strip().lower()
        normalized_operation = operation.strip().lower()
        agent = self._agent_manager.resolve_agent(agent_id)
        requirement = next(
            (
                item
                for item in self.provider_conversation_requirements_for_agent(agent.id)
                if item.provider_name == normalized_provider
                and item.operation == normalized_operation
            ),
            None,
        )
        if requirement is None:
            return ToolAccessDecision.deny(
                "provider_conversation_operation_not_registered",
                diagnostics={
                    "provider": normalized_provider,
                    "operation": normalized_operation,
                    "source": source,
                },
            )
        if requirement.required_identity != "workspace_team_presence":
            return ToolAccessDecision.deny(
                "provider_conversation_requirement_unsupported",
                diagnostics={
                    "provider": normalized_provider,
                    "operation": normalized_operation,
                    "required_identity": requirement.required_identity,
                    "source": source,
                },
            )
        if not provider_identity:
            return ToolAccessDecision.deny(
                "missing_provider_identity",
                diagnostics={
                    "provider": normalized_provider,
                    "operation": normalized_operation,
                    "source": source,
                },
            )
        try:
            manager = self._collaboration_manager()
            team = manager.team_for_agent(agent)
            if team is None:
                raise WorkspaceSetupConfigError(
                    f"caller agent {agent.id} has no workspace team for provider conversation access"
                )
            provider_view = manager.provider_view(team.id, normalized_provider)
            presence = provider_view.value.presence_by_app_key(provider_identity)
        except Exception as exc:
            return ToolAccessDecision.deny(
                "provider_conversation_policy_unavailable",
                diagnostics={
                    "provider": normalized_provider,
                    "operation": normalized_operation,
                    "detail": str(exc),
                },
            )
        if presence is None or presence.agent_id != agent.id:
            return ToolAccessDecision.deny(
                "provider_conversation_denied",
                diagnostics={
                    "provider": normalized_provider,
                    "operation": normalized_operation,
                    "agent_id": agent.id,
                    "provider_identity": provider_identity,
                },
            )
        return ToolAccessDecision.allow(
            reason="provider_conversation_allowed",
            diagnostics={
                "provider": normalized_provider,
                "operation": normalized_operation,
                "agent_id": agent.id,
                "provider_identity": provider_identity,
            },
        )

    def provider_conversation_decision_for_inbox(
        self,
        delivery: InboxDelivery,
        *,
        caller_terminal_id: str | None,
        provider: str,
        operation: str,
        provider_identity: str | None,
    ) -> ToolAccessDecision:
        """Return provider-conversation decision for an inbox read/reply surface."""
        if not caller_terminal_id:
            return ToolAccessDecision.deny("missing_caller_terminal")
        agent = self.agent_for_terminal(caller_terminal_id)
        return self.provider_conversation_decision(
            agent.id,
            provider=provider,
            operation=operation,
            source=f"inbox_notification:{delivery.notification.id}",
            provider_identity=provider_identity,
        )

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

    def _effective_local_cao_tools(
        self, agent: Agent, built_in_names: tuple[str, ...]
    ) -> tuple[str, ...] | None:
        if agent.workspace.team is not None:
            return ()
        return None if agent.cao_tools is None else tuple(agent.cao_tools)

    def _effective_direct_mcp_servers(self, agent: Agent) -> Mapping[str, Mapping[str, Any]]:
        if agent.workspace.team is not None:
            return {}
        return self._local_mcp_servers_from_agent(agent)

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

    def _local_mcp_servers_from_agent(self, agent: Agent) -> Mapping[str, Mapping[str, Any]]:
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

    def _inactive_local_grants(self, agent: Agent) -> Mapping[str, Any]:
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
        if agent.linear is not None and agent.linear.tool_access:
            inactive["linear.tool_access"] = [access.access_id for access in agent.linear.tool_access]
        return inactive

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
        if agent.workspace.team is None:
            return replace(policy, access=access)
        try:
            manager = self._collaboration_manager()
            setup = manager.setup_for_agent(agent)
            if setup is None or policy.provider_name not in setup.providers:
                return replace(policy, access=())
            authorized_locations = manager.authorized_tool_access_locations(policy.provider_name)
        except Exception:
            logger.exception(
                "Failed to resolve workspace setup provider access for teamed agent %r",
                agent.id,
            )
            return replace(policy, access=())
        return replace(
            policy,
            access=tuple(
                entry
                for entry in access
                if _is_team_owned_provider_access(entry)
                and entry.source_location in authorized_locations
            ),
        )

    def _raw_provider_policies(self) -> Mapping[str, ProviderToolAccessPolicy]:
        if self._provider_policy_loader is not None:
            return self._provider_policy_loader(self._agent_registry())
        try:
            return _load_raw_enabled_provider_tool_access_policies(
                agent_registry=self._agent_registry()
            )
        except (ProviderToolAccessConfigError, WorkspaceProviderConfigError):
            raise
        except Exception:
            logger.exception("Provider-mediated tool access loading failed")
            return {}

    def _provider_conversation_requirements(
        self,
    ) -> Mapping[str, tuple[ProviderConversationAccessRequirement, ...]]:
        if self._provider_conversation_requirement_loader is not None:
            return self._provider_conversation_requirement_loader(self._agent_registry())
        try:
            return _load_raw_enabled_provider_conversation_requirements(
                agent_registry=self._agent_registry()
            )
        except WorkspaceProviderConfigError:
            raise
        except Exception:
            logger.exception("Provider-conversation requirement loading failed")
            return {}

    def _agent_registry(self) -> AgentRegistry:
        return AgentRegistry({agent.id: agent for agent in self._agent_manager.list_agents()})

    def _collaboration_manager(self) -> WorkspaceCollaborationManager:
        return self._collaboration_manager_factory(self._agent_registry())

    @staticmethod
    def _access_key(entry: ProviderToolAccess) -> tuple[str, str, str, str]:
        return (entry.provider_name, entry.agent_id, entry.tool_name, entry.source_location)


def _load_raw_enabled_provider_tool_access_policies(
    *,
    agent_registry: AgentRegistry | None = None,
    enabled_config_path: Any = None,
    registry: WorkspaceProviderRegistry | None = None,
) -> Mapping[str, ProviderToolAccessPolicy]:
    """Load provider-owned tool definitions/access as ToolService input."""
    enabled = load_enabled_workspace_providers(enabled_config_path)
    agents = agent_registry or load_agent_registry()
    provider_registry = registry or default_workspace_provider_registry()
    policies: dict[str, ProviderToolAccessPolicy] = {}
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
        policy = provider.provider_tool_access()
        if policy.provider_name in policies:
            raise WorkspaceProviderConfigError(
                f"Duplicate provider tool access policy: {policy.provider_name}"
            )
        policies[policy.provider_name] = policy
    return policies


def _load_raw_enabled_provider_conversation_requirements(
    *,
    agent_registry: AgentRegistry | None = None,
    enabled_config_path: Any = None,
    registry: WorkspaceProviderRegistry | None = None,
) -> Mapping[str, tuple[ProviderConversationAccessRequirement, ...]]:
    """Load provider-owned provider-conversation descriptors as ToolService input."""
    if workspace_provider_config_exists(enabled_config_path):
        enabled = load_enabled_workspace_providers(enabled_config_path)
    else:
        enabled = ("linear",)
    agents = agent_registry or load_agent_registry()
    provider_registry = registry or default_workspace_provider_registry()
    requirements: dict[str, tuple[ProviderConversationAccessRequirement, ...]] = {}
    for name in enabled:
        provider = provider_registry.create(name, agents)
        if not isinstance(provider, ProviderConversationAccessWorkspaceProvider):
            continue
        declared = tuple(
            ProviderConversationAccessRequirement(
                provider_name=item.provider_name.strip().lower(),
                operation=item.operation.strip().lower(),
                required_identity=item.required_identity.strip().lower(),
            )
            for item in provider.provider_conversation_access()
            if item.provider_name.strip() and item.operation.strip()
        )
        if not declared:
            continue
        provider_name = declared[0].provider_name
        if provider_name in requirements:
            raise WorkspaceProviderConfigError(
                f"Duplicate provider conversation access requirements: {provider_name}"
            )
        requirements[provider_name] = tuple(
            sorted(
                {
                    (item.provider_name, item.operation, item.required_identity): item
                    for item in declared
                }.values(),
                key=lambda item: (item.provider_name, item.operation, item.required_identity),
            )
        )
    return requirements


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
            display_name=str(getattr(agent, "display_name", fallback_agent_id) or fallback_agent_id),
            cli_provider=cli_provider,
            workdir=str(getattr(agent, "workdir", "/tmp") or "/tmp"),
            session_name=str(getattr(agent, "session_name", fallback_agent_id) or fallback_agent_id),
            prompt=str(getattr(agent, "prompt", "") or ""),
            mcp_servers=_mapping_or_empty(getattr(agent, "mcp_servers", {})),
            cao_tools=_optional_tuple(getattr(agent, "cao_tools", None)),
            runtime_capabilities=_optional_tuple(getattr(agent, "runtime_capabilities", None)),
            codex_config=_mapping_or_empty(getattr(agent, "codex_config", {})),
        )
    agents = {resolved.id: resolved}
    if fallback_agent_id and fallback_agent_id != resolved.id:
        agents[fallback_agent_id] = resolved
    return ToolService(agent_manager=AgentManager(configured_agents=AgentRegistry(agents)))


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
    "MANAGED_CAO_MCP_SERVER",
    "ProviderConversationAccessRequirement",
    "ToolAccessDecision",
    "ToolAccessDiagnostic",
    "ToolRegistration",
    "ToolService",
    "default_tool_service",
    "tool_service_for_loaded_agent",
]

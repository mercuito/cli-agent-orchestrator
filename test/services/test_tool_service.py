from __future__ import annotations

from typing import Any, Mapping

import pytest

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig
from cli_agent_orchestrator.services.agent_manager import AgentManager
from cli_agent_orchestrator.services.tool_service import ToolService
from cli_agent_orchestrator.workspace_providers.tool_access import (
    ProviderConversationAccessRequirement,
    ProviderMediatedToolDefinition,
    ProviderToolAccess,
    ProviderToolAccessPolicy,
)


def _agent(
    agent_id: str = "agent",
    *,
    team: str | None = None,
    cao_tools: tuple[str, ...] | None = None,
    mcp_servers: Mapping[str, Mapping[str, Any]] | None = None,
    runtime_capabilities: tuple[str, ...] | None = None,
    codex_config: Mapping[str, Any] | None = None,
) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(team=team),
        cao_tools=cao_tools,
        mcp_servers=mcp_servers or {},
        runtime_capabilities=runtime_capabilities,
        codex_config=codex_config or {},
    )


def _manager(*agents: Agent, terminals: list[dict[str, object]] | None = None) -> AgentManager:
    return AgentManager(
        configured_agents=AgentRegistry({agent.id: agent for agent in agents}),
        terminal_lister=lambda: list(terminals or []),
        terminal_metadata_resolver=lambda terminal_id: {
            str(terminal["id"]): terminal for terminal in terminals or []
        }.get(terminal_id),
    )


def test_unteamed_local_access_is_effective_through_tool_service():
    agent = _agent(
        cao_tools=("send_message",),
        mcp_servers={"custom": {"command": "custom-mcp"}},
        runtime_capabilities=("fs_read",),
        codex_config={"mcp_servers": {"nested": {"command": "nested-mcp"}}},
    )
    service = ToolService(agent_manager=_manager(agent))

    access = service.tools_for_agent(agent.id, built_in_tool_names=("send_message", "assign"))

    assert access.built_in_cao_tools == ("send_message",)
    assert set(access.materialized_mcp_servers) == {"cao-mcp-server", "custom", "nested"}
    assert access.runtime_capabilities == (
        "fs_read",
        "@cao-mcp-server",
        "@custom",
        "@nested",
    )
    assert access.inactive_local_grants == {}


def test_teamed_local_access_is_inactive_and_not_materialized():
    agent = _agent(
        team="delivery",
        cao_tools=("send_message",),
        mcp_servers={"custom": {"command": "custom-mcp"}},
        runtime_capabilities=("fs_read",),
        codex_config={"mcp_servers": {"nested": {"command": "nested-mcp"}}},
    )
    service = ToolService(agent_manager=_manager(agent))

    access = service.tools_for_agent(agent.id, built_in_tool_names=("send_message", "assign"))

    assert access.built_in_cao_tools == ()
    assert set(access.materialized_mcp_servers) == {"cao-mcp-server"}
    assert access.runtime_capabilities == ("fs_read", "@cao-mcp-server")
    assert access.inactive_local_grants == {
        "cao_tools": ["send_message"],
        "mcp_servers": {"custom": {"command": "custom-mcp"}},
        "codex_config.mcp_servers": {"nested": {"command": "nested-mcp"}},
    }
    assert [diagnostic.code for diagnostic in access.diagnostics] == [
        "inactive_teamed_local_tool_access"
    ]


def test_registered_tools_for_terminal_uses_current_tool_service_decision():
    agent = _agent(cao_tools=("send_message",))
    service = ToolService(
        agent_manager=_manager(agent, terminals=[{"id": "terminal-1", "agent_id": agent.id}]),
        terminal_metadata_resolver=lambda terminal_id: {"agent_id": agent.id}
        if terminal_id == "terminal-1"
        else None,
    )

    registration = service.registered_tools_for_terminal(
        "terminal-1",
        built_in_tool_names=("send_message", "assign"),
    )

    assert registration.agent_id == agent.id
    assert registration.built_in_tools == ("send_message",)
    assert registration.registered_tools == ("send_message",)


def test_teamed_builtin_cao_tools_are_not_widened_without_team_source():
    agent = _agent(team="delivery", cao_tools=("send_message",))
    service = ToolService(
        agent_manager=_manager(agent, terminals=[{"id": "terminal-1", "agent_id": agent.id}]),
        terminal_metadata_resolver=lambda terminal_id: {"agent_id": agent.id}
        if terminal_id == "terminal-1"
        else None,
    )

    registration = service.registered_tools_for_terminal(
        "terminal-1",
        built_in_tool_names=("send_message", "assign", "terminate"),
    )
    decision = service.can_invoke(
        agent.id,
        "assign",
        built_in_tool_names=("send_message", "assign", "terminate"),
    )

    assert registration.built_in_tools == ()
    assert decision.allowed is False
    assert decision.reason == "built_in_tool_denied"


def test_builtin_invocation_denies_unknown_tools_without_catalog_entry():
    agent = _agent(cao_tools=None)
    service = ToolService(agent_manager=_manager(agent))

    decision = service.can_invoke(
        agent.id,
        "not_a_registered_builtin",
        built_in_tool_names=("send_message", "assign"),
    )

    assert decision.allowed is False
    assert decision.reason == "built_in_tool_denied"


def test_provider_mediated_access_is_scoped_by_tool_service():
    agent = _agent()
    policy = ProviderToolAccessPolicy(
        provider_name="linear",
        tools={
            "cao_linear.get_issue": ProviderMediatedToolDefinition(
                name="cao_linear.get_issue",
                description="Read issue",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            )
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="linear",
                tool_name="cao_linear.get_issue",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="linear.tool_access.reads",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_policy_loader=lambda _registry: {"linear": policy},
    )

    access = service.tools_for_agent(agent.id)
    decision = service.can_invoke(agent.id, "cao_linear.get_issue", provider_name="linear")

    assert access.provider_mediated_tools == {"linear": ("cao_linear.get_issue",)}
    assert decision.allowed is True


def test_provider_mediated_registration_skips_builtin_name_conflicts():
    agent = _agent()
    policy = ProviderToolAccessPolicy(
        provider_name="linear",
        tools={
            "send_message": ProviderMediatedToolDefinition(
                name="send_message",
                description="Conflicting provider tool",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            )
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="linear",
                tool_name="send_message",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="linear.tool_access.conflict",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent, terminals=[{"id": "terminal-1", "agent_id": agent.id}]),
        terminal_metadata_resolver=lambda terminal_id: {"agent_id": agent.id}
        if terminal_id == "terminal-1"
        else None,
        provider_policy_loader=lambda _registry: {"linear": policy},
    )

    access = service.tools_for_agent(agent.id, built_in_tool_names=("send_message",))
    registration = service.registered_tools_for_terminal(
        "terminal-1",
        built_in_tool_names=("send_message",),
    )
    decision = service.can_invoke(
        agent.id,
        "send_message",
        provider_name="linear",
        built_in_tool_names=("send_message",),
    )

    assert access.provider_mediated_tools == {"linear": ()}
    assert registration.provider_mediated_tools == ()
    assert decision.allowed is False


def test_provider_mediated_registration_deduplicates_names_in_tool_service():
    agent = _agent()
    first_tool = ProviderMediatedToolDefinition(
        name="cao_shared.lookup",
        description="First provider",
        input_schema={},
        handler=lambda _context, _arguments: {"provider": "first"},
    )
    second_tool = ProviderMediatedToolDefinition(
        name="cao_shared.lookup",
        description="Second provider",
        input_schema={},
        handler=lambda _context, _arguments: {"provider": "second"},
    )
    first_policy = ProviderToolAccessPolicy(
        provider_name="alpha",
        tools={"cao_shared.lookup": first_tool},
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="alpha",
                tool_name="cao_shared.lookup",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="alpha.tool_access.lookup",
            ),
        ),
    )
    second_policy = ProviderToolAccessPolicy(
        provider_name="beta",
        tools={"cao_shared.lookup": second_tool},
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="beta",
                tool_name="cao_shared.lookup",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="beta.tool_access.lookup",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent, terminals=[{"id": "terminal-1", "agent_id": agent.id}]),
        terminal_metadata_resolver=lambda terminal_id: {"agent_id": agent.id}
        if terminal_id == "terminal-1"
        else None,
        provider_policy_loader=lambda _registry: {
            "alpha": first_policy,
            "beta": second_policy,
        },
    )

    access = service.tools_for_agent(agent.id)
    registration = service.registered_tools_for_terminal("terminal-1")

    assert access.provider_mediated_tools == {
        "alpha": ("cao_shared.lookup",),
        "beta": (),
    }
    assert registration.provider_mediated_tools == (("alpha", first_tool),)


def test_teamed_provider_access_fails_closed_when_team_policy_is_invalid():
    agent = _agent(agent_id="agent", team="missing-team")
    policy = ProviderToolAccessPolicy(
        provider_name="linear",
        tools={
            "cao_linear.get_issue": ProviderMediatedToolDefinition(
                name="cao_linear.get_issue",
                description="Read issue",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            )
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="linear",
                tool_name="cao_linear.get_issue",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="linear.tool_access.reads",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_policy_loader=lambda _registry: {"linear": policy},
        collaboration_manager_factory=lambda _registry: _InvalidTeamManager(),
    )

    access = service.tools_for_agent(agent.id)

    assert access.provider_mediated_tools == {"linear": ()}
    assert (
        service.can_invoke(agent.id, "cao_linear.get_issue", provider_name="linear").allowed
        is False
    )


def test_teamed_provider_local_access_is_inactive_not_effective():
    agent = _agent(agent_id="agent", team="delivery")
    policy = ProviderToolAccessPolicy(
        provider_name="linear",
        tools={
            "cao_linear.get_issue": ProviderMediatedToolDefinition(
                name="cao_linear.get_issue",
                description="Read issue",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            )
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="linear",
                tool_name="cao_linear.get_issue",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="agents.agent.linear.tool_access.reads",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_policy_loader=lambda _registry: {"linear": policy},
    )

    access = service.tools_for_agent(agent.id)
    decision = service.can_invoke(agent.id, "cao_linear.get_issue", provider_name="linear")

    assert access.provider_mediated_tools == {"linear": ()}
    assert access.allowed_tools == ()
    assert decision.allowed is False
    assert decision.reason == "provider_tool_denied"


def test_teamed_provider_access_requires_workspace_setup_authorized_location():
    agent = _agent(agent_id="agent", team="delivery")
    policy = ProviderToolAccessPolicy(
        provider_name="linear",
        tools={
            "cao_linear.get_issue": ProviderMediatedToolDefinition(
                name="cao_linear.get_issue",
                description="Read issue",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            ),
            "cao_linear.create_issue": ProviderMediatedToolDefinition(
                name="cao_linear.create_issue",
                description="Create issue",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            ),
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="linear",
                tool_name="cao_linear.get_issue",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="workspace_team.delivery.linear.reads",
            ),
            ProviderToolAccess(
                provider_name="linear",
                tool_name="cao_linear.create_issue",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="workspace_team.delivery.linear.create",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_policy_loader=lambda _registry: {"linear": policy},
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            authorized_locations=("workspace_team.delivery.linear.reads",)
        ),
    )

    access = service.tools_for_agent(agent.id)

    assert access.provider_mediated_tools == {"linear": ("cao_linear.get_issue",)}
    assert service.can_invoke(
        agent.id, "cao_linear.get_issue", provider_name="linear"
    ).allowed
    assert (
        service.can_invoke(agent.id, "cao_linear.create_issue", provider_name="linear").allowed
        is False
    )


def test_provider_conversation_missing_identity_denies_through_tool_service():
    agent = _agent(agent_id="agent", team="delivery")
    service = ToolService(
        agent_manager=_manager(agent),
        provider_conversation_requirement_loader=lambda _registry: {
            "linear": (
                ProviderConversationAccessRequirement(
                    provider_name="linear",
                    operation="read",
                    required_identity="workspace_team_presence",
                ),
            )
        },
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(),
    )

    decision = service.provider_conversation_decision(
        agent.id,
        provider="linear",
        operation="read",
        source="test",
        provider_identity=None,
    )

    assert decision.allowed is False
    assert decision.reason == "missing_provider_identity"


def test_provider_conversation_denies_operations_missing_provider_descriptor():
    agent = _agent(agent_id="agent", team="delivery")
    service = ToolService(
        agent_manager=_manager(agent),
        provider_conversation_requirement_loader=lambda _registry: {
            "linear": (
                ProviderConversationAccessRequirement(
                    provider_name="linear",
                    operation="read",
                    required_identity="workspace_team_presence",
                ),
            )
        },
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(),
    )

    decision = service.provider_conversation_decision(
        agent.id,
        provider="linear",
        operation="read_reply",
        source="test",
        provider_identity="agent",
    )

    assert decision.allowed is False
    assert decision.reason == "provider_conversation_operation_not_registered"


class _InvalidTeamManager:
    def setup_for_agent(self, agent):
        raise RuntimeError("invalid team")


class _ProviderSetupManager:
    def __init__(self, authorized_locations: tuple[str, ...] = ()) -> None:
        self._authorized_locations = authorized_locations

    def setup_for_agent(self, agent):
        return _ProviderSetup()

    def authorized_tool_access_locations(self, provider_name: str):
        if provider_name != "linear":
            return frozenset()
        return frozenset(self._authorized_locations)


class _ProviderSetup:
    providers = ("linear",)

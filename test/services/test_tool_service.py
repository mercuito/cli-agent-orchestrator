from __future__ import annotations

from typing import Any, Mapping

import pytest

from cli_agent_orchestrator.agent import (
    Agent,
    AgentRegistry,
    AgentWorkspaceConfig,
    LinearConfig,
    LinearToolAccessConfig,
)
from cli_agent_orchestrator.constants import DEFAULT_RUNTIME_CAPABILITIES
from cli_agent_orchestrator.services.agent_manager import AgentManager
from cli_agent_orchestrator.services.tool_service import ToolService, tool_service_for_loaded_agent
from cli_agent_orchestrator.workspace_providers.tool_access import (
    ProviderConversationAccessRequirement,
    ProviderMediatedToolDefinition,
    ProviderToolAccess,
    ProviderToolAccessPolicy,
)
from cli_agent_orchestrator.workspace_setups import WorkspaceTeam, WorkspaceTeamRole


def _agent(
    agent_id: str = "agent",
    *,
    team: str | None = None,
    cao_tools: tuple[str, ...] | None = None,
    mcp_servers: Mapping[str, Mapping[str, Any]] | None = None,
    runtime_capabilities: tuple[str, ...] | None = None,
    codex_config: Mapping[str, Any] | None = None,
    linear: LinearConfig | None = None,
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
        linear=linear,
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
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(agents=(agent,)),
    )

    access = service.tools_for_agent(agent.id, built_in_tool_names=("send_message", "assign"))

    assert access.built_in_cao_tools == ("send_message",)
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


def test_omitted_runtime_capabilities_preserve_default_provider_native_capabilities():
    agent = _agent(mcp_servers={"custom": {"command": "custom-mcp"}})
    service = ToolService(agent_manager=_manager(agent))

    access = service.tools_for_agent(agent.id)

    assert access.runtime_capabilities == (
        *DEFAULT_RUNTIME_CAPABILITIES,
        "@cao-mcp-server",
        "@custom",
    )


def test_teamed_omitted_runtime_capabilities_preserve_agent_owned_defaults():
    agent = _agent(team="delivery", mcp_servers={"custom": {"command": "custom-mcp"}})
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(agents=(agent,)),
    )

    access = service.tools_for_agent(agent.id)

    assert access.runtime_capabilities == (
        *DEFAULT_RUNTIME_CAPABILITIES,
        "@cao-mcp-server",
    )
    assert "custom" not in access.materialized_mcp_servers
    assert access.inactive_local_grants["mcp_servers"] == {
        "custom": {"command": "custom-mcp"}
    }


def test_switching_agent_into_team_changes_active_source_to_team_role():
    standalone = _agent(
        agent_id="agent",
        cao_tools=("assign",),
        mcp_servers={"custom": {"command": "custom-mcp"}},
    )
    teamed = _agent(
        agent_id="agent",
        team="delivery",
        cao_tools=("assign",),
        mcp_servers={"custom": {"command": "custom-mcp"}},
    )
    standalone_service = ToolService(agent_manager=_manager(standalone))
    teamed_service = ToolService(
        agent_manager=_manager(teamed),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(agents=(teamed,)),
    )

    before = standalone_service.tools_for_agent(
        "agent",
        built_in_tool_names=("send_message", "handoff", "assign"),
    )
    after = teamed_service.tools_for_agent(
        "agent",
        built_in_tool_names=("send_message", "handoff", "assign"),
    )

    assert before.built_in_cao_tools == ("assign",)
    assert "custom" in before.materialized_mcp_servers
    assert before.inactive_local_grants == {}
    assert after.built_in_cao_tools == ("send_message", "handoff")
    assert "custom" not in after.materialized_mcp_servers
    assert after.inactive_local_grants == {
        "cao_tools": ["assign"],
        "mcp_servers": {"custom": {"command": "custom-mcp"}},
    }


def test_removing_agent_from_team_restores_standalone_local_source():
    teamed = _agent(
        agent_id="agent",
        team="delivery",
        cao_tools=("assign",),
        mcp_servers={"custom": {"command": "custom-mcp"}},
    )
    standalone = _agent(
        agent_id="agent",
        cao_tools=("assign",),
        mcp_servers={"custom": {"command": "custom-mcp"}},
    )
    teamed_service = ToolService(
        agent_manager=_manager(teamed),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(agents=(teamed,)),
    )
    standalone_service = ToolService(agent_manager=_manager(standalone))

    before = teamed_service.tools_for_agent(
        "agent",
        built_in_tool_names=("send_message", "handoff", "assign"),
    )
    after = standalone_service.tools_for_agent(
        "agent",
        built_in_tool_names=("send_message", "handoff", "assign"),
    )

    assert before.built_in_cao_tools == ("send_message", "handoff")
    assert "custom" not in before.materialized_mcp_servers
    assert after.built_in_cao_tools == ("assign",)
    assert "custom" in after.materialized_mcp_servers
    assert after.inactive_local_grants == {}


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

    assert access.provider_mediated_tools == {}
    assert (
        service.can_invoke(agent.id, "cao_linear.get_issue", provider_name="linear").allowed
        is False
    )


def test_teamed_missing_team_diagnostic_is_actionable():
    agent = _agent(agent_id="agent", team="missing-team")
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _InvalidTeamManager(),
    )

    access = service.tools_for_agent(agent.id)

    assert access.built_in_cao_tools == ()
    assert [diagnostic.code for diagnostic in access.diagnostics] == [
        "invalid_workspace_team"
    ]
    assert "invalid team" in access.diagnostics[0].message
    assert access.diagnostics[0].source == "workspace_team"


def test_teamed_missing_setup_diagnostic_is_actionable():
    agent = _agent(agent_id="agent", team="delivery")
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _MissingSetupManager(agent),
    )

    access = service.tools_for_agent(agent.id)

    assert access.built_in_cao_tools == ()
    assert [diagnostic.code for diagnostic in access.diagnostics] == [
        "invalid_workspace_team"
    ]
    assert "workspace team delivery has no setup" in access.diagnostics[0].message


def test_teamed_missing_role_and_non_member_assignment_diagnostics_are_actionable():
    agent = _agent(agent_id="agent", team="delivery")
    outsider = _agent(agent_id="outsider", team=None)
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        role_assignments={
            "agent": "missing_role",
            "outsider": "missing_role",
        },
    )
    service = ToolService(
        agent_manager=_manager(agent, outsider),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent, outsider),
        ),
    )

    access = service.tools_for_agent(agent.id, built_in_tool_names=("send_message", "handoff"))

    assert access.built_in_cao_tools == ("send_message", "handoff")
    assert [diagnostic.code for diagnostic in access.diagnostics] == [
        "invalid_team_role_assignment",
        "inactive_non_member_role_assignment",
    ]
    assert "missing role missing_role; using member" in access.diagnostics[0].message
    assert "to non-member outsider; assignment is inactive" in access.diagnostics[1].message


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

    assert access.provider_mediated_tools == {}
    assert access.allowed_tools == ()
    assert decision.allowed is False
    assert decision.reason == "provider_tool_denied"


def test_teamed_provider_access_requires_workspace_setup_authorized_location():
    agent = _agent(
        agent_id="agent",
        team="delivery",
        linear=LinearConfig(app_key="agent"),
    )
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("send_message", "handoff"),
                providers={
                    "linear": {
                        "reads": {
                            "tools": ["cao_linear.list_teams"],
                        },
                    },
                    "github": {
                        "outside_setup": {
                            "tools": ["ignored"],
                        },
                    },
                },
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent,),
        ),
    )

    access = service.tools_for_agent(agent.id)

    assert access.provider_mediated_tools == {"linear": ("cao_linear.list_teams",)}
    assert service.can_invoke(agent.id, "cao_linear.list_teams", provider_name="linear").allowed
    assert service.can_invoke(
        agent.id, "cao_linear.create_issue", provider_name="linear"
    ).allowed is False
    assert "role_provider_not_in_workspace_setup" in {
        diagnostic.code for diagnostic in access.diagnostics
    }


def test_teamed_role_provider_access_ignores_invalid_agent_local_linear_grants():
    agent = _agent(
        agent_id="agent",
        team="delivery",
        linear=LinearConfig(
            app_key="agent",
            tool_access=(
                LinearToolAccessConfig(
                    access_id="stale",
                    tools=("cao_linear.get_issue",),
                    issues=(),
                ),
            ),
        ),
    )
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                providers={
                    "linear": {
                        "reads": {
                            "tools": ["cao_linear.list_teams"],
                        },
                    },
                },
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent,),
        ),
    )

    access = service.tools_for_agent(agent.id)

    assert access.provider_mediated_tools == {"linear": ("cao_linear.list_teams",)}
    assert access.inactive_local_grants == {"linear.tool_access": ["stale"]}
    assert "provider_role_access_invalid" not in {
        diagnostic.code for diagnostic in access.diagnostics
    }


def test_loaded_agent_tool_service_keeps_full_registry_for_team_diagnostics(monkeypatch):
    loaded = _agent(agent_id="agent", team="delivery")
    peer = _agent(agent_id="peer", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        role_assignments={"peer": "member"},
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.tool_service.load_agent_registry",
        lambda: AgentRegistry({loaded.id: loaded, peer.id: peer}),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.tool_service.default_workspace_collaboration_manager",
        lambda *, agent_registry: _ProviderSetupManager(
            team=team,
            agents=tuple(agent_registry.all().values()),
        ),
    )

    access = tool_service_for_loaded_agent(
        loaded,
        fallback_agent_id=loaded.id,
        cli_provider=loaded.cli_provider,
    ).tools_for_agent(loaded.id, built_in_tool_names=("send_message", "handoff"))

    assert access.built_in_cao_tools == ("send_message", "handoff")
    assert "inactive_non_member_role_assignment" not in {
        diagnostic.code for diagnostic in access.diagnostics
    }


def test_default_member_role_does_not_grant_provider_conversation_requirements():
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
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(agents=(agent,)),
    )

    access = service.tools_for_agent(agent.id, built_in_tool_names=("read_inbox_message",))
    decision = service.provider_conversation_decision(
        agent.id,
        provider="linear",
        operation="read",
        source="test",
        provider_identity="agent",
    )

    assert access.built_in_cao_tools == ()
    assert access.provider_conversation_requirements == ()
    assert decision.allowed is False
    assert decision.reason == "provider_conversation_operation_not_registered"


def test_terminate_target_must_be_in_same_workspace_team():
    caller = _agent(agent_id="caller", team="delivery")
    teammate = _agent(agent_id="teammate", team="delivery")
    outsider = _agent(agent_id="outsider", team="research")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("terminate",),
            )
        },
    )
    terminals = [
        {"id": "caller-terminal", "agent_id": "caller"},
        {"id": "teammate-terminal", "agent_id": "teammate"},
        {"id": "outsider-terminal", "agent_id": "outsider"},
    ]
    service = ToolService(
        agent_manager=_manager(
            caller,
            teammate,
            outsider,
            terminals=terminals,
        ),
        terminal_metadata_resolver=lambda terminal_id: {
            str(terminal["id"]): terminal for terminal in terminals
        }.get(terminal_id),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(caller, teammate, outsider),
        ),
    )

    teammate_decision = service.can_invoke_for_terminal_target(
        "caller-terminal",
        "terminate",
        target_terminal_id="teammate-terminal",
        built_in_tool_names=("terminate",),
    )
    outsider_decision = service.can_invoke_for_terminal_target(
        "caller-terminal",
        "terminate",
        target_terminal_id="outsider-terminal",
        built_in_tool_names=("terminate",),
    )

    assert teammate_decision.allowed is True
    assert teammate_decision.reason == "target_terminal_same_workspace_team"
    assert outsider_decision.allowed is False
    assert outsider_decision.reason == "target_terminal_not_same_workspace_team"


def test_role_inbox_grant_enables_provider_conversation_requirement():
    agent = _agent(agent_id="agent", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("read_inbox_message",),
            )
        },
    )
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
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent,),
        ),
    )

    access = service.tools_for_agent(agent.id, built_in_tool_names=("read_inbox_message",))

    assert access.built_in_cao_tools == ("read_inbox_message",)
    assert access.provider_conversation_requirements == (
        ProviderConversationAccessRequirement(
            provider_name="linear",
            operation="read",
            required_identity="workspace_team_presence",
        ),
    )


def test_role_read_inbox_grant_does_not_authorize_provider_activity():
    agent = _agent(agent_id="agent", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("read_inbox_message",),
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_conversation_requirement_loader=lambda _registry: {
            "linear": (
                ProviderConversationAccessRequirement(
                    provider_name="linear",
                    operation="read",
                    required_identity="workspace_team_presence",
                ),
                ProviderConversationAccessRequirement(
                    provider_name="linear",
                    operation="activity",
                    required_identity="workspace_team_presence",
                ),
            )
        },
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent,),
        ),
    )

    access = service.tools_for_agent(agent.id, built_in_tool_names=("read_inbox_message",))
    decision = service.provider_conversation_decision(
        agent.id,
        provider="linear",
        operation="activity",
        source="test",
        provider_identity=None,
    )

    assert access.provider_conversation_requirements == (
        ProviderConversationAccessRequirement(
            provider_name="linear",
            operation="read",
            required_identity="workspace_team_presence",
        ),
    )
    assert decision.allowed is False
    assert decision.reason == "provider_conversation_operation_not_registered"


def test_role_provider_activity_permission_registers_provider_activity():
    agent = _agent(agent_id="agent", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("post_provider_activity",),
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_conversation_requirement_loader=lambda _registry: {
            "linear": (
                ProviderConversationAccessRequirement(
                    provider_name="linear",
                    operation="activity",
                    required_identity="workspace_team_presence",
                ),
            )
        },
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent,),
        ),
    )

    access = service.tools_for_agent(agent.id, built_in_tool_names=("read_inbox_message",))
    decision = service.provider_conversation_decision(
        agent.id,
        provider="linear",
        operation="activity",
        source="test",
        provider_identity=None,
    )

    assert access.built_in_cao_tools == ()
    assert access.provider_conversation_requirements == (
        ProviderConversationAccessRequirement(
            provider_name="linear",
            operation="activity",
            required_identity="workspace_team_presence",
        ),
    )
    assert decision.allowed is False
    assert decision.reason == "missing_provider_identity"


def test_role_provider_access_expands_for_each_member_on_role():
    first = _agent(agent_id="first", team="delivery", linear=LinearConfig(app_key="first"))
    second = _agent(agent_id="second", team="delivery", linear=LinearConfig(app_key="second"))
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("send_message", "handoff"),
                providers={
                    "linear": {
                        "reads": {
                            "tools": ["cao_linear.list_teams"],
                        },
                    },
                },
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(first, second),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(first, second),
        ),
    )

    first_access = service.tools_for_agent(first.id)
    second_access = service.tools_for_agent(second.id)

    assert first_access.provider_mediated_tools == {"linear": ("cao_linear.list_teams",)}
    assert second_access.provider_mediated_tools == {"linear": ("cao_linear.list_teams",)}
    assert service.can_invoke(first.id, "cao_linear.list_teams", provider_name="linear").allowed
    assert service.can_invoke(second.id, "cao_linear.list_teams", provider_name="linear").allowed


def test_role_provider_access_missing_presence_emits_diagnostic_and_no_tool():
    agent = _agent(agent_id="agent", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                providers={
                    "linear": {
                        "reads": {
                            "tools": ["cao_linear.list_teams"],
                        },
                    },
                },
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent,),
        ),
    )

    access = service.tools_for_agent(agent.id)

    assert access.provider_mediated_tools == {}
    assert "provider_role_access_invalid" in {diagnostic.code for diagnostic in access.diagnostics}


def test_role_provider_access_rejects_non_boolean_provider_fields():
    agent = _agent(agent_id="agent", team="delivery", linear=LinearConfig(app_key="agent"))
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                providers={
                    "linear": {
                        "creates": {
                            "tools": ["cao_linear.create_issue"],
                            "create_team_ids": ["team-1"],
                            "allow_top_level_create": "false",
                        },
                    },
                },
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent,),
        ),
    )

    access = service.tools_for_agent(agent.id)

    assert access.provider_mediated_tools == {}
    assert any(
        "allow_top_level_create must be a boolean" in diagnostic.message
        for diagnostic in access.diagnostics
    )


def test_provider_conversation_missing_identity_denies_through_tool_service():
    agent = _agent(agent_id="agent", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("read_inbox_message",),
            )
        },
    )
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
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent,),
        ),
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
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup="setup",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("read_inbox_message",),
            )
        },
    )
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
        collaboration_manager_factory=lambda _registry: _ProviderSetupManager(
            team=team,
            agents=(agent,),
        ),
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
    @property
    def agent_registry(self):
        return AgentRegistry({})

    def team_for_agent(self, agent):
        raise RuntimeError("invalid team")

    def setup_for_agent(self, agent):
        raise RuntimeError("invalid team")


class _MissingSetupManager:
    def __init__(self, agent: Agent) -> None:
        self._agent_registry = AgentRegistry({agent.id: agent})
        self._team = WorkspaceTeam(
            id="delivery",
            display_name="Delivery",
            workspace_setup="setup",
        )

    @property
    def agent_registry(self):
        return self._agent_registry

    def team_for_agent(self, agent):
        return self._team

    def setup_for_agent(self, agent):
        return None


class _ProviderSetupManager:
    def __init__(
        self,
        *,
        team: WorkspaceTeam | None = None,
        agents: tuple[Agent, ...] = (),
    ) -> None:
        self._team = team or WorkspaceTeam(
            id="delivery",
            display_name="Delivery",
            workspace_setup="setup",
        )
        self._agent_registry = AgentRegistry({agent.id: agent for agent in agents})

    @property
    def agent_registry(self):
        return self._agent_registry

    def team_for_agent(self, agent):
        if agent.workspace.team != self._team.id:
            raise RuntimeError("invalid team")
        return self._team

    def setup_for_agent(self, agent):
        return _ProviderSetup()


class _ProviderSetup:
    id = "setup"
    providers = ("linear",)

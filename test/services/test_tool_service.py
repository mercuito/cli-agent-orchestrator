from __future__ import annotations

from typing import Any, Mapping

import pytest

from cli_agent_orchestrator.agent import (
    Agent,
    AgentRegistry,
    AgentWorkspaceConfig,
)
from cli_agent_orchestrator.constants import DEFAULT_RUNTIME_CAPABILITIES
from cli_agent_orchestrator.services.agent_manager import AgentManager
from cli_agent_orchestrator.services.tool_service import ToolService, tool_service_for_loaded_agent
from cli_agent_orchestrator.workspaces import WorkspaceTeam, WorkspaceTeamRole
from cli_agent_orchestrator.workspace_tool_providers.tool_access import (
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
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(agents=(agent,)),
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
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(agents=(agent,)),
    )

    access = service.tools_for_agent(agent.id)

    assert access.runtime_capabilities == (
        *DEFAULT_RUNTIME_CAPABILITIES,
        "@cao-mcp-server",
    )
    assert "custom" not in access.materialized_mcp_servers
    assert access.inactive_local_grants["mcp_servers"] == {"custom": {"command": "custom-mcp"}}


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
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(agents=(teamed,)),
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
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(agents=(teamed,)),
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
        terminal_metadata_resolver=lambda terminal_id: (
            {"agent_id": agent.id} if terminal_id == "terminal-1" else None
        ),
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
        terminal_metadata_resolver=lambda terminal_id: (
            {"agent_id": agent.id} if terminal_id == "terminal-1" else None
        ),
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
        provider_name="example",
        tools={
            "example.get_issue": ProviderMediatedToolDefinition(
                name="example.get_issue",
                description="Read issue",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            )
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="example",
                tool_name="example.get_issue",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="example.tool_access.reads",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_policy_loader=lambda _registry: {"example": policy},
    )

    access = service.tools_for_agent(agent.id)
    decision = service.can_invoke(agent.id, "example.get_issue", provider_name="example")

    assert access.provider_mediated_tools == {"example": ("example.get_issue",)}
    assert decision.allowed is True


def test_agent_tool_view_reuses_provider_policy_metadata_for_same_inputs():
    agent = _agent()
    calls = 0
    policy = ProviderToolAccessPolicy(
        provider_name="example",
        tools={
            "example.get_issue": ProviderMediatedToolDefinition(
                name="example.get_issue",
                description="Read issue",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            )
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="example",
                tool_name="example.get_issue",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="example.tool_access.reads",
            ),
        ),
    )

    def provider_policy_loader(_registry):
        nonlocal calls
        calls += 1
        return {"example": policy}

    service = ToolService(
        agent_manager=_manager(agent),
        provider_policy_loader=provider_policy_loader,
    )

    first = service.agent_tool_view(
        agent.id,
        built_in_tools=(),
        built_in_tool_names=("send_message",),
    )
    second = service.agent_tool_view(
        agent.id,
        built_in_tools=(),
        built_in_tool_names=("send_message",),
    )

    assert first.effective_access.provider_mediated_tools == {"example": ("example.get_issue",)}
    assert second.effective_access.provider_mediated_tools == {"example": ("example.get_issue",)}
    assert calls == 1


def test_agent_tool_view_recomputes_provider_policy_when_provider_config_changes(
    monkeypatch,
):
    agent = _agent()
    calls = 0
    version = "one"

    def provider_policy_loader(_registry):
        nonlocal calls
        calls += 1
        return {
            "example": ProviderToolAccessPolicy(
                provider_name="example",
                tools={
                    "example.get_issue": ProviderMediatedToolDefinition(
                        name="example.get_issue",
                        description=f"Read issue {version}",
                        input_schema={},
                        handler=lambda _context, _arguments: {"ok": True},
                    )
                },
                hooks={},
                access=(
                    ProviderToolAccess(
                        provider_name="example",
                        tool_name="example.get_issue",
                        agent_id=agent.id,
                        pre_hooks=(),
                        post_hooks=(),
                        source_location=f"example.tool_access.{version}",
                    ),
                ),
            )
        }

    monkeypatch.setattr(
        "cli_agent_orchestrator.services.tool_service._workspace_tool_provider_config_cache_token",
        lambda: ("providers", version, 1),
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_policy_loader=provider_policy_loader,
    )

    first = service.agent_tool_view(
        agent.id,
        built_in_tools=(),
        built_in_tool_names=("send_message",),
    )
    again = service.agent_tool_view(
        agent.id,
        built_in_tools=(),
        built_in_tool_names=("send_message",),
    )
    version = "two"
    changed = service.agent_tool_view(
        agent.id,
        built_in_tools=(),
        built_in_tool_names=("send_message",),
    )

    assert first.mcp_surface_descriptor["tools"][0]["description"] == "Read issue one"
    assert again.mcp_surface_descriptor["tools"][0]["description"] == "Read issue one"
    assert changed.mcp_surface_descriptor["tools"][0]["description"] == "Read issue two"
    assert calls == 2


def test_agent_tool_view_recomputes_when_agent_tool_inputs_change():
    class MutableAgentManager:
        def __init__(self, agent):
            self.agent = agent

        def list_agents(self):
            return [self.agent]

        def resolve_agent(self, agent_id):
            assert agent_id == self.agent.id
            return self.agent

    manager = MutableAgentManager(_agent(agent_id="agent", cao_tools=("send_message",)))
    service = ToolService(agent_manager=manager)

    before = service.agent_tool_view(
        "agent",
        built_in_tools=(),
        built_in_tool_names=("send_message", "assign"),
    )
    manager.agent = _agent(agent_id="agent", cao_tools=("assign",))
    after = service.agent_tool_view(
        "agent",
        built_in_tools=(),
        built_in_tool_names=("send_message", "assign"),
    )

    assert before.effective_access.built_in_cao_tools == ("send_message",)
    assert after.effective_access.built_in_cao_tools == ("assign",)


def test_agent_tool_view_recomputes_when_team_role_grants_change():
    agent = _agent(agent_id="agent", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace="workspace",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("send_message",),
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(
            team=team,
            agents=(agent,),
        ),
    )

    before = service.agent_tool_view(
        agent.id,
        built_in_tools=(),
        built_in_tool_names=("send_message", "assign"),
    )
    team.roles["member"] = WorkspaceTeamRole(
        display_name="Member",
        cao_tools=("assign",),
    )
    after = service.agent_tool_view(
        agent.id,
        built_in_tools=(),
        built_in_tool_names=("send_message", "assign"),
    )

    assert before.effective_access.built_in_cao_tools == ("send_message",)
    assert after.effective_access.built_in_cao_tools == ("assign",)


def test_agent_tool_view_reuses_team_role_provider_policy_during_surface_build(
    monkeypatch,
):
    agent = _agent(agent_id="agent", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace="workspace",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("read_inbox_message",),
                providers={
                    "example": {
                        "reads": {
                            "tools": ["example.get_issue"],
                        },
                    },
                },
            )
        },
    )
    calls = 0

    class FakeRoleProvider:
        name = "example"

        def initialize(self):
            return None

        def provider_role_tool_access(self, grants):
            nonlocal calls
            calls += 1
            return ProviderToolAccessPolicy(
                provider_name="example",
                tools={
                    "example.get_issue": ProviderMediatedToolDefinition(
                        name="example.get_issue",
                        description="Read issue",
                        input_schema={},
                        handler=lambda _context, _arguments: {"ok": True},
                    )
                },
                hooks={},
                access=(
                    ProviderToolAccess(
                        provider_name="example",
                        tool_name="example.get_issue",
                        agent_id=agent.id,
                        pre_hooks=(),
                        post_hooks=(),
                        source_location=grants[0].source_location,
                    ),
                ),
            )

    class FakeProviderRegistry:
        def create(self, provider_name, _agent_registry):
            assert provider_name == "example"
            return FakeRoleProvider()

    monkeypatch.setattr(
        "cli_agent_orchestrator.services.tool_service.default_workspace_tool_provider_registry",
        lambda: FakeProviderRegistry(),
    )
    service = ToolService(
        agent_manager=_manager(agent),
                collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(
            team=team,
            agents=(agent,),
        ),
    )

    view = service.agent_tool_view(
        agent.id,
        built_in_tools=(),
        built_in_tool_names=("read_inbox_message",),
    )

    assert view.effective_access.provider_mediated_tools == {"example": ("example.get_issue",)}
    assert view.mcp_surface_descriptor["tools"][0]["name"] == "example.get_issue"
    assert calls == 1


def test_provider_mediated_registration_skips_builtin_name_conflicts():
    agent = _agent()
    policy = ProviderToolAccessPolicy(
        provider_name="example",
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
                provider_name="example",
                tool_name="send_message",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="example.tool_access.conflict",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent, terminals=[{"id": "terminal-1", "agent_id": agent.id}]),
        terminal_metadata_resolver=lambda terminal_id: (
            {"agent_id": agent.id} if terminal_id == "terminal-1" else None
        ),
        provider_policy_loader=lambda _registry: {"example": policy},
    )

    access = service.tools_for_agent(agent.id, built_in_tool_names=("send_message",))
    registration = service.registered_tools_for_terminal(
        "terminal-1",
        built_in_tool_names=("send_message",),
    )
    decision = service.can_invoke(
        agent.id,
        "send_message",
        provider_name="example",
        built_in_tool_names=("send_message",),
    )

    assert access.provider_mediated_tools == {"example": ()}
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
        terminal_metadata_resolver=lambda terminal_id: (
            {"agent_id": agent.id} if terminal_id == "terminal-1" else None
        ),
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
        provider_name="example",
        tools={
            "example.get_issue": ProviderMediatedToolDefinition(
                name="example.get_issue",
                description="Read issue",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            )
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="example",
                tool_name="example.get_issue",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="example.tool_access.reads",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_policy_loader=lambda _registry: {"example": policy},
        collaboration_manager_factory=lambda _registry: _InvalidTeamManager(),
    )

    access = service.tools_for_agent(agent.id)

    assert access.provider_mediated_tools == {}
    assert (
        service.can_invoke(agent.id, "example.get_issue", provider_name="example").allowed
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
    assert [diagnostic.code for diagnostic in access.diagnostics] == ["invalid_workspace_team"]
    assert "invalid team" in access.diagnostics[0].message
    assert access.diagnostics[0].source == "workspace_team"


def test_teamed_missing_workspace_diagnostic_is_actionable():
    agent = _agent(agent_id="agent", team="delivery")
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _MissingWorkspaceManager(agent),
    )

    access = service.tools_for_agent(agent.id)

    assert access.built_in_cao_tools == ()
    assert [diagnostic.code for diagnostic in access.diagnostics] == ["invalid_workspace_team"]
    assert "workspace team delivery has no workspace" in access.diagnostics[0].message


def test_teamed_missing_role_and_non_member_assignment_diagnostics_are_actionable():
    agent = _agent(agent_id="agent", team="delivery")
    outsider = _agent(agent_id="outsider", team=None)
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace="workspace",
        role_assignments={
            "agent": "missing_role",
            "outsider": "missing_role",
        },
    )
    service = ToolService(
        agent_manager=_manager(agent, outsider),
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(
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
        provider_name="example",
        tools={
            "example.get_issue": ProviderMediatedToolDefinition(
                name="example.get_issue",
                description="Read issue",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            )
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="example",
                tool_name="example.get_issue",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="agents.agent.example.tool_access.reads",
            ),
        ),
    )
    service = ToolService(
        agent_manager=_manager(agent),
        provider_policy_loader=lambda _registry: {"example": policy},
    )

    access = service.tools_for_agent(agent.id)
    decision = service.can_invoke(agent.id, "example.get_issue", provider_name="example")

    assert access.provider_mediated_tools == {}
    assert access.allowed_tools == ()
    assert decision.allowed is False
    assert decision.reason == "provider_tool_denied"


def test_teamed_provider_access_requires_workspace_authorized_location():
    agent = _agent(
        agent_id="agent",
        team="delivery",
    )
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace="workspace",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("send_message", "handoff"),
                providers={
                    "example": {
                        "reads": {
                            "tools": ["example.list_teams"],
                        },
                    },
                    "github": {
                        "outside_workspace": {
                            "tools": ["ignored"],
                        },
                    },
                },
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(
            team=team,
            agents=(agent,),
        ),
    )

    access = service.tools_for_agent(agent.id)

    assert access.provider_mediated_tools == {}
    assert not service.can_invoke(agent.id, "example.list_teams", provider_name="example").allowed
    assert (
        service.can_invoke(agent.id, "example.create_issue", provider_name="example").allowed
        is False
    )
    assert "role_provider_not_in_workspace" in {
        diagnostic.code for diagnostic in access.diagnostics
    }
    assert "provider_role_access_invalid" in {
        diagnostic.code for diagnostic in access.diagnostics
    }


def test_terminate_target_must_be_in_same_workspace_team():
    caller = _agent(agent_id="caller", team="delivery")
    teammate = _agent(agent_id="teammate", team="delivery")
    outsider = _agent(agent_id="outsider", team="research")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace="workspace",
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
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(
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


def test_role_provider_access_expands_for_each_member_on_role():
    first = _agent(agent_id="first", team="delivery")
    second = _agent(agent_id="second", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace="workspace",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                cao_tools=("send_message", "handoff"),
                providers={
                    "example": {
                        "reads": {
                            "tools": ["example.list_teams"],
                        },
                    },
                },
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(first, second),
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(
            team=team,
            agents=(first, second),
        ),
    )

    first_access = service.tools_for_agent(first.id)
    second_access = service.tools_for_agent(second.id)

    assert first_access.provider_mediated_tools == {}
    assert second_access.provider_mediated_tools == {}
    assert not service.can_invoke(first.id, "example.list_teams", provider_name="example").allowed
    assert not service.can_invoke(second.id, "example.list_teams", provider_name="example").allowed


def test_role_provider_access_missing_presence_emits_diagnostic_and_no_tool():
    agent = _agent(agent_id="agent", team="delivery")
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace="workspace",
        roles={
            "member": WorkspaceTeamRole(
                display_name="Member",
                providers={
                    "example": {
                        "reads": {
                            "tools": ["example.list_teams"],
                        },
                    },
                },
            )
        },
    )
    service = ToolService(
        agent_manager=_manager(agent),
        collaboration_manager_factory=lambda _registry: _ProviderWorkspaceManager(
            team=team,
            agents=(agent,),
        ),
    )

    access = service.tools_for_agent(agent.id)

    assert access.provider_mediated_tools == {}
    assert "provider_role_access_invalid" in {diagnostic.code for diagnostic in access.diagnostics}


class _InvalidTeamManager:
    @property
    def agent_registry(self):
        return AgentRegistry({})

    def team_for_agent(self, agent):
        raise RuntimeError("invalid team")

    def workspace_for_agent(self, agent):
        raise RuntimeError("invalid team")


class _MissingWorkspaceManager:
    def __init__(self, agent: Agent) -> None:
        self._agent_registry = AgentRegistry({agent.id: agent})
        self._team = WorkspaceTeam(
            id="delivery",
            display_name="Delivery",
            workspace="workspace",
        )

    @property
    def agent_registry(self):
        return self._agent_registry

    def team_for_agent(self, agent):
        return self._team

    def workspace_for_agent(self, agent):
        return None


class _ProviderWorkspaceManager:
    def __init__(
        self,
        *,
        team: WorkspaceTeam | None = None,
        agents: tuple[Agent, ...] = (),
    ) -> None:
        self._team = team or WorkspaceTeam(
            id="delivery",
            display_name="Delivery",
            workspace="workspace",
        )
        self._agent_registry = AgentRegistry({agent.id: agent for agent in agents})

    @property
    def agent_registry(self):
        return self._agent_registry

    def team_for_agent(self, agent):
        if agent.workspace.team != self._team.id:
            raise RuntimeError("invalid team")
        return self._team

    def workspace_for_agent(self, agent):
        return _ProviderWorkspace()


class _ProviderWorkspace:
    id = "workspace"
    providers = ("example",)

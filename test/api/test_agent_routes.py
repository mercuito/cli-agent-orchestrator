from __future__ import annotations

from dataclasses import dataclass as std_dataclass
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import ClassVar, Literal

import pytest
from pydantic.dataclasses import dataclass

from cli_agent_orchestrator.agent import (
    Agent,
    AgentConfigError,
    AgentRegistry,
    AgentWorkspaceConfig,
    LinearConfig,
    LinearToolAccessConfig,
    load_agent,
    load_agent_registry,
    write_agent,
)
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import TerminalAgentAlreadyRunningError
from cli_agent_orchestrator.events import (
    AgentParticipant,
    CaoCausationId,
    CaoCorrelationId,
    CaoEventDispatcher,
    CaoEventId,
    CaoEventOccurredAt,
    CaoEventSourceId,
    CaoEventSourceRef,
    CaoEventSourceType,
)
from cli_agent_orchestrator.linear.workspace_events import LinearAgentMentionedEvent
from cli_agent_orchestrator.runtime.events import (
    AgentRuntimeNotificationDeliveryEvent,
    RuntimeWorkspaceEvent,
    notification_delivery_event,
    workspace_runtime_event,
)
from cli_agent_orchestrator.services.agent_manager import AgentManager, AgentStatus
from cli_agent_orchestrator.services.tool_service import ToolService
from cli_agent_orchestrator.utils.dashboard_links import create_agent_dashboard_token
from cli_agent_orchestrator.workspaces import (
    Workspace,
    WorkspaceDiagnostic,
    WorkspaceRegistry,
    WorkspaceTeam,
    WorkspaceTeamRole,
    WorkspaceTeamService,
    WorkspaceTeamStore,
)
from cli_agent_orchestrator.workspace_tool_providers.tool_access import (
    ProviderMediatedToolDefinition,
    ProviderToolAccess,
    ProviderToolAccessPolicy,
)

OCCURRED_AT = CaoEventOccurredAt(datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc))


@dataclass(frozen=True, kw_only=True)
class _ExperimentalAuditEvent:
    event_name: ClassVar[str] = "experimental_audit_event"
    kind: Literal["experimental.audit_event"] = "experimental.audit_event"

    event_id: CaoEventId
    source: CaoEventSourceRef
    occurred_at: CaoEventOccurredAt
    correlation_id: CaoCorrelationId | None
    causation_id: CaoCausationId | None
    audit_kind: str
    confidence: float
    agent_participants: tuple[AgentParticipant, ...]


@std_dataclass
class _FakeAgentManager:
    statuses: tuple[AgentStatus, ...]
    status_calls: tuple[str, ...] = ()

    def list_statuses(self, *, active=None):
        if active is None:
            return self.statuses
        return tuple(status for status in self.statuses if status.active is active)

    def status_for_agent(self, agent_id: str):
        self.status_calls = (*self.status_calls, agent_id)
        for status in self.statuses:
            if status.agent_id == agent_id:
                return status
        raise AgentConfigError(f"Unknown CAO agent: {agent_id}")


def _tool_view(agent_id: str, *, built_ins: tuple[str, ...] = ("send_message",)):
    return SimpleNamespace(
        mcp_surface_descriptor={
            "schema_version": "cao-agent-mcp-surface.v1",
            "tools": [
                {
                    "source": {"kind": "cao_builtin", "name": "cao"},
                    "name": name,
                    "description": f"{name} tool.",
                }
                for name in built_ins
            ],
        },
        effective_access=SimpleNamespace(
            agent_id=agent_id,
            team_id=None,
            role_id=None,
            registered_tools=built_ins,
            allowed_tools=built_ins,
            blocked_tools=(),
            built_in_cao_tools=built_ins,
            provider_mediated_tools={},
            materialized_mcp_servers={},
            runtime_capabilities=(),
            source_markers={name: "test" for name in built_ins},
            inactive_local_grants={},
            provider_conversation_requirements=(),
            diagnostics=(),
        ),
    )


def _install_route_tool_service(monkeypatch, manager, factory=None):
    class FakeToolService:
        def __init__(self, *, agent_manager):
            assert agent_manager is manager

        def agent_tool_view(
            self,
            agent_id,
            *,
            built_in_tools,
            built_in_tool_names,
            baton_enabled=True,
        ):
            if factory is not None:
                return factory(agent_id, built_in_tools, built_in_tool_names, baton_enabled)
            return _tool_view(agent_id)

    monkeypatch.setattr("cli_agent_orchestrator.api.main.ToolService", FakeToolService)


def _agent(agent_id: str = "implementation_partner") -> Agent:
    return Agent(
        id=agent_id,
        display_name="Implementation Partner",
        cli_provider="claude_code",
        workdir="/repo",
        session_name=agent_id.replace("_", "-"),
        prompt="# Agent\n",
        description="Developer Agent in a multi-agent system",
        model="claude-opus-4-7",
        reasoning_effort="medium",
        mcp_servers={"cao-mcp-server": {"command": "cao-mcp-server"}},
        tools=("bash",),
        tool_aliases={"shell": "bash"},
        tools_settings={"bash": {"timeout": 120}},
        cao_tools=("send_message",),
        skills=("coding-discipline",),
        tags=("implementation",),
        resources=("file:///repo/README.md",),
        hooks={"pre": {"command": "true"}},
        use_legacy_mcp_json=False,
        runtime_capabilities=("@builtin",),
        codex_config={"model": "gpt-5.2"},
        linear=LinearConfig(
            app_key=agent_id,
            client_id="client-1",
            client_secret="secret-1",
            oauth_redirect_uri="https://example.test/linear/oauth/callback",
            access_token="access-1",
            tool_access=(
                LinearToolAccessConfig(
                    access_id="workflow",
                    tools=("cao_linear.get_issue",),
                    issues=("CAO-1",),
                    update_fields=("title",),
                ),
            ),
        ),
    )


def _status(
    agent_id: str = "implementation_partner",
    *,
    active: bool = False,
) -> AgentStatus:
    agent = _agent(agent_id)
    return AgentStatus(
        agent_id=agent_id,
        display_name=agent.display_name,
        cli_provider=agent.cli_provider,
        workdir=agent.workdir,
        session_name=agent.session_name,
        agent=agent,
        active=active,
        active_terminal_id="abcd1234" if active else None,
        active_workspace_context_id="wctx_abc" if active else None,
        last_active_at=datetime(2026, 5, 13, 12, 0, 0) if active else None,
    )


def test_list_agents_returns_stable_status_shape(client, monkeypatch):
    manager = _FakeAgentManager((_status(active=True), _status("reviewer")))

    def factory(agent_id, _built_in_tools, _built_in_tool_names, _baton_enabled):
        return SimpleNamespace(
            mcp_surface_descriptor={
                "schema_version": "cao-agent-mcp-surface.v1",
                "tools": [
                    {
                        "source": {"kind": "cao_builtin", "name": "cao"},
                        "name": "send_message",
                        "description": "Send a message to another CAO agent.",
                    },
                    {
                        "source": {"kind": "provider", "name": "linear"},
                        "name": "cao_linear.get_issue",
                        "description": "Read a Linear issue.",
                    },
                ],
            },
            effective_access=SimpleNamespace(
                agent_id=agent_id,
                team_id=None,
                role_id=None,
                registered_tools=("send_message", "cao_linear.get_issue"),
                allowed_tools=("send_message", "cao_linear.get_issue"),
                blocked_tools=(),
                built_in_cao_tools=("send_message",),
                provider_mediated_tools={"linear": ("cao_linear.get_issue",)},
                materialized_mcp_servers={},
                runtime_capabilities=(),
                source_markers={"send_message": "test"},
                inactive_local_grants={},
                provider_conversation_requirements=(),
                diagnostics=(),
            ),
        )

    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: manager,
    )
    _install_route_tool_service(monkeypatch, manager, factory)

    response = client.get("/agents")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["agent_id"] == "implementation_partner"
    assert body[0]["config"]["workdir"] == "/repo"
    assert body[0]["config"]["session_name"] == "implementation-partner"
    assert "workspace" in body[0]["config"]
    assert body[0]["config"]["mcp_servers"] == {"cao-mcp-server": {"command": "cao-mcp-server"}}
    assert body[0]["config"]["reasoning_effort"] == "medium"
    assert body[0]["config"]["tool_aliases"] == {"shell": "bash"}
    assert body[0]["config"]["tools_settings"] == {"bash": {"timeout": 120}}
    assert body[0]["config"]["cao_tools"] == ["send_message"]
    assert body[0]["config"]["runtime_capabilities"] == ["@builtin"]
    assert body[0]["config"]["codex_config"] == {"model": "gpt-5.2"}
    assert body[0]["config"]["linear"]["app_key"] == "implementation_partner"
    assert body[0]["config"]["linear"]["client_secret_configured"] is True
    assert body[0]["config"]["linear"]["access_token_configured"] is True
    assert body[0]["config"]["linear"]["tool_access"][0]["tools"] == ["cao_linear.get_issue"]
    assert body[0]["mcp_tool_surface"] == {
        "schema_version": "cao-agent-mcp-surface.v1",
        "tools": [
            {
                "source": {"kind": "cao_builtin", "name": "cao"},
                "name": "send_message",
                "description": "Send a message to another CAO agent.",
            },
            {
                "source": {"kind": "provider", "name": "linear"},
                "name": "cao_linear.get_issue",
                "description": "Read a Linear issue.",
            },
        ],
    }
    assert body[0]["agent_dashboard_token"]
    assert body[0]["active_terminal_id"] == "abcd1234"
    assert body[1]["agent_id"] == "reviewer"


def test_list_agents_effective_access_reserves_hidden_builtin_names(client, monkeypatch):
    agent = replace(_agent(), cao_tools=("send_message",))
    policy = ProviderToolAccessPolicy(
        provider_name="linear",
        tools={
            "assign": ProviderMediatedToolDefinition(
                name="assign",
                description="Conflicting provider tool",
                input_schema={},
                handler=lambda _context, _arguments: {"ok": True},
            )
        },
        hooks={},
        access=(
            ProviderToolAccess(
                provider_name="linear",
                tool_name="assign",
                agent_id=agent.id,
                pre_hooks=(),
                post_hooks=(),
                source_location="agents.implementation_partner.linear.tool_access.conflict",
            ),
        ),
    )

    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main._available_builtin_cao_tool_names_for_access",
        lambda: ("send_message", "assign"),
    )

    class FakeToolService:
        def __init__(self, *, agent_manager):
            assert agent_manager is manager
            self._service = ToolService(
                agent_manager=AgentManager(configured_agents=AgentRegistry({agent.id: agent})),
                provider_policy_loader=lambda _registry: {"linear": policy},
            )

        def agent_tool_view(
            self,
            agent_id,
            *,
            built_in_tools,
            built_in_tool_names,
            baton_enabled=True,
        ):
            access = self._service.tools_for_agent(
                agent_id,
                built_in_tool_names=built_in_tool_names,
            )
            return SimpleNamespace(
                mcp_surface_descriptor={
                    "schema_version": "cao-agent-mcp-surface.v1",
                    "tools": [
                        {
                            "source": {"kind": "cao_builtin", "name": "cao"},
                            "name": "send_message",
                            "description": "Send a message to another CAO agent.",
                        }
                    ],
                },
                effective_access=access,
            )

    manager = _FakeAgentManager((replace(_status(active=False), agent=agent),))
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: manager,
    )
    monkeypatch.setattr("cli_agent_orchestrator.api.main.ToolService", FakeToolService)

    response = client.get("/agents")

    assert response.status_code == 200
    effective_access = response.json()[0]["effective_tool_access"]
    assert effective_access["built_in_cao_tools"] == ["send_message"]
    assert effective_access["provider_mediated_tools"] == {"linear": []}
    assert effective_access["allowed_tools"] == ["send_message"]


def test_list_agents_reads_tool_metadata_from_tool_service_owner(client, monkeypatch):
    manager = _FakeAgentManager((_status(active=True),))
    calls: list[str] = []

    class FakeToolService:
        def __init__(self, *, agent_manager):
            assert agent_manager is manager

        def agent_tool_view(
            self,
            agent_id,
            *,
            built_in_tools,
            built_in_tool_names,
            baton_enabled=True,
        ):
            calls.append(agent_id)
            assert built_in_tool_names == ("send_message", "assign")
            assert baton_enabled is True
            return SimpleNamespace(
                mcp_surface_descriptor={
                    "schema_version": "cao-agent-mcp-surface.v1",
                    "tools": [
                        {
                            "source": {"kind": "cao_builtin", "name": "cao"},
                            "name": "send_message",
                            "description": "Send a message.",
                        }
                    ],
                },
                effective_access=SimpleNamespace(
                    agent_id=agent_id,
                    team_id=None,
                    role_id=None,
                    registered_tools=("send_message",),
                    allowed_tools=("send_message",),
                    blocked_tools=(),
                    built_in_cao_tools=("send_message",),
                    provider_mediated_tools={},
                    materialized_mcp_servers={},
                    runtime_capabilities=(),
                    source_markers={"send_message": "test"},
                    inactive_local_grants={},
                    provider_conversation_requirements=(),
                    diagnostics=(),
                ),
            )

    monkeypatch.setattr("cli_agent_orchestrator.api.main.default_agent_manager", lambda: manager)
    monkeypatch.setattr("cli_agent_orchestrator.api.main.ToolService", FakeToolService)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main._build_mcp_surface_descriptor_for_agent",
        lambda _agent: pytest.fail("API route should ask ToolService for MCP surface"),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.tool_service_for_loaded_agent",
        lambda *_args, **_kwargs: pytest.fail("API route should not build per-agent services"),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main._available_builtin_cao_tool_names_for_access",
        lambda: ("send_message", "assign"),
    )

    response = client.get("/agents")

    assert response.status_code == 200
    assert calls == ["implementation_partner"]
    assert response.json()[0]["mcp_tool_surface"]["tools"][0]["name"] == "send_message"
    assert response.json()[0]["effective_tool_access"]["allowed_tools"] == ["send_message"]


def test_get_agent_reads_tool_metadata_from_tool_service_owner(client, monkeypatch):
    manager = _FakeAgentManager((_status(active=True),))
    calls: list[str] = []

    def factory(agent_id, _built_in_tools, built_in_tool_names, baton_enabled):
        calls.append(agent_id)
        assert built_in_tool_names == ("send_message", "assign")
        assert baton_enabled is True
        return _tool_view(agent_id, built_ins=("assign",))

    monkeypatch.setattr("cli_agent_orchestrator.api.main.default_agent_manager", lambda: manager)
    _install_route_tool_service(monkeypatch, manager, factory)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main._build_mcp_surface_descriptor_for_agent",
        lambda _agent: pytest.fail("API route should ask ToolService for MCP surface"),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.tool_service_for_loaded_agent",
        lambda *_args, **_kwargs: pytest.fail("API route should not build per-agent services"),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main._available_builtin_cao_tool_names_for_access",
        lambda: ("send_message", "assign"),
    )

    response = client.get("/agents/implementation_partner")

    assert response.status_code == 200
    assert calls == ["implementation_partner"]
    assert response.json()["agent_id"] == "implementation_partner"
    assert response.json()["mcp_tool_surface"]["tools"][0]["name"] == "assign"
    assert response.json()["effective_tool_access"]["allowed_tools"] == ["assign"]


def test_workspace_diagnostics_endpoint_surfaces_manager_diagnostics(client, monkeypatch):
    manager = SimpleNamespace(
        diagnostics=lambda: (
            WorkspaceDiagnostic(
                code="unknown_team",
                message="Unknown workspace team: future",
                team_id="future",
                agent_id="implementation_partner",
            ),
        )
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_collaboration_manager",
        lambda: manager,
    )

    response = client.get("/workspaces/diagnostics")

    assert response.status_code == 200
    assert response.json() == [
        {
            "code": "unknown_team",
            "message": "Unknown workspace team: future",
            "team_id": "future",
            "workspace_id": None,
            "agent_id": "implementation_partner",
            "provider_name": None,
        }
    ]


def test_workspace_team_endpoints_use_team_service_and_render_members(client, monkeypatch):
    saved: list[tuple[str, str, str]] = []
    team = WorkspaceTeam(
        id="cao_delivery",
        display_name="CAO Delivery",
        workspace="linear_delivery",
    )

    class _TeamService:
        def list_teams(self):
            return (team,)

        def update_team_metadata(
            self,
            *,
            team_id: str,
            display_name: str,
            workspace: str,
        ):
            saved.append((team_id, display_name, workspace))
            return WorkspaceTeam(
                id=team_id,
                display_name=display_name,
                workspace=workspace,
            )

    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_team_service",
        lambda: _TeamService(),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: SimpleNamespace(
            list_agents=lambda: (
                replace(
                    _agent("implementation_partner"),
                    workspace=AgentWorkspaceConfig(team="cao_delivery"),
                ),
            )
        ),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_collaboration_manager",
        lambda: SimpleNamespace(diagnostics=lambda: ()),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_registry",
        lambda: SimpleNamespace(
            all=lambda: (
                Workspace(
                    id="linear_delivery",
                    display_name="Linear Delivery",
                    providers=("linear",),
                    resolver=lambda event: None,
                ),
            )
        ),
    )

    list_response = client.get("/workspace-teams")
    workspaces_response = client.get("/workspaces")
    save_response = client.put(
        "/workspace-teams/research",
        json={
            "id": "research",
            "display_name": "Research",
            "workspace": "linear_delivery",
        },
    )

    assert list_response.status_code == 200
    assert list_response.json()[0]["members"] == ["implementation_partner"]
    assert workspaces_response.status_code == 200
    assert workspaces_response.json()[0]["id"] == "linear_delivery"
    assert save_response.status_code == 200
    assert saved == [("research", "Research", "linear_delivery")]


@pytest.mark.parametrize(
    "path",
    ("/workspace-setups", "/workspace-setups/diagnostics"),
)
def test_legacy_workspace_setup_routes_are_not_registered(client, path):
    response = client.get(path)

    assert response.status_code == 404


@pytest.mark.parametrize(
    "method,path",
    (("post", "/workspace-teams"), ("put", "/workspace-teams/research")),
)
def test_workspace_team_write_rejects_legacy_workspace_setup_field(client, method, path):
    response = getattr(client, method)(
        path,
        json={
            "id": "research",
            "display_name": "Research",
            "workspace_setup": "linear_delivery",
        },
    )

    assert response.status_code == 400


def test_workspace_team_role_api_round_trips_single_role_policy_through_store(
    client, monkeypatch, tmp_path
):
    workspace_registry = WorkspaceRegistry(
        (
            Workspace(
                id="linear_delivery",
                display_name="Linear Delivery",
                providers=("linear",),
                resolver=lambda event: None,
            ),
        )
    )
    team_store = WorkspaceTeamStore(tmp_path / "workspace-teams.json", bootstrap_teams=())
    service = WorkspaceTeamService(
        workspace_registry=workspace_registry,
        team_store=team_store,
        agent_registry=AgentRegistry({}),
        available_providers=("linear",),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_team_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: SimpleNamespace(list_agents=lambda: ()),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_collaboration_manager",
        lambda: SimpleNamespace(diagnostics=lambda: ()),
    )

    create_response = client.post(
        "/workspace-teams",
        json={
            "id": "research",
            "display_name": "Research",
            "workspace": "linear_delivery",
        },
    )
    role_response = client.put(
        "/workspace-teams/research/roles/reviewer",
        json={
            "display_name": "Reviewer",
            "cao_tools": ["read_inbox_message"],
            "mcp_servers": {"custom": {"command": "custom-mcp"}},
            "providers": {
                "linear": {
                    "reads": {
                        "tools": ["cao_linear.get_issue"],
                        "issues": ["*"],
                    }
                }
            },
        },
    )
    list_response = client.get("/workspace-teams")
    stored = WorkspaceTeamStore(tmp_path / "workspace-teams.json").get("research")

    assert create_response.status_code == 201
    assert role_response.status_code == 200
    assert role_response.json()["roles"]["reviewer"]["providers"]["linear"]["reads"]["issues"] == [
        "*"
    ]
    assert list_response.status_code == 200
    assert list_response.json()[0]["role_assignments"] == {}
    assert stored.roles["reviewer"] == WorkspaceTeamRole(
        display_name="Reviewer",
        cao_tools=("read_inbox_message",),
        mcp_servers={"custom": {"command": "custom-mcp"}},
        providers={
            "linear": {
                "reads": {
                    "tools": ["cao_linear.get_issue"],
                    "issues": ["*"],
                }
            }
        },
    )


def test_workspace_team_api_crud_lifecycle_uses_team_service(client, monkeypatch, tmp_path):
    workspace_registry = WorkspaceRegistry(
        (
            Workspace(
                id="linear_delivery",
                display_name="Linear Delivery",
                providers=("linear",),
                resolver=lambda event: None,
            ),
        )
    )
    service = WorkspaceTeamService(
        workspace_registry=workspace_registry,
        team_store=WorkspaceTeamStore(tmp_path / "workspace-teams.json", bootstrap_teams=()),
        agent_registry=AgentRegistry({}),
        available_providers=("linear",),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_team_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: SimpleNamespace(list_agents=lambda: ()),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_collaboration_manager",
        lambda: SimpleNamespace(diagnostics=lambda: ()),
    )

    created = client.post(
        "/workspace-teams",
        json={
            "id": "research",
            "display_name": "Research",
            "workspace": "linear_delivery",
        },
    )
    fetched = client.get("/workspace-teams/research")
    updated = client.put(
        "/workspace-teams/research",
        json={
            "id": "research",
            "display_name": "Research Renamed",
            "workspace": "linear_delivery",
        },
    )
    deleted = client.delete("/workspace-teams/research")

    assert created.status_code == 201
    assert created.json()["roles"]["member"]["deletable"] is False
    assert fetched.status_code == 200
    assert fetched.json()["id"] == "research"
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Research Renamed"
    assert deleted.status_code == 200
    assert deleted.json()["id"] == "research"
    assert service.list_teams() == ()


def test_workspace_team_role_delete_api_falls_assignments_back_to_member(
    client, monkeypatch, tmp_path
):
    workspace_registry = WorkspaceRegistry(
        (
            Workspace(
                id="linear_delivery",
                display_name="Linear Delivery",
                providers=("linear",),
                resolver=lambda event: None,
            ),
        )
    )
    service = WorkspaceTeamService(
        workspace_registry=workspace_registry,
        team_store=WorkspaceTeamStore(
            tmp_path / "workspace-teams.json",
            bootstrap_teams=(
                WorkspaceTeam(
                    id="research",
                    display_name="Research",
                    workspace="linear_delivery",
                    roles={"reviewer": WorkspaceTeamRole(display_name="Reviewer")},
                    role_assignments={"aria": "reviewer"},
                ),
            ),
        ),
        agent_registry=AgentRegistry({}),
        available_providers=("linear",),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_team_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: SimpleNamespace(list_agents=lambda: ()),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_collaboration_manager",
        lambda: SimpleNamespace(diagnostics=lambda: ()),
    )

    response = client.delete("/workspace-teams/research/roles/reviewer")

    assert response.status_code == 200
    assert "reviewer" not in response.json()["roles"]
    assert response.json()["role_assignments"] == {"aria": "member"}


def test_workspace_team_api_rejects_member_role_and_member_team_deletion(
    client, monkeypatch, tmp_path
):
    agents_root = tmp_path / "agents"
    write_agent(
        replace(_agent("aria"), workspace=AgentWorkspaceConfig(team="research")),
        agents_root=agents_root,
    )
    workspace_registry = WorkspaceRegistry(
        (
            Workspace(
                id="linear_delivery",
                display_name="Linear Delivery",
                providers=("linear",),
                resolver=lambda event: None,
            ),
        )
    )
    service = WorkspaceTeamService(
        workspace_registry=workspace_registry,
        team_store=WorkspaceTeamStore(
            tmp_path / "workspace-teams.json",
            bootstrap_teams=(
                WorkspaceTeam(
                    id="research",
                    display_name="Research",
                    workspace="linear_delivery",
                ),
            ),
        ),
        agent_registry=load_agent_registry(agents_root=agents_root),
        available_providers=("linear",),
        agents_root=agents_root,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_team_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: SimpleNamespace(
            list_agents=lambda: tuple(load_agent_registry(agents_root=agents_root).all().values())
        ),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_collaboration_manager",
        lambda: SimpleNamespace(diagnostics=lambda: ()),
    )

    role_delete = client.delete("/workspace-teams/research/roles/member")
    team_delete = client.delete("/workspace-teams/research")

    assert role_delete.status_code == 400
    assert "member role cannot be deleted" in role_delete.json()["detail"]
    assert team_delete.status_code == 400
    assert "members exist" in team_delete.json()["detail"]


def test_workspace_team_metadata_put_rejects_legacy_role_policy_payload(client, monkeypatch):
    team = WorkspaceTeam(
        id="research",
        display_name="Research",
        workspace="linear_delivery",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_team_service",
        lambda: SimpleNamespace(get_team=lambda team_id: team),
    )

    response = client.put(
        "/workspace-teams/research",
        json={
            "id": "research",
            "display_name": "Research",
            "workspace": "linear_delivery",
            "roles": {"reviewer": {"display_name": "Reviewer"}},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"][0]["loc"] == ["body", "roles"]


def test_workspace_team_member_api_moves_agent_and_returns_member_detail(
    client, monkeypatch, tmp_path
):
    agents_root = tmp_path / "agents"
    write_agent(
        replace(_agent("aria"), workspace=AgentWorkspaceConfig(team="delivery")),
        agents_root=agents_root,
    )
    workspace_registry = WorkspaceRegistry(
        (
            Workspace(
                id="linear_delivery",
                display_name="Linear Delivery",
                providers=("linear",),
                resolver=lambda event: None,
            ),
        )
    )
    team_store = WorkspaceTeamStore(
        tmp_path / "workspace-teams.json",
        bootstrap_teams=(
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace="linear_delivery",
                roles={"reviewer": WorkspaceTeamRole(display_name="Reviewer")},
                role_assignments={"aria": "reviewer"},
            ),
            WorkspaceTeam(
                id="research",
                display_name="Research",
                workspace="linear_delivery",
            ),
        ),
    )
    service = WorkspaceTeamService(
        workspace_registry=workspace_registry,
        team_store=team_store,
        agent_registry=load_agent_registry(agents_root=agents_root),
        available_providers=("linear",),
        agents_root=agents_root,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_team_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: SimpleNamespace(
            list_agents=lambda: tuple(load_agent_registry(agents_root=agents_root).all().values())
        ),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_collaboration_manager",
        lambda: SimpleNamespace(diagnostics=lambda: ()),
    )

    response = client.put(
        "/workspace-teams/research/members/aria",
        json={},
    )

    assert response.status_code == 200
    assert load_agent("aria", agents_root=agents_root).workspace.team == "research"
    assert response.json()["members"] == ["aria"]
    assert response.json()["member_details"] == [
        {
            "agent_id": "aria",
            "display_name": "Implementation Partner",
            "role_id": "member",
            "role_explicitly_assigned": True,
        }
    ]
    assert (
        WorkspaceTeamStore(tmp_path / "workspace-teams.json").get("delivery").role_assignments == {}
    )


def test_workspace_team_member_remove_api_clears_membership_and_assignment(
    client, monkeypatch, tmp_path
):
    agents_root = tmp_path / "agents"
    write_agent(
        replace(_agent("aria"), workspace=AgentWorkspaceConfig(team="delivery")),
        agents_root=agents_root,
    )
    workspace_registry = WorkspaceRegistry(
        (
            Workspace(
                id="linear_delivery",
                display_name="Linear Delivery",
                providers=("linear",),
                resolver=lambda event: None,
            ),
        )
    )
    team_store = WorkspaceTeamStore(
        tmp_path / "workspace-teams.json",
        bootstrap_teams=(
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace="linear_delivery",
                roles={"reviewer": WorkspaceTeamRole(display_name="Reviewer")},
                role_assignments={"aria": "reviewer"},
            ),
        ),
    )
    service = WorkspaceTeamService(
        workspace_registry=workspace_registry,
        team_store=team_store,
        agent_registry=load_agent_registry(agents_root=agents_root),
        available_providers=("linear",),
        agents_root=agents_root,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_team_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: SimpleNamespace(
            list_agents=lambda: tuple(load_agent_registry(agents_root=agents_root).all().values())
        ),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_collaboration_manager",
        lambda: SimpleNamespace(diagnostics=lambda: ()),
    )

    response = client.delete("/workspace-teams/delivery/members/aria")

    assert response.status_code == 200
    assert load_agent("aria", agents_root=agents_root).workspace.team is None
    assert response.json()["members"] == []
    assert (
        WorkspaceTeamStore(tmp_path / "workspace-teams.json").get("delivery").role_assignments == {}
    )


def test_workspace_team_response_hides_provider_pruning_diagnostics(client, monkeypatch):
    team = WorkspaceTeam(
        id="cao_delivery",
        display_name="CAO Delivery",
        workspace="linear_delivery",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_team_service",
        lambda: SimpleNamespace(list_teams=lambda: (team,)),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: SimpleNamespace(list_agents=lambda: ()),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_workspace_collaboration_manager",
        lambda: SimpleNamespace(
            diagnostics=lambda: (
                WorkspaceDiagnostic(
                    code="pruned_provider_identity",
                    message="Workspace team cao_delivery pruned linear tool access for discovery",
                    team_id="cao_delivery",
                    workspace_id="linear_delivery",
                    agent_id="discovery",
                    provider_name="linear",
                ),
                WorkspaceDiagnostic(
                    code="unavailable_provider",
                    message=(
                        "Workspace team cao_delivery workspace linear_delivery "
                        "requires unavailable provider linear"
                    ),
                    team_id="cao_delivery",
                    workspace_id="linear_delivery",
                    provider_name="linear",
                ),
            )
        ),
    )

    response = client.get("/workspace-teams")

    assert response.status_code == 200
    assert response.json()[0]["diagnostics"] == [
        "Workspace team cao_delivery workspace linear_delivery requires unavailable provider linear"
    ]


def test_list_agents_active_filter(client, monkeypatch):
    manager = _FakeAgentManager((_status(active=True), _status("reviewer")))
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: manager,
    )
    _install_route_tool_service(monkeypatch, manager)

    response = client.get("/agents?active=true")

    assert response.status_code == 200
    assert [row["agent_id"] for row in response.json()] == ["implementation_partner"]


def test_get_agent_unknown_returns_404(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _FakeAgentManager((_status(active=True),)),
    )

    response = client.get("/agents/missing")

    assert response.status_code == 404
    assert "Unknown CAO agent" in response.json()["detail"]


def test_start_agent_starts_configured_agent(client, monkeypatch):
    manager = _FakeAgentManager((_status(),))
    resolve_calls = []

    def _resolve_agent(agent_id: str):
        resolve_calls.append(agent_id)
        return _agent(agent_id)

    manager.resolve_agent = _resolve_agent  # type: ignore[attr-defined]

    handle_calls = []

    class _Handle:
        def __init__(self, agent, *, agent_manager):
            handle_calls.append((agent.id, agent_manager))

        def ensure_started(self):
            return SimpleNamespace(id="terminal-new")

    monkeypatch.setattr("cli_agent_orchestrator.api.main.default_agent_manager", lambda: manager)
    monkeypatch.setattr("cli_agent_orchestrator.api.main.AgentRuntimeHandle", _Handle)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.create_terminal_dashboard_token",
        lambda terminal_id: f"token-{terminal_id}",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.terminal_service.get_terminal",
        lambda terminal_id: {
            "id": terminal_id,
            "name": "implementation-partner-1234",
            "provider": "codex",
            "session_name": "cao-implementation-partner",
            "agent_id": "implementation_partner",
            "workspace_context_id": "wctx-default",
            "allowed_tools": None,
            "status": "idle",
            "last_active": datetime(2026, 5, 13, 12, 0, 0),
        },
    )

    response = client.post("/agents/implementation_partner/start")

    assert response.status_code == 200
    body = response.json()
    assert body["terminal"]["id"] == "terminal-new"
    assert body["terminal_token"] == "token-terminal-new"
    assert resolve_calls == ["implementation_partner"]
    assert handle_calls == [("implementation_partner", manager)]


def test_start_agent_rejects_existing_live_instance(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _FakeAgentManager((_status(active=True),)),
    )

    response = client.post("/agents/implementation_partner/start")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "Agent 'implementation_partner' is already running",
        "terminal_id": "abcd1234",
    }


def test_start_agent_reports_database_race_as_existing_live_instance(client, monkeypatch):
    manager = _FakeAgentManager((_status(),))

    def _resolve_agent(agent_id: str):
        return _agent(agent_id)

    manager.resolve_agent = _resolve_agent  # type: ignore[attr-defined]

    class _Handle:
        def __init__(self, agent, *, agent_manager):
            pass

        def ensure_started(self):
            raise TerminalAgentAlreadyRunningError("implementation_partner", "terminal-race")

    monkeypatch.setattr("cli_agent_orchestrator.api.main.default_agent_manager", lambda: manager)
    monkeypatch.setattr("cli_agent_orchestrator.api.main.AgentRuntimeHandle", _Handle)

    response = client.post("/agents/implementation_partner/start")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "Agent 'implementation_partner' is already running",
        "terminal_id": "terminal-race",
    }


def test_stop_agent_deletes_existing_live_instance(client, monkeypatch):
    delete_calls = []

    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _FakeAgentManager((_status(active=True),)),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.terminal_service.delete_terminal",
        lambda terminal_id, *, require_window_killed: delete_calls.append(
            (terminal_id, require_window_killed)
        )
        or True,
    )

    response = client.post("/agents/implementation_partner/stop")

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert delete_calls == [("abcd1234", True)]


def test_update_agent_rejects_unsupported_cli_provider(client, monkeypatch):
    """An unknown ``cli_provider`` returns 400 with a clear pointer at the field."""
    existing_agent = _agent()
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.load_agent",
        lambda agent_id: existing_agent,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.patch_agent_config",
        lambda agent, *, changed_fields: None,
    )

    response = client.put(
        "/agents/implementation_partner",
        json={"cli_provider": "bogus"},
    )

    assert response.status_code == 400
    assert "cli_provider" in response.json()["detail"]
    assert "bogus" in response.json()["detail"]


def test_update_agent_accepts_reasoning_effort_without_static_provider_declarations(
    client, monkeypatch
):
    """Agent writes no longer validate effort against removed static declarations."""
    existing_agent = _agent()
    patched_agents = []
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.load_agent",
        lambda agent_id: existing_agent,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.patch_agent_config",
        lambda agent, *, changed_fields: patched_agents.append(agent),
    )

    response = client.put(
        "/agents/implementation_partner",
        json={"cli_provider": "q_cli", "model": None, "reasoning_effort": "low"},
    )

    assert response.status_code == 200
    assert patched_agents[0].cli_provider == "q_cli"
    assert patched_agents[0].reasoning_effort == "low"


def test_update_agent_allows_empty_mcp_tools_and_skills(client, monkeypatch):
    existing_agent = _agent()
    patched_agent = None
    patched_fields = None

    def _patch_agent_config(agent, *, changed_fields):
        nonlocal patched_agent, patched_fields
        patched_agent = agent
        patched_fields = changed_fields

    class _WriteThroughAgentManager:
        def status_for_agent(self, agent_id: str):
            assert patched_agent is not None
            return AgentStatus(
                agent_id=agent_id,
                display_name=patched_agent.display_name,
                cli_provider=patched_agent.cli_provider,
                workdir=patched_agent.workdir,
                session_name=patched_agent.session_name,
                agent=patched_agent,
                active=False,
            )

    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.load_agent",
        lambda agent_id: existing_agent,
    )
    monkeypatch.setattr("cli_agent_orchestrator.api.main.patch_agent_config", _patch_agent_config)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _WriteThroughAgentManager(),
    )

    response = client.put(
        "/agents/implementation_partner",
        json={
            "mcp_servers": {},
            "tools": [],
            "skills": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["config"]["mcp_servers"] == {}
    assert response.json()["config"]["tools"] == []
    assert response.json()["config"]["skills"] == []
    assert patched_fields == {"mcp_servers", "tools", "skills"}


def test_agent_crud_lifecycle_allows_running_update_and_confirmed_delete(
    client,
    monkeypatch,
    tmp_path,
    runtime_inbox_db_session,
):
    agents_root = tmp_path / "agents"
    monkeypatch.setattr("cli_agent_orchestrator.agent.AGENTS_ROOT", agents_root)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.create_terminal_dashboard_token",
        lambda terminal_id: f"token-{terminal_id}",
    )

    class _Handle:
        def __init__(self, agent, *, agent_manager):
            self.agent = agent

        def ensure_started(self):
            db_module.create_terminal(
                "terminal-crud",
                self.agent.session_name,
                "crud-agent-0001",
                self.agent.cli_provider,
                agent_id=self.agent.id,
                workspace_context_id=f"ctx_{self.agent.id}_default",
            )
            return SimpleNamespace(id="terminal-crud")

    def _get_terminal(terminal_id: str):
        metadata = db_module.get_terminal_metadata(terminal_id)
        assert metadata is not None
        return {
            "id": metadata["id"],
            "name": metadata["tmux_window"],
            "provider": metadata["provider"],
            "session_name": metadata["tmux_session"],
            "agent_id": metadata["agent_id"],
            "workspace_context_id": metadata["workspace_context_id"],
            "allowed_tools": metadata.get("allowed_tools"),
            "status": "idle",
            "last_active": metadata["last_active"],
        }

    delete_calls = []

    def _delete_terminal(terminal_id: str, *, require_window_killed: bool = False):
        delete_calls.append((terminal_id, require_window_killed))
        return db_module.delete_terminal(terminal_id)

    monkeypatch.setattr("cli_agent_orchestrator.api.main.AgentRuntimeHandle", _Handle)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.terminal_service.get_terminal",
        _get_terminal,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.terminal_service.delete_terminal",
        _delete_terminal,
    )

    created = client.post(
        "/agents",
        json={
            "id": "crud_agent",
            "display_name": "CRUD Agent",
            "cli_provider": "codex",
            "workdir": "/repo",
            "prompt": "# Initial\n",
        },
    )
    assert created.status_code == 201
    assert created.json()["agent_id"] == "crud_agent"
    assert (agents_root / "crud_agent" / "agent.toml").is_file()
    assert (agents_root / "crud_agent" / "prompt.md").read_text() == "# Initial\n"

    started = client.post("/agents/crud_agent/start")
    assert started.status_code == 200
    assert started.json()["terminal"]["id"] == "terminal-crud"
    assert started.json()["terminal_token"] == "token-terminal-crud"

    updated = client.put(
        "/agents/crud_agent",
        json={
            "display_name": "CRUD Agent Renamed",
            "model": "gpt-5.4",
            "reasoning_effort": "high",
            "prompt": "# Updated\n",
            "tools": [],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["active"] is True
    assert updated.json()["active_terminal_id"] == "terminal-crud"
    assert updated.json()["display_name"] == "CRUD Agent Renamed"
    assert updated.json()["config"]["prompt"] == "# Updated\n"
    assert updated.json()["config"]["model"] == "gpt-5.4"
    assert updated.json()["config"]["reasoning_effort"] == "high"
    assert 'model = "gpt-5.4"' in (agents_root / "crud_agent" / "agent.toml").read_text()
    assert 'reasoning_effort = "high"' in (agents_root / "crud_agent" / "agent.toml").read_text()
    assert (agents_root / "crud_agent" / "prompt.md").read_text() == "# Updated\n"

    live_delete = client.delete("/agents/crud_agent?confirm=true")
    assert live_delete.status_code == 409
    assert live_delete.json()["detail"] == {
        "message": "Agent 'crud_agent' is running",
        "terminal_id": "terminal-crud",
    }

    stopped = client.post("/agents/crud_agent/stop")
    assert stopped.status_code == 200
    assert stopped.json() == {"success": True}
    assert delete_calls == [("terminal-crud", True)]

    unconfirmed_delete = client.delete("/agents/crud_agent")
    assert unconfirmed_delete.status_code == 400
    assert unconfirmed_delete.json()["detail"] == "confirm=true is required"

    deleted = client.delete("/agents/crud_agent?confirm=true")
    assert deleted.status_code == 200
    assert deleted.json() == {"success": True}
    assert not (agents_root / "crud_agent").exists()


def test_create_agent_validation_returns_400_with_field_detail(client, monkeypatch, tmp_path):
    agents_root = tmp_path / "agents"
    monkeypatch.setattr("cli_agent_orchestrator.agent.AGENTS_ROOT", agents_root)

    response = client.post(
        "/agents",
        json={
            "id": "bad_agent",
            "cli_provider": "not_a_provider",
            "workdir": "/repo",
        },
    )

    assert response.status_code == 400
    assert "agents.bad_agent.cli_provider" in response.json()["detail"]


def test_create_agent_body_validation_returns_400_with_field_detail(client):
    response = client.post(
        "/agents",
        json={"id": "bad_agent", "mcp_servers": "not-a-table"},
    )

    assert response.status_code == 400
    assert response.json()["detail"][0]["loc"] == ["body", "mcp_servers"]


def test_update_agent_rejects_empty_required_field_and_clears_nullable_model(
    client,
    monkeypatch,
):
    existing_agent = _agent()
    patched_agent = None
    patched_fields = None

    def _patch_agent_config(agent, *, changed_fields):
        nonlocal patched_agent, patched_fields
        patched_agent = agent
        patched_fields = changed_fields

    class _WriteThroughAgentManager:
        def status_for_agent(self, agent_id: str):
            assert patched_agent is not None
            return AgentStatus(
                agent_id=agent_id,
                display_name=patched_agent.display_name,
                cli_provider=patched_agent.cli_provider,
                workdir=patched_agent.workdir,
                session_name=patched_agent.session_name,
                agent=patched_agent,
                active=False,
            )

    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.load_agent",
        lambda agent_id: existing_agent,
    )
    monkeypatch.setattr("cli_agent_orchestrator.api.main.patch_agent_config", _patch_agent_config)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _WriteThroughAgentManager(),
    )

    empty_name = client.put(
        "/agents/implementation_partner",
        json={"display_name": ""},
    )
    assert empty_name.status_code == 400
    assert "agents.implementation_partner.display_name" in empty_name.json()["detail"]

    clear_model = client.put(
        "/agents/implementation_partner",
        json={"model": None},
    )
    assert clear_model.status_code == 200
    assert clear_model.json()["config"]["model"] is None
    assert patched_agent is not None
    assert patched_agent.model is None
    assert patched_fields == {"model"}


def test_update_agent_rejects_direct_workspace_team_mutation(client, monkeypatch):
    existing_agent = replace(_agent(), workspace=AgentWorkspaceConfig(team="cao_delivery"))
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.load_agent",
        lambda agent_id: existing_agent,
    )

    clear_response = client.put(
        "/agents/implementation_partner",
        json={"workspace": {"team": None}},
    )
    move_response = client.put(
        "/agents/implementation_partner",
        json={"workspace": {"team": "research"}},
    )

    assert clear_response.status_code == 400
    assert "/workspace-teams/{team_id}/members/{agent_id}" in clear_response.json()["detail"]
    assert move_response.status_code == 400
    assert "/workspace-teams/{team_id}/members/{agent_id}" in move_response.json()["detail"]


def test_create_agent_rejects_direct_workspace_team_membership(client, monkeypatch, tmp_path):
    agents_root = tmp_path / "agents"
    monkeypatch.setattr("cli_agent_orchestrator.agent.AGENTS_ROOT", agents_root)

    response = client.post(
        "/agents",
        json={
            "id": "teamed_agent",
            "display_name": "Teamed Agent",
            "cli_provider": "codex",
            "workdir": "/repo",
            "workspace": {"team": "research"},
        },
    )

    assert response.status_code == 400
    assert "/workspace-teams/{team_id}/members/{agent_id}" in response.json()["detail"]


def test_update_agent_rejects_legacy_workspace(client, monkeypatch):
    existing_agent = replace(_agent(), workspace=AgentWorkspaceConfig(team="cao_delivery"))
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.load_agent",
        lambda agent_id: existing_agent,
    )

    response = client.put(
        "/agents/implementation_partner",
        json={"workspace": {"setup": "linear_delivery"}},
    )

    assert response.status_code == 400
    assert "setup" in response.text


def test_runtime_terminal_endpoint_uses_agent_manager_status(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _FakeAgentManager((_status(active=True),)),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.terminal_service.get_terminal",
        lambda terminal_id: {
            "id": terminal_id,
            "name": "developer-0000",
            "provider": "codex",
            "session_name": "cao-implementation-partner",
            "agent_id": "implementation_partner",
            "workspace_context_id": "wctx_abc",
            "status": "idle",
            "last_active": datetime(2026, 5, 13, 12, 0, 0),
        },
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.create_terminal_dashboard_token",
        lambda terminal_id: f"token-{terminal_id}",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main._agent_dashboard_request_authorized",
        lambda request, agent_id, agent_token: True,
    )

    response = client.get("/agents/runtime/implementation_partner/terminal")

    assert response.status_code == 200
    assert response.json()["terminal"]["id"] == "abcd1234"
    assert response.json()["terminal_token"] == "token-abcd1234"


def test_runtime_terminal_endpoint_accepts_agent_dashboard_token(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: _FakeAgentManager((_status(active=True),)),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.terminal_service.get_terminal",
        lambda terminal_id: {
            "id": terminal_id,
            "name": "developer-0000",
            "provider": "codex",
            "session_name": "cao-implementation-partner",
            "agent_id": "implementation_partner",
            "workspace_context_id": "wctx_abc",
            "status": "idle",
            "last_active": datetime(2026, 5, 13, 12, 0, 0),
        },
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.create_terminal_dashboard_token",
        lambda terminal_id: f"token-{terminal_id}",
    )

    response_without_token = client.get("/agents/runtime/implementation_partner/terminal")
    assert response_without_token.status_code == 403

    response = client.get(
        "/agents/runtime/implementation_partner/terminal",
        params={"agent_token": create_agent_dashboard_token("implementation_partner")},
    )

    assert response.status_code == 200
    assert response.json()["terminal"]["id"] == "abcd1234"
    assert response.json()["terminal_token"] == "token-abcd1234"


def _linear_mentioned_event(
    *,
    event_id: str = "linear:agent_mentioned:event-1",
    occurred_at: CaoEventOccurredAt = OCCURRED_AT,
    source_id: str = "msg-1",
    correlation_id: str | None = "thread-1",
    causation_id: str | None = None,
    participants: tuple[AgentParticipant, ...] | None = None,
) -> LinearAgentMentionedEvent:
    return LinearAgentMentionedEvent(
        event_id=CaoEventId(event_id),
        source=CaoEventSourceRef(
            source_type=CaoEventSourceType("linear"),
            source_id=CaoEventSourceId(source_id),
        ),
        occurred_at=occurred_at,
        correlation_id=CaoCorrelationId(correlation_id) if correlation_id is not None else None,
        causation_id=CaoCausationId(causation_id) if causation_id is not None else None,
        event_type="AgentSession",
        app_key="linear-app",
        agent_id="implementation_partner",
        app_user_id="user-1",
        app_user_name="RJ Wilson",
        issue_id="issue-id-1",
        issue_identifier="CAO-96",
        issue_url="https://linear.app/yards-framework/issue/CAO-96/example",
        issue_title="Persist events",
        issue_state="Backlog",
        parent_issue_id="parent-id-1",
        parent_issue_identifier="CAO-89",
        agent_session_id="session-1",
        thread_id="thread-1",
        thread_url="https://linear.app/session/1",
        prompt_context="Please implement this.",
        message_id=source_id,
        message_body="Please implement CAO-96.",
        message_kind="comment",
        message_metadata={"visibility": "public"},
        action="create",
        should_notify_agent=True,
        suppression_reason=None,
        raw_payload={"typed_contract_field": True},
        delivery_id="delivery-1",
        metadata={"classification": "human_mention_or_prompt"},
        agent_participants=(
            participants
            if participants is not None
            else (
                AgentParticipant(
                    agent_id="implementation_partner",
                    role="mentioned",
                ),
            )
        ),
    )


def _manager_with_timeline_agents():
    return _FakeAgentManager((_status(), _status("reviewer")))


def _patch_default_agent_manager(monkeypatch, manager):
    status_calls = []
    original_status_for_agent = manager.status_for_agent

    def _status_for_agent(agent_id: str):
        status_calls.append(agent_id)
        return original_status_for_agent(agent_id)

    monkeypatch.setattr(manager, "status_for_agent", _status_for_agent)
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_manager",
        lambda: manager,
    )
    return status_calls


def _publish_agent_timeline_scenario(
    *,
    mention_correlation_id: str,
    broadcast_correlation_id: str,
    broadcast_partner_role: str,
    broadcast_reviewer_role: str,
    workspace_correlation_id: str,
) -> tuple[
    LinearAgentMentionedEvent,
    AgentRuntimeNotificationDeliveryEvent,
    LinearAgentMentionedEvent,
    RuntimeWorkspaceEvent,
]:
    mention = _linear_mentioned_event(
        event_id="linear:agent_mentioned:mention",
        occurred_at=OCCURRED_AT,
        correlation_id=mention_correlation_id,
    )
    delivery = notification_delivery_event(
        agent_id="implementation_partner",
        workspace_context_id="wctx-1",
        inbox_notification_id=42,
        inbox_receiver_id="implementation_partner",
        terminal_id="terminal-1",
        runtime_status="ready",
        outcome="delivered",
        attempted=True,
        delivered=True,
        error=None,
        source_kind="linear_event",
        message_body="Please implement CAO-96.",
        causing_event=mention,
    )
    delivery = replace(
        delivery,
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=1)),
    )
    broadcast = _linear_mentioned_event(
        event_id="linear:agent_mentioned:broadcast",
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=2)),
        source_id="msg-broadcast",
        correlation_id=broadcast_correlation_id,
        participants=(
            AgentParticipant(
                agent_id="implementation_partner",
                role=broadcast_partner_role,
            ),
            AgentParticipant(agent_id="reviewer", role=broadcast_reviewer_role),
        ),
    )
    workspace = workspace_runtime_event(
        workspace_context_id="wctx-1",
        action="refresh",
        runtime_status="ready",
        correlation_id=CaoCorrelationId(workspace_correlation_id),
    )
    workspace = replace(
        workspace,
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=3)),
    )
    dispatcher = CaoEventDispatcher(
        (
            LinearAgentMentionedEvent,
            AgentRuntimeNotificationDeliveryEvent,
            RuntimeWorkspaceEvent,
        ),
        persist_events=True,
    )
    for event in (mention, delivery, broadcast, workspace):
        dispatcher.publish(event)
    return mention, delivery, broadcast, workspace


def _event_ids(response_events):
    return [event["event_id"] for event in response_events]


def test_agent_timeline_openapi_preserves_public_event_envelope(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    timeline_event_schema = schemas["AgentTimelineEventResponse"]
    timeline_response_schema = schemas["AgentTimelineResponse"]
    related_response_schema = schemas["AgentRelatedEventsResponse"]
    causation_response_schema = schemas["AgentCausationRelatedEventsResponse"]
    event_data_schema = timeline_event_schema["properties"]["event_data"]

    assert timeline_event_schema["properties"]["event_type_key"] == {
        "type": "string",
        "title": "Event Type Key",
    }
    assert "event_type_key" in timeline_event_schema["required"]
    assert event_data_schema["type"] == "object"
    assert event_data_schema["additionalProperties"] is True
    assert "event_data" in timeline_event_schema["required"]
    assert timeline_response_schema["properties"]["events"]["items"] == {
        "$ref": "#/components/schemas/AgentTimelineEventResponse"
    }
    assert related_response_schema["properties"]["event"] == {
        "$ref": "#/components/schemas/AgentTimelineEventResponse"
    }
    assert related_response_schema["properties"]["correlation_events"]["items"] == {
        "$ref": "#/components/schemas/AgentTimelineEventResponse"
    }
    assert related_response_schema["properties"]["causation_events"] == {
        "$ref": "#/components/schemas/AgentCausationRelatedEventsResponse"
    }
    assert causation_response_schema["properties"]["direct_cause"]["anyOf"] == [
        {"$ref": "#/components/schemas/AgentTimelineEventResponse"},
        {"type": "null"},
    ]
    assert causation_response_schema["properties"]["direct_effects"]["items"] == {
        "$ref": "#/components/schemas/AgentTimelineEventResponse"
    }


def test_agent_timeline_route_returns_participant_index_rows(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _manager_with_timeline_agents()
    status_calls = _patch_default_agent_manager(monkeypatch, manager)
    mention, delivery, broadcast, workspace = _publish_agent_timeline_scenario(
        mention_correlation_id="thread-1",
        broadcast_correlation_id="thread-broadcast",
        broadcast_partner_role="mentioned",
        broadcast_reviewer_role="observer",
        workspace_correlation_id="workspace-refresh",
    )

    response = client.get("/agents/implementation_partner/timeline")

    assert response.status_code == 200
    body = response.json()
    assert status_calls == ["implementation_partner"]
    assert body["agent"]["agent_id"] == "implementation_partner"
    assert _event_ids(body["events"]) == [
        str(mention.event_id),
        str(delivery.event_id),
        str(broadcast.event_id),
    ]
    assert str(workspace.event_id) not in _event_ids(body["events"])
    assert db_module.get_cao_event(str(workspace.event_id)) is not None
    assert [(event["event_name"], event["participant_role"]) for event in body["events"]] == [
        ("agent_mentioned", "mentioned"),
        ("agent_runtime_notification_delivery", "delivery_target"),
        ("agent_mentioned", "mentioned"),
    ]
    assert body["events"][0]["correlation_id"] == "thread-1"
    assert body["events"][0]["event_data"]["issue_title"] == "Persist events"
    assert body["events"][0]["event_data"]["message_body"] == "Please implement CAO-96."
    assert body["events"][0]["event_data"]["raw_payload"] == {"typed_contract_field": True}
    assert body["events"][1]["event_data"]["terminal_id"] == "terminal-1"
    assert body["events"][1]["event_data"]["source_kind"] == "linear_event"
    assert body["events"][1]["event_data"]["message_body"] == "Please implement CAO-96."
    assert body["events"][1]["causation_id"] == str(mention.event_id)


def test_agent_timeline_route_preserves_broadcast_viewpoint(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _manager_with_timeline_agents()
    _patch_default_agent_manager(monkeypatch, manager)
    _, _, broadcast, _ = _publish_agent_timeline_scenario(
        mention_correlation_id="thread-1",
        broadcast_correlation_id="thread-broadcast",
        broadcast_partner_role="mentioned",
        broadcast_reviewer_role="observer",
        workspace_correlation_id="workspace-refresh",
    )

    partner_response = client.get("/agents/implementation_partner/timeline")
    reviewer_response = client.get("/agents/reviewer/timeline")

    assert partner_response.status_code == 200
    assert reviewer_response.status_code == 200
    partner_broadcast_events = [
        event
        for event in partner_response.json()["events"]
        if event["event_id"] == str(broadcast.event_id)
    ]
    assert partner_broadcast_events[0]["participant_role"] == "mentioned"
    reviewer_events = reviewer_response.json()["events"]
    assert len(reviewer_events) == 1
    reviewer_event = reviewer_events[0]
    assert {key: value for key, value in reviewer_event.items() if key != "event_data"} == {
        "event_id": str(broadcast.event_id),
        "event_name": "agent_mentioned",
        "event_type_key": (
            "cli_agent_orchestrator.linear.workspace_events.LinearAgentMentionedEvent"
        ),
        "source_type": "linear",
        "source_id": "msg-broadcast",
        "occurred_at": "2026-05-13T12:02:00",
        "correlation_id": "thread-broadcast",
        "causation_id": None,
        "participant_role": "observer",
    }
    assert reviewer_event["event_data"]["message_id"] == "msg-broadcast"
    assert reviewer_event["event_data"]["agent_participants"] == [
        {"agent_id": "implementation_partner", "role": "mentioned"},
        {"agent_id": "reviewer", "role": "observer"},
    ]


def test_agent_timeline_route_unknown_agent_returns_404(
    client,
    monkeypatch,
):
    manager = _FakeAgentManager((_status(),))
    _patch_default_agent_manager(monkeypatch, manager)

    response = client.get("/agents/missing/timeline")

    assert response.status_code == 404
    assert "Unknown CAO agent" in response.json()["detail"]


def test_agent_related_events_route_uses_envelope_threads(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _manager_with_timeline_agents()
    _patch_default_agent_manager(monkeypatch, manager)
    mention, delivery, _, _ = _publish_agent_timeline_scenario(
        mention_correlation_id="thread-1",
        broadcast_correlation_id="thread-broadcast",
        broadcast_partner_role="mentioned",
        broadcast_reviewer_role="observer",
        workspace_correlation_id="workspace-refresh",
    )

    mention_response = client.get(
        f"/agents/implementation_partner/events/{mention.event_id}/related"
    )
    delivery_response = client.get(
        f"/agents/implementation_partner/events/{delivery.event_id}/related"
    )

    assert mention_response.status_code == 200
    assert _event_ids(mention_response.json()["correlation_events"]) == [
        str(mention.event_id),
        str(delivery.event_id),
    ]
    assert mention_response.json()["event"]["event_data"]["issue_identifier"] == "CAO-96"
    assert mention_response.json()["correlation_events"][0]["event_data"]["message_body"] == (
        "Please implement CAO-96."
    )
    assert mention_response.json()["correlation_events"][1]["event_data"]["terminal_id"] == (
        "terminal-1"
    )
    assert mention_response.json()["causation_events"]["direct_cause"] is None
    assert _event_ids(mention_response.json()["causation_events"]["direct_effects"]) == [
        str(delivery.event_id)
    ]
    assert (
        mention_response.json()["causation_events"]["direct_effects"][0]["event_data"]["outcome"]
        == "delivered"
    )
    assert delivery_response.status_code == 200
    assert delivery_response.json()["causation_events"]["direct_cause"]["event_id"] == str(
        mention.event_id
    )
    assert (
        delivery_response.json()["causation_events"]["direct_cause"]["event_data"]["message_body"]
        == "Please implement CAO-96."
    )


def test_agent_related_events_route_keeps_untaught_events_related_and_roleful(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _manager_with_timeline_agents()
    _patch_default_agent_manager(monkeypatch, manager)
    root = _ExperimentalAuditEvent(
        event_id=CaoEventId("experimental:audit:event-1"),
        source=CaoEventSourceRef(
            source_type=CaoEventSourceType("audit"),
            source_id=CaoEventSourceId("audit-1"),
        ),
        occurred_at=OCCURRED_AT,
        correlation_id=CaoCorrelationId("thread-audit"),
        causation_id=None,
        audit_kind="workspace_scan",
        confidence=0.92,
        agent_participants=(
            AgentParticipant(agent_id="implementation_partner", role="participant"),
        ),
    )
    effect = replace(
        root,
        event_id=CaoEventId("experimental:audit:event-2"),
        source=CaoEventSourceRef(
            source_type=CaoEventSourceType("audit"),
            source_id=CaoEventSourceId("audit-2"),
        ),
        occurred_at=CaoEventOccurredAt(OCCURRED_AT + timedelta(minutes=1)),
        causation_id=CaoCausationId(str(root.event_id)),
        audit_kind="related_probe",
        confidence=0.73,
        agent_participants=(
            AgentParticipant(agent_id="implementation_partner", role="effect_target"),
        ),
    )
    dispatcher = CaoEventDispatcher((_ExperimentalAuditEvent,), persist_events=True)
    dispatcher.publish(effect)
    dispatcher.publish(root)

    response = client.get(f"/agents/implementation_partner/events/{root.event_id}/related")

    assert response.status_code == 200
    body = response.json()
    assert body["event"]["event_name"] == "experimental_audit_event"
    assert body["event"]["participant_role"] == "participant"
    assert body["event"]["event_data"]["audit_kind"] == "workspace_scan"
    assert _event_ids(body["correlation_events"]) == [
        str(root.event_id),
        str(effect.event_id),
    ]
    assert _event_ids(body["causation_events"]["direct_effects"]) == [str(effect.event_id)]
    assert body["causation_events"]["direct_effects"][0]["participant_role"] == ("effect_target")
    assert (
        body["causation_events"]["direct_effects"][0]["event_data"]["audit_kind"] == "related_probe"
    )


def test_agent_related_events_route_handles_missing_relatedness_and_unknown_event(
    client,
    monkeypatch,
    runtime_inbox_db_session,
):
    manager = _FakeAgentManager((_status(),))
    _patch_default_agent_manager(monkeypatch, manager)
    isolated = _linear_mentioned_event(
        event_id="linear:agent_mentioned:isolated",
        correlation_id=None,
        causation_id=None,
    )
    dispatcher = CaoEventDispatcher((LinearAgentMentionedEvent,), persist_events=True)
    dispatcher.publish(isolated)

    response = client.get(f"/agents/implementation_partner/events/{isolated.event_id}/related")
    missing_response = client.get("/agents/implementation_partner/events/missing-event/related")

    assert response.status_code == 200
    assert response.json()["correlation_events"] == []
    assert response.json()["causation_events"] == {
        "direct_cause": None,
        "direct_effects": [],
    }
    assert missing_response.status_code == 404
    assert "Unknown CAO event" in missing_response.json()["detail"]

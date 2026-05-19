from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from cli_agent_orchestrator.agent import (
    Agent,
    AgentRegistry,
    AgentWorkspaceConfig,
    load_agent,
    load_agent_registry,
    write_agent,
)
from cli_agent_orchestrator.workspace_contexts import WorkspaceContextResolution
from cli_agent_orchestrator.workspace_setups import (
    DEFAULT_WORKSPACE_SETUP_ID,
    DEFAULT_WORKSPACE_TEAM_ID,
    WorkspaceCollaborationManager,
    WorkspaceProviderCandidateMapping,
    WorkspaceProviderView,
    WorkspaceSetup,
    WorkspaceSetupConfigError,
    WorkspaceSetupRegistry,
    WorkspaceTeam,
    WorkspaceTeamAuthorizedMapping,
    WorkspaceTeamRegistry,
    WorkspaceTeamRole,
    WorkspaceTeamService,
    WorkspaceTeamStore,
    default_workspace_team_service,
)


def _agent(agent_id: str, team: str | None = None) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(team=team),
    )


@dataclass(frozen=True)
class Event:
    agent_key: str


class RecordingProviderAdapter:
    provider_name = "test"

    def build_candidate_mappings(
        self, agent_registry: AgentRegistry
    ) -> tuple[WorkspaceProviderCandidateMapping, ...]:
        return (
            WorkspaceProviderCandidateMapping(
                provider_name="test",
                agent_id="agent_a",
                mapping_kind="presence",
                provider_identity="app_user_id",
                provider_value="provider-a",
                payload={"agent": "agent_a"},
            ),
            WorkspaceProviderCandidateMapping(
                provider_name="test",
                agent_id="agent_b",
                mapping_kind="presence",
                provider_identity="app_user_id",
                provider_value="provider-b",
                payload={"agent": "agent_b"},
            ),
        )

    def build_provider_view(
        self,
        *,
        team: WorkspaceTeam,
        setup: WorkspaceSetup,
        authorized_mappings: tuple[WorkspaceTeamAuthorizedMapping, ...],
        agent_registry: AgentRegistry,
    ) -> WorkspaceProviderView:
        return WorkspaceProviderView(
            team_id=team.id,
            setup_id=setup.id,
            provider_name="test",
            value={mapping.provider_value: mapping.agent_id for mapping in authorized_mappings},
        )

    def resolve_event_agent_id(
        self, *, provider_view: WorkspaceProviderView, event
    ) -> tuple[str, object]:
        try:
            return provider_view.value[event.agent_key], event.agent_key
        except KeyError as exc:
            raise WorkspaceSetupConfigError("provider identity is not team-authorized") from exc

    def candidate_mappings_for_event(
        self,
        *,
        event,
        candidates: tuple[WorkspaceProviderCandidateMapping, ...],
    ) -> tuple[WorkspaceProviderCandidateMapping, ...]:
        return tuple(
            candidate
            for candidate in candidates
            if candidate.provider_identity == "app_user_id"
            and candidate.provider_value == event.agent_key
        )

    def describe_event_identity(self, event) -> str:
        return event.agent_key


class DuplicateIdentityProviderAdapter(RecordingProviderAdapter):
    def build_candidate_mappings(
        self, agent_registry: AgentRegistry
    ) -> tuple[WorkspaceProviderCandidateMapping, ...]:
        return (
            WorkspaceProviderCandidateMapping(
                provider_name="test",
                agent_id="agent_a",
                mapping_kind="presence",
                provider_identity="app_user_id",
                provider_value="shared-provider-user",
                payload={"agent": "agent_a"},
            ),
            WorkspaceProviderCandidateMapping(
                provider_name="test",
                agent_id="agent_b",
                mapping_kind="presence",
                provider_identity="app_user_id",
                provider_value="shared-provider-user",
                payload={"agent": "agent_b"},
            ),
        )


def _resolver(_event):
    return WorkspaceContextResolution(
        workspace_context_id="wctx",
        resolver_id="linear_planning",
        boundary_provider_id="test",
        boundary_object_type="issue",
        boundary_object_id="CAO-1",
    )


def _setup_registry() -> WorkspaceSetupRegistry:
    return WorkspaceSetupRegistry(
        (
            WorkspaceSetup(
                id=DEFAULT_WORKSPACE_SETUP_ID,
                display_name="Linear Delivery Setup",
                providers=("test",),
                resolver=_resolver,
            ),
        )
    )


def _team_store(tmp_path, *teams: WorkspaceTeam) -> WorkspaceTeamStore:
    return WorkspaceTeamStore(
        tmp_path / "workspace-teams.json",
        bootstrap_teams=teams
        or (
            WorkspaceTeam(
                id=DEFAULT_WORKSPACE_TEAM_ID,
                display_name="CAO Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
            ),
        ),
    )


def _manager(tmp_path, registry: AgentRegistry, *teams: WorkspaceTeam):
    store = _team_store(tmp_path, *teams)
    return WorkspaceCollaborationManager(
        setup_registry=_setup_registry(),
        team_registry=WorkspaceTeamRegistry(store),
        agent_registry=registry,
        provider_adapters={"test": RecordingProviderAdapter()},
    )


def _write_agents(tmp_path, *agents: Agent):
    agents_root = tmp_path / "agents"
    for agent in agents:
        write_agent(agent, agents_root=agents_root)
    return agents_root


def test_team_store_seeds_bootstrap_and_persists_dashboard_edits(tmp_path):
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(tmp_path),
        agent_registry=AgentRegistry({}),
        available_providers=("test",),
    )

    service.create_or_update_team(
        team_id="research",
        display_name="Research",
        workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
    )
    reloaded = WorkspaceTeamRegistry(_team_store(tmp_path))

    assert [team.id for team in reloaded.all()] == ["cao_delivery", "research"]
    assert reloaded.get("research").workspace_setup == DEFAULT_WORKSPACE_SETUP_ID


def test_team_store_deletes_persisted_team(tmp_path):
    # Given
    store = _team_store(
        tmp_path,
        WorkspaceTeam(
            id="delivery",
            display_name="Delivery",
            workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
        ),
    )

    # When
    store.delete("delivery")

    # Then
    assert store.list() == ()


def test_team_service_creates_team_with_default_member_role(tmp_path):
    # Given
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=WorkspaceTeamStore(tmp_path / "workspace-teams.json", bootstrap_teams=()),
        agent_registry=AgentRegistry({}),
        available_providers=("test",),
    )

    # When
    team = service.create_team(
        team_id="research",
        display_name="Research",
        workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
    )

    # Then
    assert sorted(team.roles) == ["member"]
    assert team.role_assignments == {}


def test_team_service_updates_metadata_without_erasing_roles_or_assignments(tmp_path):
    # Given
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(
            tmp_path,
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
                roles={"reviewer": WorkspaceTeamRole(display_name="Reviewer")},
                role_assignments={"agent_a": "reviewer"},
            ),
        ),
        agent_registry=AgentRegistry({}),
        available_providers=("test",),
    )

    # When
    team = service.update_team_metadata(
        team_id="delivery",
        display_name="Delivery Renamed",
        workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
    )

    # Then
    assert team.display_name == "Delivery Renamed"
    assert "reviewer" in team.roles
    assert team.role_assignments == {"agent_a": "reviewer"}


def test_team_service_deletes_empty_team_and_rejects_member_team_deletion(tmp_path):
    # Given
    agents_root = _write_agents(tmp_path, _agent("agent_a", "delivery"))
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(
            tmp_path,
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
            ),
            WorkspaceTeam(
                id="research",
                display_name="Research",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
            ),
        ),
        agent_registry=load_agent_registry(agents_root=agents_root),
        available_providers=("test",),
        agents_root=agents_root,
    )

    # When
    deleted = service.delete_team("research")

    # Then
    assert deleted.id == "research"
    assert [team.id for team in service.list_teams()] == ["delivery"]
    with pytest.raises(WorkspaceSetupConfigError, match="members exist"):
        service.delete_team("delivery")


def test_reused_default_root_team_service_rejects_delete_after_member_assignment(
    tmp_path, monkeypatch
):
    # Given
    agents_root = _write_agents(tmp_path, _agent("agent_a"))
    monkeypatch.setattr("cli_agent_orchestrator.agent.AGENTS_ROOT", agents_root)
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(
            tmp_path,
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
            ),
        ),
        agent_registry=load_agent_registry(),
        available_providers=("test",),
        agents_root=agents_root,
    )
    service.assign_member(team_id="delivery", agent_id="agent_a")

    # When / Then
    with pytest.raises(WorkspaceSetupConfigError, match="members exist"):
        service.delete_team("delivery")


def test_default_team_service_uses_injected_agents_root_for_member_writes(
    tmp_path, monkeypatch
):
    # Given
    explicit_root = _write_agents(tmp_path / "explicit", _agent("agent_a"))
    global_root = _write_agents(tmp_path / "global", _agent("agent_a"))
    monkeypatch.setattr("cli_agent_orchestrator.agent.AGENTS_ROOT", global_root)
    service = default_workspace_team_service(
        agent_registry=load_agent_registry(agents_root=explicit_root),
        agents_root=explicit_root,
        team_store_path=tmp_path / "workspace-teams.json",
    )

    # When
    service.assign_member(team_id=DEFAULT_WORKSPACE_TEAM_ID, agent_id="agent_a")

    # Then
    assert load_agent("agent_a", agents_root=explicit_root).workspace.team == (
        DEFAULT_WORKSPACE_TEAM_ID
    )
    assert load_agent("agent_a", agents_root=global_root).workspace.team is None


def test_team_service_put_role_mutates_one_role_without_resubmitting_policy(tmp_path):
    # Given
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(
            tmp_path,
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
                roles={
                    "reviewer": WorkspaceTeamRole(
                        display_name="Reviewer",
                        cao_tools=("read_inbox_message",),
                    )
                },
            ),
        ),
        agent_registry=AgentRegistry({}),
        available_providers=("test",),
    )

    # When
    team = service.put_role(
        team_id="delivery",
        role_id="operator",
        role=WorkspaceTeamRole(display_name="Operator", cao_tools=("send_message",)),
    )

    # Then
    assert sorted(team.roles) == ["member", "operator", "reviewer"]
    assert team.roles["reviewer"].cao_tools == ("read_inbox_message",)
    assert team.roles["operator"].cao_tools == ("send_message",)


def test_team_service_assigns_member_through_agent_config_and_role_assignment(tmp_path):
    # Given
    agents_root = _write_agents(tmp_path, _agent("agent_a"))
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(
            tmp_path,
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
                roles={"reviewer": WorkspaceTeamRole(display_name="Reviewer")},
            ),
        ),
        agent_registry=load_agent_registry(agents_root=agents_root),
        available_providers=("test",),
        agents_root=agents_root,
    )

    # When
    team = service.assign_member(team_id="delivery", agent_id="agent_a", role_id="reviewer")

    # Then
    assert load_agent("agent_a", agents_root=agents_root).workspace.team == "delivery"
    assert team.role_assignments == {"agent_a": "reviewer"}


def test_team_service_moves_member_and_clears_old_role_assignment(tmp_path):
    # Given
    agents_root = _write_agents(tmp_path, _agent("agent_a", "delivery"))
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(
            tmp_path,
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
                roles={"reviewer": WorkspaceTeamRole(display_name="Reviewer")},
                role_assignments={"agent_a": "reviewer"},
            ),
            WorkspaceTeam(
                id="research",
                display_name="Research",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
            ),
        ),
        agent_registry=load_agent_registry(agents_root=agents_root),
        available_providers=("test",),
        agents_root=agents_root,
    )

    # When
    target = service.assign_member(team_id="research", agent_id="agent_a")

    # Then
    assert load_agent("agent_a", agents_root=agents_root).workspace.team == "research"
    assert target.role_assignments == {"agent_a": "member"}
    assert service.get_team("delivery").role_assignments == {}


def test_team_service_removes_member_and_clears_team_role_assignment(tmp_path):
    # Given
    agents_root = _write_agents(tmp_path, _agent("agent_a", "delivery"))
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(
            tmp_path,
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
                roles={"reviewer": WorkspaceTeamRole(display_name="Reviewer")},
                role_assignments={"agent_a": "reviewer"},
            ),
        ),
        agent_registry=load_agent_registry(agents_root=agents_root),
        available_providers=("test",),
        agents_root=agents_root,
    )

    # When
    team = service.remove_member(team_id="delivery", agent_id="agent_a")

    # Then
    assert load_agent("agent_a", agents_root=agents_root).workspace.team is None
    assert team.role_assignments == {}


def test_role_assignment_alone_does_not_create_team_membership(tmp_path):
    # Given
    agents_root = _write_agents(tmp_path, _agent("agent_a"))
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(
            tmp_path,
            WorkspaceTeam(
                id="delivery",
                display_name="Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
                roles={"reviewer": WorkspaceTeamRole(display_name="Reviewer")},
            ),
        ),
        agent_registry=load_agent_registry(agents_root=agents_root),
        available_providers=("test",),
        agents_root=agents_root,
    )

    # When
    team = service.assign_role(team_id="delivery", agent_id="agent_a", role_id="reviewer")

    # Then
    assert load_agent("agent_a", agents_root=agents_root).workspace.team is None
    assert team.role_assignments == {"agent_a": "reviewer"}


def test_team_store_persists_roles_and_role_assignments(tmp_path):
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(tmp_path),
        agent_registry=AgentRegistry({}),
        available_providers=("test",),
    )

    service.create_or_update_team(
        team_id="delivery",
        display_name="Delivery",
        workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
        roles={
            "reviewer": WorkspaceTeamRole(
                display_name="Reviewer",
                cao_tools=("read_inbox_message",),
                mcp_servers={"custom": {"command": "custom-mcp"}},
                providers={"test": {"read": {"tools": ["test.read"]}}},
            )
        },
        role_assignments={"agent_a": "reviewer"},
    )
    reloaded = WorkspaceTeamRegistry(_team_store(tmp_path)).get("delivery")

    assert reloaded.roles["member"].cao_tools == ("send_message", "handoff")
    assert reloaded.roles["reviewer"].providers == {"test": {"read": {"tools": ["test.read"]}}}
    assert reloaded.roles["reviewer"].mcp_servers == {"custom": {"command": "custom-mcp"}}
    assert reloaded.role_assignments == {"agent_a": "reviewer"}


def test_team_role_assignment_and_deletion_semantics(tmp_path):
    team = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
        roles={
            "reviewer": WorkspaceTeamRole(
                display_name="Reviewer",
                cao_tools=("read_inbox_message",),
            )
        },
        role_assignments={"agent_a": "reviewer", "outsider": "reviewer"},
    )
    registry = AgentRegistry({"agent_a": _agent("agent_a", "delivery")})
    service = WorkspaceTeamService(
        setup_registry=_setup_registry(),
        team_store=_team_store(tmp_path, team),
        agent_registry=registry,
        available_providers=("test",),
    )

    service.delete_role_assignment(team_id="delivery", agent_id="outsider")
    without_assignment = WorkspaceTeamRegistry(_team_store(tmp_path)).get("delivery")
    assert without_assignment.role_assignments == {"agent_a": "reviewer"}
    assert without_assignment.role_for_member("missing") == (
        "member",
        without_assignment.roles["member"],
    )

    service.delete_role(team_id="delivery", role_id="reviewer")
    without_role = WorkspaceTeamRegistry(_team_store(tmp_path)).get("delivery")
    assert without_role.role_assignments == {"agent_a": "member"}
    assert "reviewer" not in without_role.roles

    with pytest.raises(WorkspaceSetupConfigError, match="member role cannot be deleted"):
        service.delete_role(team_id="delivery", role_id="member")


def test_team_store_rejects_non_string_persisted_team_fields(tmp_path):
    store_path = tmp_path / "workspace-teams.json"
    store_path.write_text(
        json.dumps(
            {
                "teams": [
                    {
                        "id": None,
                        "display_name": "Broken",
                        "workspace_setup": DEFAULT_WORKSPACE_SETUP_ID,
                    }
                ]
            }
        )
    )
    store = WorkspaceTeamStore(store_path)

    with pytest.raises(WorkspaceSetupConfigError, match="workspace team id"):
        store.list()


def test_team_authorizes_only_provider_candidates_for_team_members(tmp_path):
    registry = AgentRegistry(
        {
            "agent_a": _agent("agent_a", DEFAULT_WORKSPACE_TEAM_ID),
            "agent_b": _agent("agent_b"),
        }
    )
    manager = _manager(tmp_path, registry)

    view = manager.provider_view(DEFAULT_WORKSPACE_TEAM_ID, "test")

    assert view.value == {"provider-a": "agent_a"}
    assert [
        diagnostic.message
        for diagnostic in manager.diagnostics()
        if diagnostic.code == "pruned_provider_identity"
    ] == [
        "Workspace team cao_delivery pruned test app_user_id provider-b for "
        "out-of-team agent agent_b"
    ]


def test_manager_reports_unknown_team_setup_and_unavailable_provider(tmp_path):
    setup_registry = WorkspaceSetupRegistry(
        (
            WorkspaceSetup(
                id=DEFAULT_WORKSPACE_SETUP_ID,
                display_name="Linear Delivery Setup",
                providers=("missing",),
                resolver=_resolver,
            ),
        )
    )
    store = WorkspaceTeamStore(
        tmp_path / "teams.json",
        bootstrap_teams=(
            WorkspaceTeam(
                id=DEFAULT_WORKSPACE_TEAM_ID,
                display_name="CAO Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
            ),
            WorkspaceTeam(
                id="broken",
                display_name="Broken",
                workspace_setup="future_setup",
            ),
        ),
    )
    manager = WorkspaceCollaborationManager(
        setup_registry=setup_registry,
        team_registry=WorkspaceTeamRegistry(store),
        agent_registry=AgentRegistry({"agent_a": _agent("agent_a", "unknown_team")}),
        provider_adapters={},
        available_providers=(),
    )

    diagnostics = manager.diagnostics()

    assert sorted(diagnostic.code for diagnostic in diagnostics) == [
        "unavailable_provider",
        "unknown_setup",
        "unknown_team",
    ]


def test_setup_rejects_multiple_resolvers():
    with pytest.raises(WorkspaceSetupConfigError, match="exactly one resolver"):
        WorkspaceSetup(
            id=DEFAULT_WORKSPACE_SETUP_ID,
            display_name="Linear Delivery Setup",
            providers=("test",),
            resolver=(_resolver, _resolver),  # type: ignore[arg-type]
        )


def test_agents_without_team_do_not_resolve_provider_events(tmp_path):
    manager = _manager(tmp_path, AgentRegistry({"agent_a": _agent("agent_a")}))

    assert manager.resolve_event_context(_agent("agent_a"), Event("provider-a")) is None


def test_collaboration_requires_same_non_empty_team_even_when_setup_is_shared(tmp_path):
    delivery = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
    )
    research = WorkspaceTeam(
        id="research",
        display_name="Research",
        workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
    )
    manager = _manager(tmp_path, AgentRegistry({}), delivery, research)
    sender = _agent("agent_a", "delivery")

    manager.require_same_team_collaboration(sender=sender, receiver=_agent("agent_b", "delivery"))

    with pytest.raises(WorkspaceSetupConfigError, match="sender agent_a team delivery"):
        manager.require_same_team_collaboration(
            sender=sender,
            receiver=_agent("agent_b", "research"),
        )
    with pytest.raises(WorkspaceSetupConfigError, match="receiver agent_b team none"):
        manager.require_same_team_collaboration(sender=sender, receiver=_agent("agent_b"))


def test_ambiguous_provider_events_fail_closed_across_teams(tmp_path):
    delivery = WorkspaceTeam(
        id="delivery",
        display_name="Delivery",
        workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
    )
    research = WorkspaceTeam(
        id="research",
        display_name="Research",
        workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
    )
    registry = AgentRegistry(
        {
            "agent_a": _agent("agent_a", "delivery"),
            "agent_b": _agent("agent_b", "research"),
        }
    )
    store = _team_store(tmp_path, delivery, research)
    manager = WorkspaceCollaborationManager(
        setup_registry=_setup_registry(),
        team_registry=WorkspaceTeamRegistry(store),
        agent_registry=registry,
        provider_adapters={"test": DuplicateIdentityProviderAdapter()},
    )

    with pytest.raises(WorkspaceSetupConfigError, match="multiple workspace teams"):
        manager.resolve_provider_event("test", Event("shared-provider-user"))

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig
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
    WorkspaceTeamService,
    WorkspaceTeamStore,
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

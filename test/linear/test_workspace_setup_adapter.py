from __future__ import annotations

import pytest

from cli_agent_orchestrator.agent import (
    Agent,
    AgentRegistry,
    AgentWorkspaceConfig,
    LinearConfig,
    LinearToolAccessConfig,
)
from cli_agent_orchestrator.linear.workspace_events import LinearIssueContextEvent
from cli_agent_orchestrator.linear.workspace_setup_adapter import LinearWorkspaceSetupAdapter
from cli_agent_orchestrator.workspace_contexts import WorkspaceContextResolution
from cli_agent_orchestrator.workspace_setups import (
    DEFAULT_WORKSPACE_SETUP_ID,
    WorkspaceSetup,
    WorkspaceSetupConfigError,
    WorkspaceCollaborationManager,
    WorkspaceSetupRegistry,
    WorkspaceTeam,
    WorkspaceTeamRegistry,
    WorkspaceTeamStore,
)


def _agent(agent_id: str, *, team: str | None, app_key: str, app_user_id: str) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(team=team),
        linear=LinearConfig(
            app_key=app_key,
            app_user_id=app_user_id,
            app_user_name=f"{agent_id} Linear",
            tool_access=(
                LinearToolAccessConfig(
                    access_id=f"{agent_id}_access",
                    tools=("cao_linear.get_issue",),
                    issues=("CAO-1",),
                ),
            ),
        ),
    )


def _resolver(_event):
    return WorkspaceContextResolution(
        workspace_context_id="wctx",
        resolver_id="linear_planning",
        boundary_provider_id="linear",
        boundary_object_type="issue",
        boundary_object_id="CAO-1",
    )


def _manager(tmp_path) -> WorkspaceCollaborationManager:
    registry = AgentRegistry(
        {
            "agent_a": _agent(
                "agent_a",
                team="cao_delivery",
                app_key="agent-a",
                app_user_id="linear-user-a",
            ),
            "agent_b": _agent(
                "agent_b",
                team=None,
                app_key="agent-b",
                app_user_id="linear-user-b",
            ),
        }
    )
    store = WorkspaceTeamStore(
        tmp_path / "teams.json",
        bootstrap_teams=(
            WorkspaceTeam(
                id="cao_delivery",
                display_name="CAO Delivery",
                workspace_setup=DEFAULT_WORKSPACE_SETUP_ID,
            ),
        ),
    )
    return WorkspaceCollaborationManager(
        setup_registry=WorkspaceSetupRegistry(
            (
                WorkspaceSetup(
                    id=DEFAULT_WORKSPACE_SETUP_ID,
                    display_name="Linear Delivery Setup",
                    providers=("linear",),
                    resolver=_resolver,
                ),
            )
        ),
        team_registry=WorkspaceTeamRegistry(store),
        agent_registry=registry,
        provider_adapters={"linear": LinearWorkspaceSetupAdapter()},
    )


def _event(**overrides: str | None) -> LinearIssueContextEvent:
    values = {
        "event_type": "AgentSessionEvent",
        "action": "prompted",
        "app_key": "agent-a",
        "app_user_id": "linear-user-a",
        "app_user_name": "agent_a Linear",
        "issue_id": "issue-1",
        "issue_identifier": "CAO-1",
        "agent_session_id": "session-1",
        "thread_id": "session-1",
        "message_id": "activity-1",
        "message_body": "Can you inspect this?",
    }
    values.update(overrides)
    return LinearIssueContextEvent(**values)


def test_linear_provider_view_prunes_out_of_team_presence_and_tool_access(tmp_path):
    manager = _manager(tmp_path)

    view = manager.provider_view("cao_delivery", "linear")
    config = view.value

    assert config.presence_by_app_key("agent-a").agent_id == "agent_a"
    assert config.presence_by_app_user_id("linear-user-a").agent_id == "agent_a"
    assert config.presence_by_app_user_name("agent_a Linear").agent_id == "agent_a"
    assert config.presence_by_app_key("agent-b") is None
    assert config.presence_by_app_user_id("linear-user-b") is None
    assert config.presence_by_app_user_name("agent_b Linear") is None
    assert [access.agent_id for access in config.tool_access.values()] == ["agent_a"]


def test_linear_event_for_out_of_team_identity_is_not_cao_addressable(tmp_path):
    manager = _manager(tmp_path)

    with pytest.raises(WorkspaceSetupConfigError, match="not CAO-addressable"):
        manager.resolve_provider_event(
            "linear",
            _event(
                app_key="agent-b",
                app_user_id="linear-user-b",
                app_user_name="agent_b Linear",
            ),
        )

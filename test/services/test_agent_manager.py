from __future__ import annotations

from datetime import datetime

import pytest

from cli_agent_orchestrator.agent import Agent, AgentConfigError, AgentRegistry
from cli_agent_orchestrator.services.agent_manager import AgentManager


def _agent(agent_id: str = "agent_a", **overrides: object) -> Agent:
    values = {
        "id": agent_id,
        "display_name": "Agent A",
        "cli_provider": "codex",
        "workdir": "/repo",
        "session_name": "agent-a",
        "prompt": "# Agent\n",
    }
    values.update(overrides)
    return Agent(**values)


def _manager(*agents: Agent, terminals=None) -> AgentManager:
    return AgentManager(
        configured_agents=AgentRegistry({agent.id: agent for agent in agents}),
        terminal_lister=lambda: list(terminals or []),
        terminal_metadata_resolver=lambda terminal_id: {
            "id": terminal_id,
            "agent_identity_id": agents[0].id if agents else None,
        },
    )


def test_configured_agents_list_and_resolve_through_manager():
    agent = _agent()
    manager = _manager(agent)

    status = manager.status_for_agent(agent.id)

    assert [item.agent_id for item in manager.list_statuses()] == ["agent_a"]
    assert status.agent == agent
    assert status.workdir == "/repo"
    assert status.session_name == "agent-a"


def test_agent_manager_reports_active_terminal_from_current_schema():
    agent = _agent()
    manager = _manager(
        agent,
        terminals=[
            {
                "id": "terminal-1",
                "agent_identity_id": agent.id,
                "workspace_context_id": "ctx-1",
                "last_active": datetime(2026, 5, 13, 12, 0, 0),
            }
        ],
    )

    status = manager.status_for_agent(agent.id)

    assert status.active is True
    assert status.active_terminal_id == "terminal-1"
    assert status.active_workspace_context_id == "ctx-1"


def test_agent_manager_unknown_agent_fails_closed():
    manager = _manager(_agent())

    with pytest.raises(AgentConfigError, match="Unknown CAO agent"):
        manager.status_for_agent("missing")

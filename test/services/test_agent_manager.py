from __future__ import annotations

from datetime import datetime

import pytest

from cli_agent_orchestrator.agent import (
    Agent,
    AgentConfigError,
    AgentPathError,
    AgentRegistry,
)
from cli_agent_orchestrator.services.agent_manager import AgentManager


def _agent(agent_id: str = "agent_a", **overrides: str) -> Agent:
    values = {
        "id": agent_id,
        "display_name": agent_id.replace("_", " ").title(),
        "cli_provider": "codex",
        "workdir": "/repo",
        "session_name": agent_id.replace("_", "-"),
        "prompt": "",
    }
    values.update(overrides)
    return Agent(**values)


def _manager(
    *,
    agents: dict[str, Agent] | None = None,
    terminals=None,
) -> AgentManager:
    return AgentManager(
        configured_agents=AgentRegistry(agents or {}),
        terminal_lister=lambda: list(terminals or []),
        terminal_metadata_resolver=lambda terminal_id: {
            terminal["id"]: terminal for terminal in terminals or []
        }.get(terminal_id),
    )


def test_configured_agents_register_list_and_resolve_through_manager():
    agent = _agent()
    manager = _manager(agents={agent.id: agent})

    assert manager.resolve_agent("agent_a") == agent
    assert [status.agent_id for status in manager.list_statuses()] == ["agent_a"]
    assert manager.status_for_agent("agent_a").active is False


def test_invalid_agent_registration_is_rejected_at_manager_boundary():
    manager = _manager()

    with pytest.raises(AgentConfigError, match="supported provider"):
        manager.register_agent(_agent(cli_provider="not-a-provider"))

    with pytest.raises(AgentPathError, match="agent id"):
        _agent("")


def test_registered_agent_enters_manager_registration_boundary():
    agent = _agent("registered_agent")
    manager = _manager()
    manager.register_agent(agent)

    assert manager.resolve_agent("registered_agent") == agent
    assert manager.list_agents() == (agent,)


def test_require_registered_agent_rejects_raw_mismatch_before_terminal_boundary():
    configured = _agent("agent_a", workdir="/configured")
    raw = _agent("agent_a", workdir="/raw")
    manager = _manager(agents={configured.id: configured})

    with pytest.raises(AgentConfigError, match="does not match"):
        manager.require_registered_agent(raw)


def test_active_and_inactive_status_derive_from_terminal_rows():
    active_agent = _agent("agent_a")
    inactive_agent = _agent("agent_b")
    last_active = datetime(2026, 5, 13, 12, 0, 0)
    manager = _manager(
        agents={
            active_agent.id: active_agent,
            inactive_agent.id: inactive_agent,
        },
        terminals=[
            {
                "id": "terminal-a",
                "agent_id": "agent_a",
                "workspace_context_id": "wctx-a",
                "last_active": last_active,
            }
        ],
    )

    active = manager.status_for_agent("agent_a")
    inactive = manager.status_for_agent("agent_b")

    assert active.active is True
    assert active.active_terminal_id == "terminal-a"
    assert active.active_workspace_context_id == "wctx-a"
    assert active.last_active_at == last_active
    assert inactive.active is False
    assert inactive.active_terminal_id is None
    assert [status.agent_id for status in manager.list_statuses(active=True)] == [
        "agent_a"
    ]


def test_orphaned_terminal_references_are_diagnostic_not_valid_agents():
    manager = _manager(
        agents={"agent_a": _agent("agent_a")},
        terminals=[
            {
                "id": "terminal-a",
                "agent_id": "agent_a",
                "workspace_context_id": "wctx-a",
            },
            {
                "id": "terminal-orphan",
                "agent_id": "missing",
                "workspace_context_id": "wctx-orphan",
            },
        ],
    )

    assert [status.agent_id for status in manager.list_statuses(active=True)] == [
        "agent_a"
    ]
    orphan = manager.orphaned_terminal_references()[0]
    assert orphan.terminal_id == "terminal-orphan"
    assert orphan.agent_id == "missing"


def test_terminal_agent_resolution_fails_for_unknown_mapping():
    manager = _manager(
        terminals=[
            {
                "id": "terminal-orphan",
                "agent_id": "missing",
                "workspace_context_id": "wctx-orphan",
            }
        ],
    )

    with pytest.raises(AgentConfigError, match="references unknown"):
        manager.agent_for_terminal("terminal-orphan")

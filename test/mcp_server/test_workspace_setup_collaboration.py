from __future__ import annotations

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig
from cli_agent_orchestrator.mcp_server import server


def _agent(agent_id: str, setup: str | None) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(setup=setup),
    )


def test_assign_allows_same_setup_collaboration(monkeypatch):
    sender = _agent("sender", "cao_delivery")
    receiver = _agent("receiver", "cao_delivery")
    sent = {}

    monkeypatch.setenv("CAO_TERMINAL_ID", "terminal-sender")
    monkeypatch.setattr(
        server.db_module,
        "get_terminal_metadata",
        lambda terminal_id: {"id": terminal_id, "agent_id": sender.id},
    )
    monkeypatch.setattr(
        server,
        "load_agent_registry",
        lambda: AgentRegistry({sender.id: sender, receiver.id: receiver}),
    )
    monkeypatch.setattr(server, "_create_terminal", lambda agent_id, working_directory: ("t1", "codex"))
    monkeypatch.setattr(
        server,
        "_deliver_assign_payload",
        lambda terminal_id, message: sent.update({"terminal_id": terminal_id, "message": message}),
    )

    result = server._assign_impl("receiver", "please help")

    assert result["success"] is True
    assert sent == {"terminal_id": "t1", "message": "please help"}


def test_assign_rejects_different_or_missing_setup_before_terminal_creation(monkeypatch):
    sender = _agent("sender", "cao_delivery")
    receiver = _agent("receiver", "other_setup")
    create_terminal_calls = []

    monkeypatch.setenv("CAO_TERMINAL_ID", "terminal-sender")
    monkeypatch.setattr(
        server.db_module,
        "get_terminal_metadata",
        lambda terminal_id: {"id": terminal_id, "agent_id": sender.id},
    )
    monkeypatch.setattr(
        server,
        "load_agent_registry",
        lambda: AgentRegistry({sender.id: sender, receiver.id: receiver}),
    )
    monkeypatch.setattr(
        server,
        "_create_terminal",
        lambda agent_id, working_directory: create_terminal_calls.append(agent_id),
    )

    result = server._assign_impl("receiver", "please help")

    assert result["success"] is False
    assert "sender sender setup cao_delivery" in result["message"]
    assert "receiver receiver setup other_setup" in result["message"]
    assert create_terminal_calls == []

    missing_setup = _agent("missing_setup", None)
    monkeypatch.setattr(
        server,
        "load_agent_registry",
        lambda: AgentRegistry({sender.id: sender, missing_setup.id: missing_setup}),
    )

    result = server._assign_impl("missing_setup", "please help")

    assert result["success"] is False
    assert "receiver missing_setup setup none" in result["message"]
    assert create_terminal_calls == []


def test_baton_create_rejects_different_setup_before_service_call(monkeypatch):
    sender = _agent("sender", "cao_delivery")
    receiver = _agent("receiver", "other_setup")
    service_calls = []

    monkeypatch.setenv("CAO_TERMINAL_ID", "terminal-sender")
    monkeypatch.setattr(
        server.db_module,
        "get_terminal_metadata",
        lambda terminal_id: {
            "terminal-sender": {"id": terminal_id, "agent_id": sender.id},
            "terminal-receiver": {"id": terminal_id, "agent_id": receiver.id},
        }.get(terminal_id),
    )
    monkeypatch.setattr(
        server,
        "load_agent_registry",
        lambda: AgentRegistry({sender.id: sender, receiver.id: receiver}),
    )
    monkeypatch.setattr(
        server.baton_service,
        "create_baton",
        lambda **kwargs: service_calls.append(kwargs),
    )

    result = server._create_baton_impl("T01", "terminal-receiver", "please help")

    assert result["success"] is False
    assert "sender sender setup cao_delivery" in result["error"]
    assert "receiver receiver setup other_setup" in result["error"]
    assert service_calls == []


def test_baton_pass_rejects_missing_setup_before_service_call(monkeypatch):
    sender = _agent("sender", "cao_delivery")
    receiver = _agent("receiver", None)
    service_calls = []

    monkeypatch.setenv("CAO_TERMINAL_ID", "terminal-sender")
    monkeypatch.setattr(
        server.db_module,
        "get_terminal_metadata",
        lambda terminal_id: {
            "terminal-sender": {"id": terminal_id, "agent_id": sender.id},
            "terminal-receiver": {"id": terminal_id, "agent_id": receiver.id},
        }.get(terminal_id),
    )
    monkeypatch.setattr(
        server,
        "load_agent_registry",
        lambda: AgentRegistry({sender.id: sender, receiver.id: receiver}),
    )
    monkeypatch.setattr(
        server.baton_service,
        "pass_baton",
        lambda **kwargs: service_calls.append(kwargs),
    )

    result = server._pass_baton_impl("baton-1", "terminal-receiver", "please help")

    assert result["success"] is False
    assert "receiver receiver setup none" in result["error"]
    assert service_calls == []

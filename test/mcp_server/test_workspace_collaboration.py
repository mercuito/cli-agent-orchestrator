from __future__ import annotations

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig
from cli_agent_orchestrator.mcp_server import server


def _agent(agent_id: str, team: str | None) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(team=team),
    )


def test_assign_allows_same_team_collaboration(monkeypatch):
    sender = _agent("sender", "cao_delivery")
    receiver = _agent("receiver", "cao_delivery")
    sent = {}

    monkeypatch.setenv("CAO_AGENT_ID", sender.id)
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
        server, "_create_terminal", lambda agent_id, working_directory: ("t1", "codex")
    )
    monkeypatch.setattr(
        server,
        "_deliver_assign_payload",
        lambda terminal_id, message: sent.update({"terminal_id": terminal_id, "message": message}),
    )

    result = server._assign_impl("receiver", "please help")

    assert result["success"] is True
    assert sent == {"terminal_id": "t1", "message": "please help"}


def test_assign_delivery_does_not_promise_hidden_send_message(monkeypatch):
    sent = {}

    monkeypatch.setenv("CAO_AGENT_ID", "sender")
    monkeypatch.setattr(server, "ENABLE_SENDER_ID_INJECTION", True)
    monkeypatch.setattr(server, "_terminal_can_invoke_builtin", lambda terminal_id, tool: False)
    monkeypatch.setattr(
        server.db_module,
        "get_terminal_metadata",
        lambda terminal_id: {"id": terminal_id, "agent_id": "receiver"},
    )
    monkeypatch.setattr(
        server,
        "_send_to_inbox",
        lambda receiver_agent_id, message: sent.update(
            {"receiver_agent_id": receiver_agent_id, "message": message}
        ),
    )

    server._deliver_assign_payload("worker-terminal", "please help")

    assert sent == {
        "receiver_agent_id": "receiver",
        "message": "please help\n\n[Assigned by agent sender.]",
    }
    assert "send_message" not in sent["message"]


def test_assign_rejects_different_or_missing_team_before_terminal_creation(monkeypatch):
    sender = _agent("sender", "cao_delivery")
    receiver = _agent("receiver", "other_team")
    create_terminal_calls = []

    monkeypatch.setenv("CAO_AGENT_ID", sender.id)
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
    assert "sender sender team cao_delivery" in result["message"]
    assert "receiver receiver team other_team" in result["message"]
    assert create_terminal_calls == []

    missing_team = _agent("missing_team", None)
    monkeypatch.setattr(
        server,
        "load_agent_registry",
        lambda: AgentRegistry({sender.id: sender, missing_team.id: missing_team}),
    )

    result = server._assign_impl("missing_team", "please help")

    assert result["success"] is False
    assert "receiver missing_team team none" in result["message"]
    assert create_terminal_calls == []


def test_baton_create_rejects_different_team_before_service_call(monkeypatch):
    sender = _agent("sender", "cao_delivery")
    receiver = _agent("receiver", "other_team")
    service_calls = []

    monkeypatch.setenv("CAO_AGENT_ID", sender.id)
    monkeypatch.setattr(
        server.db_module,
        "list_terminals_by_agent",
        lambda agent_id: [{"id": "terminal-sender", "agent_id": sender.id}]
        if agent_id == sender.id
        else [],
    )
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

    result = server._create_baton_impl("T01", "receiver", "please help")

    assert result["success"] is False
    assert "sender sender team cao_delivery" in result["error"]
    assert "receiver receiver team other_team" in result["error"]
    assert service_calls == []


def test_baton_pass_rejects_missing_team_before_service_call(monkeypatch):
    sender = _agent("sender", "cao_delivery")
    receiver = _agent("receiver", None)
    service_calls = []

    monkeypatch.setenv("CAO_AGENT_ID", sender.id)
    monkeypatch.setattr(
        server.db_module,
        "list_terminals_by_agent",
        lambda agent_id: [{"id": "terminal-sender", "agent_id": sender.id}]
        if agent_id == sender.id
        else [],
    )
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

    result = server._pass_baton_impl("baton-1", "receiver", "please help")

    assert result["success"] is False
    assert "receiver receiver team none" in result["error"]
    assert service_calls == []

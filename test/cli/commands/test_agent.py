from __future__ import annotations

from datetime import datetime

from click.testing import CliRunner

from cli_agent_orchestrator.agent import Agent, load_agent, validate_agent_dir, write_agent
from cli_agent_orchestrator.cli.commands.agent import agent_command
from cli_agent_orchestrator.services.agent_manager import AgentStatus


def _agent(agent_id: str = "developer") -> Agent:
    return Agent(
        id=agent_id,
        display_name="Developer",
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id,
        prompt="# Agent\n",
        model="gpt-5.2",
        mcp_servers={"cao": {"command": "cao-mcp-server"}},
        tools=("bash",),
        cao_tools=("send_message",),
    )


class _Manager:
    def __init__(self, statuses: tuple[AgentStatus, ...]) -> None:
        self._statuses = statuses

    def list_statuses(self):
        return self._statuses

    def status_for_agent(self, agent_id: str) -> AgentStatus:
        for status in self._statuses:
            if status.agent_id == agent_id:
                return status
        raise AssertionError(f"unexpected agent id: {agent_id}")


def _status(agent: Agent, *, active: bool = False) -> AgentStatus:
    return AgentStatus(
        agent_id=agent.id,
        display_name=agent.display_name,
        cli_provider=agent.cli_provider,
        workdir=agent.workdir,
        session_name=agent.session_name,
        agent=agent,
        active=active,
        active_terminal_id="term-live" if active else None,
        active_workspace_context_id="wctx-live" if active else None,
        last_active_at=datetime(2026, 5, 16, 12, 0, 0) if active else None,
    )


def _patch_agents_root(monkeypatch, agents_root):
    monkeypatch.setattr("cli_agent_orchestrator.agent.AGENTS_ROOT", agents_root)
    monkeypatch.setattr("cli_agent_orchestrator.cli.commands.agent.AGENTS_ROOT", agents_root)


def test_agent_list_prints_current_instance_status(tmp_path, monkeypatch):
    agent = _agent()
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager((_status(agent, active=True),)),
    )

    result = CliRunner().invoke(agent_command, ["list"])

    assert result.exit_code == 0
    assert "developer\tcodex\trunning term-live" in result.output


def test_agent_show_prints_agent_toml_and_status(tmp_path, monkeypatch):
    _patch_agents_root(monkeypatch, tmp_path)
    agent = _agent()
    write_agent(agent, agents_root=tmp_path)
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager((_status(agent),)),
    )

    result = CliRunner().invoke(agent_command, ["show", "developer"])

    assert result.exit_code == 0
    assert "status: stopped" in result.output
    assert "agent.toml:" in result.output
    assert 'workdir = "/repo"' in result.output
    assert 'session_name = "developer"' in result.output
    assert 'model = "gpt-5.2"' in result.output
    assert "[mcp_servers.cao]" in result.output
    assert 'cao_tools = ["send_message"]' in result.output
    assert "prompt.md:" in result.output


def test_agent_create_writes_valid_stub_agent(tmp_path, monkeypatch):
    _patch_agents_root(monkeypatch, tmp_path)

    result = CliRunner().invoke(
        agent_command,
        ["create", "new_agent", "--provider", "codex", "--workdir", "/repo"],
    )

    assert result.exit_code == 0
    agent = load_agent("new_agent", agents_root=tmp_path)
    assert agent.prompt == "# Agent\n"
    assert validate_agent_dir(tmp_path / "new_agent") == []


def test_agent_delete_refuses_running_agent(tmp_path, monkeypatch):
    _patch_agents_root(monkeypatch, tmp_path)
    agent = _agent()
    write_agent(agent, agents_root=tmp_path)
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager((_status(agent, active=True),)),
    )

    result = CliRunner().invoke(agent_command, ["delete", "developer", "--confirm"])

    assert result.exit_code != 0
    assert "agent is running in terminal term-live" in result.output
    assert (tmp_path / "developer" / "agent.toml").exists()


def test_agent_delete_removes_stopped_agent(tmp_path, monkeypatch):
    _patch_agents_root(monkeypatch, tmp_path)
    agent = _agent()
    write_agent(agent, agents_root=tmp_path)
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager((_status(agent),)),
    )

    result = CliRunner().invoke(agent_command, ["delete", "developer", "--confirm"])

    assert result.exit_code == 0
    assert not (tmp_path / "developer").exists()


def test_agent_start_rejects_second_live_instance(monkeypatch):
    agent = _agent()
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager((_status(agent, active=True),)),
    )

    result = CliRunner().invoke(agent_command, ["start", "developer"])

    assert result.exit_code != 0
    assert "agent already running in terminal term-live" in result.output


def test_agent_start_opens_runtime_terminal(tmp_path, monkeypatch):
    _patch_agents_root(monkeypatch, tmp_path)
    agent = _agent()
    write_agent(agent, agents_root=tmp_path)
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager((_status(agent),)),
    )

    class _Handle:
        def __init__(self, loaded_agent: Agent) -> None:
            assert loaded_agent.id == "developer"

        def ensure_started(self):
            return type("Terminal", (), {"id": "term-new", "session_name": "developer"})()

    monkeypatch.setattr("cli_agent_orchestrator.cli.commands.agent.AgentRuntimeHandle", _Handle)

    result = CliRunner().invoke(agent_command, ["start", "developer"])

    assert result.exit_code == 0
    assert "started developer in terminal term-new" in result.output


def test_agent_stop_deletes_live_terminal(monkeypatch):
    agent = _agent()
    deleted: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager((_status(agent, active=True),)),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.terminal_service.delete_terminal",
        lambda terminal_id, require_window_killed=False: deleted.append(
            (terminal_id, require_window_killed)
        ),
    )

    result = CliRunner().invoke(agent_command, ["stop", "developer"])

    assert result.exit_code == 0
    assert deleted == [("term-live", True)]
    assert "stopped developer" in result.output

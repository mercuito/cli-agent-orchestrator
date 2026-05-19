from __future__ import annotations

import os
from dataclasses import replace
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


def test_agent_list_prints_current_instance_status(tmp_path, monkeypatch):
    developer = _agent("developer")
    discovery = _agent("discovery_partner")
    reviewer = _agent("reviewer")
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager(
            (
                _status(developer, active=True),
                _status(discovery),
                _status(reviewer),
            )
        ),
    )

    result = CliRunner().invoke(agent_command, ["list"])

    assert result.exit_code == 0
    assert "developer\tcodex\trunning\tteam=none\tsetup=default term-live" in result.output
    assert "discovery_partner\tcodex\tstopped\tteam=none\tsetup=default" in result.output
    assert "reviewer\tcodex\tstopped\tteam=none\tsetup=default" in result.output


def test_agent_help_covers_each_subcommand():
    runner = CliRunner()

    group_help = runner.invoke(agent_command, ["--help"])
    assert group_help.exit_code == 0
    for subcommand in ("list", "show", "create", "edit", "delete", "start", "stop"):
        assert subcommand in group_help.output

        command_help = runner.invoke(agent_command, [subcommand, "--help"])
        assert command_help.exit_code == 0
        assert f"Usage: agent {subcommand}" in command_help.output


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
    assert "effective_tool_access:" in result.output
    assert 'allowed_tools: ["send_message"]' in result.output
    assert '"cao-mcp-server"' in result.output
    assert "agent.toml:" in result.output
    assert 'workdir = "/repo"' in result.output
    assert 'session_name = "developer"' in result.output
    assert 'model = "gpt-5.2"' in result.output
    assert "[mcp_servers.cao]" in result.output
    assert 'cao_tools = ["send_message"]' in result.output
    assert "prompt.md:" in result.output


def test_agent_show_uses_available_builtin_tool_candidates(tmp_path, monkeypatch):
    _patch_agents_root(monkeypatch, tmp_path)
    monkeypatch.setenv("CAO_BATON_ENABLED", "false")
    agent = replace(_agent(), cao_tools=None)
    write_agent(agent, agents_root=tmp_path)
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager((_status(agent),)),
    )

    result = CliRunner().invoke(agent_command, ["show", "developer"])

    assert result.exit_code == 0
    allowed_line = next(
        line for line in result.output.splitlines() if line.startswith("allowed_tools:")
    )
    assert "send_message" in allowed_line
    assert "create_baton" not in allowed_line


def test_agent_create_writes_valid_stub_agent(tmp_path, monkeypatch):
    _patch_agents_root(monkeypatch, tmp_path)

    result = CliRunner().invoke(
        agent_command,
        ["create", "foo", "--provider", "codex", "--workdir", "/repo"],
    )

    assert result.exit_code == 0
    agent = load_agent("foo", agents_root=tmp_path)
    assert agent.prompt == "# Agent\n"
    assert validate_agent_dir(tmp_path / "foo") == []


def test_agent_edit_opens_editor_and_validates_saved_config(tmp_path, monkeypatch):
    _patch_agents_root(monkeypatch, tmp_path)
    agent = _agent()
    write_agent(agent, agents_root=tmp_path)
    editor = tmp_path / "editor.sh"
    editor.write_text("#!/bin/sh\nprintf '\\n# edited by test\\n' >> \"$1\"\n")
    os.chmod(editor, 0o755)
    monkeypatch.setenv("EDITOR", str(editor))

    result = CliRunner().invoke(agent_command, ["edit", "developer"])

    assert result.exit_code == 0
    assert "validated developer" in result.output
    assert "# edited by test" in (tmp_path / "developer" / "agent.toml").read_text()


def test_agent_edit_rejects_invalid_saved_config(tmp_path, monkeypatch):
    _patch_agents_root(monkeypatch, tmp_path)
    agent = _agent()
    write_agent(agent, agents_root=tmp_path)
    config_path = tmp_path / "developer" / "agent.toml"
    original_config = config_path.read_text()
    editor = tmp_path / "editor.sh"
    editor.write_text("#!/bin/sh\nprintf 'not valid toml = [' > \"$1\"\n")
    os.chmod(editor, 0o755)
    monkeypatch.setenv("EDITOR", str(editor))

    result = CliRunner().invoke(agent_command, ["edit", "developer"])

    assert result.exit_code != 0
    assert "Error:" in result.output
    assert "agent.toml" in result.output
    assert config_path.read_text() == original_config
    assert validate_agent_dir(config_path.parent) == []


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
    agent = _agent("discovery_partner")
    write_agent(agent, agents_root=tmp_path)
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.default_agent_manager",
        lambda: _Manager((_status(agent),)),
    )

    class _Handle:
        def __init__(self, loaded_agent: Agent) -> None:
            assert loaded_agent.id == "discovery_partner"

        def ensure_started(self):
            return type(
                "Terminal",
                (),
                {"id": "term-new", "session_name": "discovery_partner"},
            )()

    monkeypatch.setattr("cli_agent_orchestrator.cli.commands.agent.AgentRuntimeHandle", _Handle)
    attach_calls = []
    monkeypatch.setattr("cli_agent_orchestrator.cli.commands.agent.os.isatty", lambda fd: True)
    monkeypatch.setattr(
        "cli_agent_orchestrator.cli.commands.agent.subprocess.run",
        lambda args, check: attach_calls.append((args, check)),
    )

    result = CliRunner().invoke(agent_command, ["start", "discovery_partner"])

    assert result.exit_code == 0
    assert "started discovery_partner in terminal term-new" in result.output
    assert attach_calls == [(["tmux", "attach-session", "-t", "discovery_partner"], False)]


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

"""Tests for durable CAO agent directories."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from cli_agent_orchestrator.agent import (
    AGENT_CONFIG_MODE,
    AGENT_PROMPT_MODE,
    Agent,
    AgentConfigError,
    AgentValidationError,
    AgentWorkspaceConfig,
    load_agent,
    load_agent_registry,
    patch_agent_config,
    validate_agents_root,
    write_agent,
)


def _agent(**overrides: object) -> Agent:
    values = {
        "id": "implementation_partner",
        "display_name": "Implementation Partner",
        "cli_provider": "claude_code",
        "workdir": "/repo",
        "session_name": "implementation-partner",
        "prompt": "# Agent\n\nHelp with implementation.\n",
        "description": "Developer Agent in a multi-agent system",
        "model": "claude-opus-4-7",
        "reasoning_effort": "medium",
        "mcp_servers": {"cao-mcp-server": {"command": "cao-mcp-server"}},
        "tools": ("bash",),
        "tool_aliases": {"shell": "bash"},
        "tools_settings": {"bash": {"timeout": 120}},
        "cao_tools": ("send_message",),
        "skills": ("coding-discipline",),
        "tags": ("implementation",),
        "resources": ("file:///repo/README.md",),
        "hooks": {"pre": {"command": "true"}},
        "use_legacy_mcp_json": False,
        "runtime_capabilities": ("@builtin",),
        "workspace": AgentWorkspaceConfig(team="cao_delivery"),
    }
    values.update(overrides)
    return Agent(**values)


def test_agents_root_honors_cao_agents_dir_env_at_import(tmp_path):
    """CAO_AGENTS_DIR configures durable agent storage at process startup."""
    agents_root = tmp_path / "env-agents"
    env = {
        **os.environ,
        "CAO_AGENTS_DIR": str(agents_root),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from cli_agent_orchestrator.agent import AGENTS_ROOT; print(AGENTS_ROOT)",
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.stdout.strip() == str(agents_root)


def test_agent_model_rejects_invalid_workspace():
    with pytest.raises(AgentConfigError, match="workspace.team"):
        _agent(workspace=AgentWorkspaceConfig(team=""))


def test_agent_model_rejects_unsupported_cli_provider():
    with pytest.raises(AgentConfigError, match="not a supported provider"):
        _agent(cli_provider="bogus", reasoning_effort=None)


def test_agent_model_accepts_reasoning_effort_without_static_provider_declarations():
    """Model and effort options are catalog-discovered, not Agent-level statics."""
    agent = _agent(cli_provider="q_cli", model=None, reasoning_effort="ultra")

    assert agent.reasoning_effort == "ultra"


def test_agent_model_has_frozen_value_semantics():
    agent = _agent(mcp_servers={"cao-mcp-server": {"command": "cao-mcp-server", "args": []}})
    equal_agent = _agent(mcp_servers={"cao-mcp-server": {"command": "cao-mcp-server", "args": []}})

    with pytest.raises(FrozenInstanceError):
        agent.display_name = "Mutated"  # type: ignore[misc]
    with pytest.raises(TypeError):
        agent.mcp_servers["cao-mcp-server"] = {"command": "changed"}  # type: ignore[index]
    with pytest.raises(TypeError):
        agent.mcp_servers["cao-mcp-server"]["command"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        agent.mcp_servers["cao-mcp-server"].setdefault("args", []).append("--changed")
    with pytest.raises(TypeError):
        agent.mcp_servers["cao-mcp-server"] |= {"command": "changed"}
    with pytest.raises(TypeError):
        agent.mcp_servers["cao-mcp-server"]["args"] += ["--changed"]
    with pytest.raises(TypeError):
        agent.mcp_servers["cao-mcp-server"]["args"] *= 2
    assert agent == equal_agent


def test_write_then_load_agent_round_trips_and_sets_permissions(tmp_path):
    given_agent = _agent()

    write_agent(given_agent, agents_root=tmp_path)
    loaded = load_agent("implementation_partner", agents_root=tmp_path)

    assert loaded == given_agent
    assert (tmp_path / "implementation_partner" / "agent.toml").stat().st_mode & 0o777 == (
        AGENT_CONFIG_MODE
    )
    assert (tmp_path / "implementation_partner" / "prompt.md").stat().st_mode & 0o777 == (
        AGENT_PROMPT_MODE
    )


def test_agent_workspace_round_trips_without_legacy_block(tmp_path):
    given_agent = _agent(workspace=AgentWorkspaceConfig(team="cao_delivery"))

    write_agent(given_agent, agents_root=tmp_path)
    loaded = load_agent("implementation_partner", agents_root=tmp_path)
    config_text = (tmp_path / "implementation_partner" / "agent.toml").read_text()

    assert loaded.workspace.team == "cao_delivery"
    assert "[workspace]" in config_text
    assert 'team = "cao_delivery"' in config_text
    assert "workspace_context" not in config_text


def test_agent_without_workspace_round_trips(tmp_path):
    given_agent = _agent(workspace=AgentWorkspaceConfig())

    write_agent(given_agent, agents_root=tmp_path)
    loaded = load_agent("implementation_partner", agents_root=tmp_path)

    assert loaded.workspace.team is None
    assert "[workspace]" not in (tmp_path / "implementation_partner" / "agent.toml").read_text()


def test_write_agent_failed_replace_preserves_existing_file_and_removes_temp(tmp_path):
    given_agent = _agent()
    write_agent(given_agent, agents_root=tmp_path)
    config_path = tmp_path / given_agent.id / "agent.toml"
    original_text = config_path.read_text()
    original_mode = config_path.stat().st_mode & 0o777

    with (
        patch("cli_agent_orchestrator.agent.os.replace", side_effect=OSError("boom")),
        pytest.raises(OSError, match="boom"),
    ):
        write_agent(_agent(model="gpt-5.4"), agents_root=tmp_path)

    assert config_path.read_text() == original_text
    assert config_path.stat().st_mode & 0o777 == original_mode
    assert not list((tmp_path / given_agent.id).glob(".agent.toml.*"))


def test_load_agent_errors_name_agent_id_and_path(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    (agent_dir / "prompt.md").write_text("prompt")

    with pytest.raises(AgentConfigError) as exc_info:
        load_agent("implementation_partner", agents_root=tmp_path)

    assert "implementation_partner" in str(exc_info.value)
    assert str(agent_dir / "agent.toml") in str(exc_info.value)


def test_load_agent_errors_on_missing_directory_name_agent_id_and_path(tmp_path):
    with pytest.raises(AgentConfigError) as exc_info:
        load_agent("implementation_partner", agents_root=tmp_path)

    assert "implementation_partner" in str(exc_info.value)
    assert str(tmp_path / "implementation_partner") in str(exc_info.value)


def test_load_agent_errors_on_missing_prompt_name_agent_id_and_path(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    (agent_dir / "agent.toml").write_text("""
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"
""".lstrip())

    with pytest.raises(AgentConfigError) as exc_info:
        load_agent("implementation_partner", agents_root=tmp_path)

    assert "implementation_partner" in str(exc_info.value)
    assert str(agent_dir / "prompt.md") in str(exc_info.value)


def test_load_agent_semantic_errors_name_agent_id_and_config_path(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    config_path = agent_dir / "agent.toml"
    config_path.write_text("""
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"

[workspace_context]
enabled = true
""".lstrip())
    (agent_dir / "prompt.md").write_text("# Agent\n")

    with pytest.raises(AgentConfigError) as exc_info:
        load_agent("implementation_partner", agents_root=tmp_path)

    message = str(exc_info.value)
    assert "implementation_partner" in message
    assert str(config_path) in message
    assert "workspace_context is not supported" in message
    assert "[workspace] team" in message


def test_legacy_workspace_context_without_team_is_rejected(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    config_path = agent_dir / "agent.toml"
    config_path.write_text("""
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"

[workspace_context]
enabled = true
resolver_id = "example_planning"
""".lstrip())
    (agent_dir / "prompt.md").write_text("# Agent\n")

    with pytest.raises(AgentConfigError) as exc_info:
        load_agent("implementation_partner", agents_root=tmp_path)

    message = str(exc_info.value)
    assert "implementation_partner" in message
    assert str(config_path) in message
    assert "workspace_context is not supported" in message
    assert "[workspace] team" in message


def test_workspace_wins_over_legacy_workspace_context(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    (agent_dir / "agent.toml").write_text("""
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"

[workspace]
team = "cao_delivery"

[workspace_context]
enabled = true
resolver_id = "example_planning"
""".lstrip())
    (agent_dir / "prompt.md").write_text("# Agent\n")

    agent = load_agent("implementation_partner", agents_root=tmp_path)

    assert agent.workspace.team == "cao_delivery"
    assert agent.workspace.diagnostics == (
        "agents.implementation_partner.workspace_context is legacy and ignored because "
        "[workspace] team is authoritative",
    )


def test_load_agent_path_only_semantic_errors_get_agent_context(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    config_path = agent_dir / "agent.toml"
    config_path.write_text("""
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"
mcp_servers = "not-a-table"
""".lstrip())
    (agent_dir / "prompt.md").write_text("# Agent\n")

    with pytest.raises(AgentConfigError) as exc_info:
        load_agent("implementation_partner", agents_root=tmp_path)

    message = str(exc_info.value)
    assert "Agent 'implementation_partner'" in message
    assert str(config_path) in message
    assert "mcp_servers must be a table" in message


def test_load_agent_errors_on_malformed_toml(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    config_path = agent_dir / "agent.toml"
    config_path.write_text("[broken\n")
    (agent_dir / "prompt.md").write_text("prompt")

    with pytest.raises(AgentConfigError) as exc_info:
        load_agent("implementation_partner", agents_root=tmp_path)

    assert "implementation_partner" in str(exc_info.value)
    assert str(config_path) in str(exc_info.value)


def test_load_agent_accepts_optional_fields_absent(tmp_path):
    agent_dir = tmp_path / "minimal"
    agent_dir.mkdir()
    (agent_dir / "agent.toml").write_text("""
id = "minimal"
display_name = "Minimal"
cli_provider = "codex"
workdir = "/repo"
session_name = "minimal"
""".lstrip())
    (agent_dir / "prompt.md").write_text("# Minimal\n")

    loaded = load_agent("minimal", agents_root=tmp_path)

    assert loaded.description is None
    assert loaded.mcp_servers == {}
    assert loaded.cao_tools is None


def test_load_agent_rejects_missing_required_id(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    (agent_dir / "agent.toml").write_text("""
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"
""".lstrip())
    (agent_dir / "prompt.md").write_text("# Agent\n")

    with pytest.raises(AgentConfigError, match="id"):
        load_agent("implementation_partner", agents_root=tmp_path)


def test_load_agent_rejects_removed_linear_config_section(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    config_path = agent_dir / "agent.toml"
    config_path.write_text("""
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"

[linear]
app_key = "stale"
""".lstrip())
    (agent_dir / "prompt.md").write_text("# Agent\n")

    with pytest.raises(AgentConfigError) as exc_info:
        load_agent("implementation_partner", agents_root=tmp_path)

    message = str(exc_info.value)
    assert "implementation_partner" in message
    assert str(config_path) in message
    assert "removed config section [linear]" in message


def test_load_agent_registry_ignores_invalid_local_agent_dirs(tmp_path):
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "agent.toml").write_text("""
id = "bad"
display_name = "Bad"
cli_provider = "codex"
workdir = "/repo"
session_name = "bad"

[linear]
app_key = "stale"
""".lstrip())
    (bad_dir / "prompt.md").write_text("# Bad\n")
    write_agent(_agent(id="good", display_name="Good", session_name="good"), agents_root=tmp_path)

    registry = load_agent_registry(agents_root=tmp_path)

    assert list(registry.all()) == ["good"]


def test_patch_agent_config_preserves_unrelated_formatting_and_updates_prompt(tmp_path):
    given_agent = _agent()
    write_agent(given_agent, agents_root=tmp_path)
    config_path = tmp_path / given_agent.id / "agent.toml"
    config_path.write_text("""
# keep this operator note
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"
model = "gpt-5.2"
tools = ["bash"]

[mcp_servers.cao-mcp-server]
command = "cao-mcp-server"
""".lstrip())
    updated = _agent(
        model="gpt-5.4",
        tools=(),
        mcp_servers={"cao-mcp-server": {"command": "cao-mcp-server", "args": ["--stdio"]}},
        prompt="# Updated Agent\n",
    )

    patch_agent_config(
        updated,
        changed_fields={"model", "tools", "mcp_servers", "prompt"},
        agents_root=tmp_path,
    )

    patched_text = config_path.read_text()
    loaded = load_agent(given_agent.id, agents_root=tmp_path)
    assert "# keep this operator note" in patched_text
    assert loaded.model == "gpt-5.4"
    assert loaded.tools == ()
    assert loaded.mcp_servers["cao-mcp-server"]["args"] == ["--stdio"]
    assert loaded.prompt == "# Updated Agent\n"


def test_validate_agents_root_flags_bad_permissions(tmp_path):
    given_agent = _agent()
    write_agent(given_agent, agents_root=tmp_path)
    os.chmod(tmp_path / given_agent.id / "prompt.md", 0o600)

    with pytest.raises(AgentValidationError) as exc_info:
        validate_agents_root(agents_root=tmp_path)

    message = str(exc_info.value)
    assert "implementation_partner" in message
    assert "prompt.md" in message
    assert "0644" in message


def test_validate_agents_root_flags_empty_prompt(tmp_path):
    write_agent(
        _agent(
            id="agent_a",
            display_name="Agent A",
            session_name="agent-a",
            prompt="",
        ),
        agents_root=tmp_path,
    )

    with pytest.raises(AgentValidationError) as exc_info:
        validate_agents_root(agents_root=tmp_path)

    message = str(exc_info.value)
    assert "prompt.md must be non-empty" in message


def test_validate_agents_root_flags_load_errors_and_continues_aggregation(tmp_path):
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "agent.toml").write_text("[broken\n")
    (bad_dir / "prompt.md").write_text("# Bad\n")
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    good_config = good_dir / "agent.toml"
    good_prompt = good_dir / "prompt.md"
    good_config.write_text("""
id = "good"
display_name = "Good"
cli_provider = "codex"
workdir = "/repo"
session_name = "good"
""".lstrip())
    good_prompt.write_text("# Good\n")
    os.chmod(good_config, AGENT_CONFIG_MODE)
    os.chmod(good_prompt, 0o600)

    with pytest.raises(AgentValidationError) as exc_info:
        validate_agents_root(agents_root=tmp_path)

    message = str(exc_info.value)
    assert "invalid TOML" in message
    assert "good" in message
    assert "0644" in message

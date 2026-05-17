"""Tests for durable CAO agent directories."""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError

import pytest

from cli_agent_orchestrator.agent import (
    AGENT_CONFIG_MODE,
    AGENT_PROMPT_MODE,
    Agent,
    AgentConfigError,
    AgentValidationError,
    AgentWorkspaceContextConfig,
    LinearConfig,
    LinearToolAccessConfig,
    load_agent,
    load_all_agents,
    patch_agent_config,
    patch_agent_section,
    validate_agents_root,
    write_agent,
)


def _agent(**overrides: object) -> Agent:
    values = {
        "id": "implementation_partner",
        "display_name": "Implementation Partner",
        "cli_provider": "codex",
        "workdir": "/repo",
        "session_name": "implementation-partner",
        "prompt": "# Agent\n\nHelp with implementation.\n",
        "description": "Developer Agent in a multi-agent system",
        "model": "gpt-5.2",
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
        "workspace_context": AgentWorkspaceContextConfig(
            enabled=True,
            resolver_id="linear_planning",
        ),
        "linear": LinearConfig(
            app_key="implementation_partner",
            client_id="client-1",
            client_secret="secret-1",
            oauth_redirect_uri="https://example.test/linear/oauth/callback",
            tool_access=(
                LinearToolAccessConfig(
                    access_id="implementation_partner_workflow",
                    tools=("cao_linear.get_issue", "cao_linear.update_issue"),
                    issues=("CAO-1",),
                    update_fields=("title",),
                ),
            ),
        ),
    }
    values.update(overrides)
    return Agent(**values)


def test_agent_model_rejects_invalid_workspace_context_combination():
    with pytest.raises(AgentConfigError, match="resolver_id is required"):
        _agent(workspace_context=AgentWorkspaceContextConfig(enabled=True))


def test_agent_model_rejects_invalid_linear_tool_access_at_construction():
    with pytest.raises(AgentConfigError, match="tools must be a non-empty tuple"):
        LinearToolAccessConfig(
            access_id="empty_tools",
            tools=(),
            issues=("CAO-1",),
        )

    with pytest.raises(AgentConfigError, match="issues must be a non-empty tuple"):
        LinearToolAccessConfig(
            access_id="empty_issues",
            tools=("cao_linear.get_issue",),
            issues=(),
        )

    with pytest.raises(AgentConfigError, match="linear.tool_access must contain"):
        LinearConfig(tool_access=("not-a-policy",))  # type: ignore[arg-type]


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


def test_load_agent_errors_name_agent_id_and_path(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    (agent_dir / "prompt.md").write_text("prompt")

    with pytest.raises(AgentConfigError) as exc_info:
        load_agent("implementation_partner", agents_root=tmp_path)

    assert "implementation_partner" in str(exc_info.value)
    assert str(agent_dir / "agent.toml") in str(exc_info.value)


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
    assert loaded.linear is None


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


def test_load_all_agents_returns_independent_linear_sections(tmp_path):
    write_agent(
        _agent(id="agent_a", display_name="Agent A", session_name="agent-a"),
        agents_root=tmp_path,
    )
    write_agent(
        _agent(
            id="agent_b",
            display_name="Agent B",
            session_name="agent-b",
            linear=LinearConfig(app_key="agent_b", client_id="client-b"),
        ),
        agents_root=tmp_path,
    )

    registry = load_all_agents(agents_root=tmp_path)

    assert registry.get("agent_a").linear is not None
    assert registry.get("agent_b").linear is not None
    assert registry.get("agent_a").linear is not registry.get("agent_b").linear


def test_patch_agent_section_preserves_unrelated_linear_tool_access(tmp_path):
    given_agent = _agent()
    write_agent(given_agent, agents_root=tmp_path)
    config_path = tmp_path / given_agent.id / "agent.toml"
    original = config_path.read_text()

    patch_agent_section(
        given_agent.id,
        "linear",
        {
            "access_token": "access-2",
            "refresh_token": "refresh-2",
            "app_user_id": "user-2",
            "token_expires_at": "2026-05-16T20:00:00+00:00",
        },
        agents_root=tmp_path,
    )
    loaded = load_agent(given_agent.id, agents_root=tmp_path)

    assert loaded.linear is not None
    assert loaded.linear.access_token == "access-2"
    assert loaded.linear.refresh_token == "refresh-2"
    assert loaded.linear.app_user_id == "user-2"
    assert loaded.linear.tool_access == given_agent.linear.tool_access
    assert "[linear.tool_access.implementation_partner_workflow]" in config_path.read_text()
    assert "[mcp_servers.cao-mcp-server]" in original


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

[linear]
app_key = "implementation_partner"
client_id = "client-1"
client_secret = "secret-1"
oauth_redirect_uri = "https://example.test/linear/oauth/callback"

[linear.tool_access.implementation_partner_workflow]
tools = ["cao_linear.get_issue"]
issues = ["CAO-1"]
update_fields = ["title"]
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
    assert "[linear.tool_access.implementation_partner_workflow]" in patched_text
    assert loaded.model == "gpt-5.4"
    assert loaded.tools == ()
    assert loaded.mcp_servers["cao-mcp-server"]["args"] == ["--stdio"]
    assert loaded.prompt == "# Updated Agent\n"


def test_validate_agents_root_flags_unknown_linear_tool_and_bad_permissions(tmp_path):
    given_agent = _agent(
        linear=LinearConfig(
            app_key="implementation_partner",
            tool_access=(
                LinearToolAccessConfig(
                    access_id="bad",
                    tools=("cao_linear.nope",),
                    issues=("*",),
                ),
            ),
        )
    )
    write_agent(given_agent, agents_root=tmp_path)
    os.chmod(tmp_path / given_agent.id / "prompt.md", 0o600)

    with pytest.raises(AgentValidationError) as exc_info:
        validate_agents_root(agents_root=tmp_path)

    message = str(exc_info.value)
    assert "implementation_partner" in message
    assert "cao_linear.nope" in message
    assert "prompt.md" in message
    assert "0644" in message


def test_validate_agents_root_flags_empty_prompt_unknown_update_field_and_duplicate_linear_user(
    tmp_path,
):
    write_agent(
        _agent(
            id="agent_a",
            display_name="Agent A",
            session_name="agent-a",
            prompt="",
            linear=LinearConfig(
                app_key="agent_a",
                app_user_id="linear-user-1",
                tool_access=(
                    LinearToolAccessConfig(
                        access_id="bad_update",
                        tools=("cao_linear.update_issue",),
                        issues=("CAO-1",),
                        update_fields=("not_a_field",),
                    ),
                ),
            ),
        ),
        agents_root=tmp_path,
    )
    write_agent(
        _agent(
            id="agent_b",
            display_name="Agent B",
            session_name="agent-b",
            linear=LinearConfig(app_key="agent_b", app_user_id="linear-user-1"),
        ),
        agents_root=tmp_path,
    )

    with pytest.raises(AgentValidationError) as exc_info:
        validate_agents_root(agents_root=tmp_path)

    message = str(exc_info.value)
    assert "prompt.md must be non-empty" in message
    assert "not_a_field" in message
    assert "duplicates agent_a" in message


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


def test_validate_agents_root_rejects_non_boolean_linear_allow_top_level_create(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    config = agent_dir / "agent.toml"
    prompt = agent_dir / "prompt.md"
    config.write_text(f"""
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"

[linear.tool_access.workflow]
tools = ["cao_linear.create_issue"]
issues = ["*"]
allow_top_level_create = "false"
""".lstrip())
    prompt.write_text("# Agent\n")
    os.chmod(config, AGENT_CONFIG_MODE)
    os.chmod(prompt, AGENT_PROMPT_MODE)

    with pytest.raises(AgentValidationError, match="allow_top_level_create"):
        validate_agents_root(agents_root=tmp_path)


@pytest.mark.parametrize(
    ("tool_access_body", "missing_field"),
    [
        ('issues = ["*"]', "tools"),
        ('tools = ["cao_linear.get_issue"]', "issues"),
    ],
)
def test_validate_agents_root_rejects_missing_required_linear_tool_access_fields(
    tmp_path,
    tool_access_body,
    missing_field,
):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    config = agent_dir / "agent.toml"
    prompt = agent_dir / "prompt.md"
    config.write_text(f"""
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"

[linear.tool_access.workflow]
{tool_access_body}
""".lstrip())
    prompt.write_text("# Agent\n")
    os.chmod(config, AGENT_CONFIG_MODE)
    os.chmod(prompt, AGENT_PROMPT_MODE)

    with pytest.raises(AgentValidationError, match=missing_field):
        validate_agents_root(agents_root=tmp_path)


def test_validate_agents_root_passes_for_hand_written_shape(tmp_path):
    agent_dir = tmp_path / "implementation_partner"
    agent_dir.mkdir()
    config = agent_dir / "agent.toml"
    prompt = agent_dir / "prompt.md"
    config.write_text("""
id = "implementation_partner"
display_name = "Implementation Partner"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"

[linear]
app_key = "implementation_partner"

[linear.tool_access.workflow]
tools = ["cao_linear.get_issue"]
issues = ["*"]
""".lstrip())
    prompt.write_text("# Agent\n")
    os.chmod(config, AGENT_CONFIG_MODE)
    os.chmod(prompt, AGENT_PROMPT_MODE)

    validate_agents_root(agents_root=tmp_path)

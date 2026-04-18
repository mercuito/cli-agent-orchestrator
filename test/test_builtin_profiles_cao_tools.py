"""Smoke tests for the caoTools declarations in CAO's built-in agent profiles.

Built-in profiles ship with explicit caoTools so the LLM only sees what
each role is supposed to use. A supervisor gets the orchestration tools;
developers and reviewers get only the callback/skill loaders.

These tests load profiles directly from the package's built-in store so
they assert on what CAO *ships*, not on whatever the current user has
installed locally (which might shadow built-ins with a stale pre-Phase-4
copy).
"""

from __future__ import annotations

from importlib import resources

from cli_agent_orchestrator.utils.agent_profiles import parse_agent_profile_text
from cli_agent_orchestrator.utils.cao_tool_allowlist import resolve_cao_tool_allowlist


def _load_builtin_profile(name: str):
    """Parse the shipped built-in profile for ``name`` directly from the
    package's agent_store, bypassing local-store override lookup."""
    store = resources.files("cli_agent_orchestrator.agent_store")
    text = (store / f"{name}.md").read_text()
    return parse_agent_profile_text(text, name)


def test_code_supervisor_can_orchestrate():
    profile = _load_builtin_profile("code_supervisor")
    allowlist = resolve_cao_tool_allowlist(profile)

    # Must be able to spawn workers and collect results
    assert "assign" in allowlist
    assert "handoff" in allowlist
    assert "terminate" in allowlist
    assert "send_message" in allowlist
    # Profile discovery for runtime orchestration choices
    assert "list_agent_profiles" in allowlist
    assert "get_agent_profile" in allowlist
    # Skills for agent behaviour customization
    assert "load_skill" in allowlist


def test_developer_cannot_spawn_or_terminate():
    profile = _load_builtin_profile("developer")
    allowlist = resolve_cao_tool_allowlist(profile)

    # Callback and skill loading only — no orchestration
    assert allowlist == ["send_message", "load_skill"]
    assert "assign" not in allowlist
    assert "handoff" not in allowlist
    assert "terminate" not in allowlist


def test_reviewer_cannot_spawn_or_terminate():
    profile = _load_builtin_profile("reviewer")
    allowlist = resolve_cao_tool_allowlist(profile)

    # Same minimal surface as developer
    assert allowlist == ["send_message", "load_skill"]
    assert "assign" not in allowlist
    assert "handoff" not in allowlist
    assert "terminate" not in allowlist


def test_builtin_profile_allowlists_reference_only_real_tools():
    """Every tool named in a built-in profile's caoTools must exist in the
    server's deferred registry. Catches typos in profile frontmatter at
    test time rather than at startup."""
    from cli_agent_orchestrator.mcp_server.server import _PENDING_TOOLS

    known = {name for name, _, _ in _PENDING_TOOLS}

    for profile_name in ("code_supervisor", "developer", "reviewer"):
        profile = _load_builtin_profile(profile_name)
        for tool in profile.caoTools or []:
            assert tool in known, (
                f"built-in profile {profile_name!r} declares unknown tool {tool!r}; "
                f"known tools: {sorted(known)}"
            )

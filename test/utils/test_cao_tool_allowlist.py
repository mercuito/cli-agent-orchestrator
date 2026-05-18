"""Tests for the CAO MCP tool allowlist resolver.

The resolver decides which ``cao-mcp-server`` tools an agent is allowed to
call, based on (in priority order):
  1. ``agent.cao_tools`` — explicit per-agent allowlist
  2. ``None`` — nothing configured

Returning ``None`` is deliberately distinct from returning ``[]`` (empty
allowlist). Downstream callers use ``None`` to mean "no restriction
configured, fall back to permissive" during Phase 2/3, and ``[]`` to mean
"explicitly no tools allowed."

No runtime wiring yet — this phase only adds the mechanism.
"""

from __future__ import annotations

from test.support.agent_factory import Agent

from cli_agent_orchestrator.utils.cao_tool_allowlist import resolve_cao_tool_allowlist


def _profile(**kwargs) -> Agent:
    """Build a minimal valid Agent with overrides."""
    defaults = {"name": "test", "description": "t"}
    defaults.update(kwargs)
    return Agent(**defaults)


class TestProfileExplicitAllowlistWins:
    def test_profile_cao_tools_is_returned_as_is(self):
        profile = _profile(cao_tools=["send_message", "read_inbox_message"])
        result = resolve_cao_tool_allowlist(profile)
        assert result == ["send_message", "read_inbox_message"]

    def test_empty_list_on_profile_is_respected_not_treated_as_none(self):
        """``cao_tools = []`` explicitly means 'no tools allowed'."""
        profile = _profile(cao_tools=[])
        result = resolve_cao_tool_allowlist(profile)
        assert result == []

    def test_profile_allowlist_is_named_cao_tool_source(self):
        profile = _profile(cao_tools=["send_message"])
        result = resolve_cao_tool_allowlist(profile)
        assert result == ["send_message"]


class TestNothingConfigured:
    def test_no_cao_tools_returns_none(self):
        profile = _profile()
        result = resolve_cao_tool_allowlist(profile)
        assert result is None


class TestAgentFieldSchema:
    """cao_tools must be an optional tuple-of-strings field on Agent."""

    def test_profile_accepts_cao_tools_list(self):
        profile = Agent(name="x", description="y", cao_tools=["send_message"])
        assert profile.cao_tools == ("send_message",)

    def test_profile_cao_tools_defaults_to_none(self):
        profile = Agent(name="x", description="y")
        assert profile.cao_tools is None

    def test_profile_accepts_empty_list(self):
        profile = Agent(name="x", description="y", cao_tools=[])
        assert profile.cao_tools == ()

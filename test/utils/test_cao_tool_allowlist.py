"""Tests for the CAO MCP tool allowlist resolver.

The resolver decides which ``cao-mcp-server`` tools an agent is allowed to
call, based on (in priority order):
  1. ``profile.caoTools`` — explicit per-profile allowlist
  2. ``None`` — nothing configured

Returning ``None`` is deliberately distinct from returning ``[]`` (empty
allowlist). Downstream callers use ``None`` to mean "no restriction
configured, fall back to permissive" during Phase 2/3, and ``[]`` to mean
"explicitly no tools allowed."

No runtime wiring yet — this phase only adds the mechanism.
"""

from __future__ import annotations

from cli_agent_orchestrator.models.agent_profile import AgentProfile
from cli_agent_orchestrator.utils.cao_tool_allowlist import resolve_cao_tool_allowlist


def _profile(**kwargs) -> AgentProfile:
    """Build a minimal valid AgentProfile with overrides."""
    defaults = {"name": "test", "description": "t"}
    defaults.update(kwargs)
    return AgentProfile(**defaults)


class TestProfileExplicitAllowlistWins:
    def test_profile_cao_tools_is_returned_as_is(self):
        profile = _profile(caoTools=["send_message", "read_inbox_message"])
        result = resolve_cao_tool_allowlist(profile)
        assert result == ["send_message", "read_inbox_message"]

    def test_empty_list_on_profile_is_respected_not_treated_as_none(self):
        """``caoTools: []`` explicitly means 'no tools allowed'."""
        profile = _profile(caoTools=[])
        result = resolve_cao_tool_allowlist(profile)
        assert result == []

    def test_profile_allowlist_is_named_cao_tool_source(self):
        profile = _profile(caoTools=["send_message"])
        result = resolve_cao_tool_allowlist(profile)
        assert result == ["send_message"]


class TestNothingConfigured:
    def test_no_cao_tools_returns_none(self):
        profile = _profile()
        result = resolve_cao_tool_allowlist(profile)
        assert result is None

class TestAgentProfileFieldSchema:
    """caoTools must be an optional list-of-strings field on AgentProfile."""

    def test_profile_accepts_cao_tools_list(self):
        profile = AgentProfile(name="x", description="y", caoTools=["send_message"])
        assert profile.caoTools == ["send_message"]

    def test_profile_cao_tools_defaults_to_none(self):
        profile = AgentProfile(name="x", description="y")
        assert profile.caoTools is None

    def test_profile_accepts_empty_list(self):
        profile = AgentProfile(name="x", description="y", caoTools=[])
        assert profile.caoTools == []

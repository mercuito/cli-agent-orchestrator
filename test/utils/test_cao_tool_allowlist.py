"""Tests for the CAO MCP tool allowlist resolver.

The resolver decides which ``cao-mcp-server`` tools an agent is allowed to
call, based on (in priority order):
  1. ``profile.caoTools`` — explicit per-profile allowlist
  2. ``settings.role_cao_tools[profile.role]`` — role-based default
  3. ``None`` — nothing configured

Returning ``None`` is deliberately distinct from returning ``[]`` (empty
allowlist). Downstream callers use ``None`` to mean "no restriction
configured, fall back to permissive" during Phase 2/3, and ``[]`` to mean
"explicitly no tools allowed."

No runtime wiring yet — this phase only adds the mechanism.
"""

from __future__ import annotations

from unittest.mock import patch

from cli_agent_orchestrator.models.agent_profile import AgentProfile
from cli_agent_orchestrator.utils.cao_tool_allowlist import resolve_cao_tool_allowlist


def _profile(**kwargs) -> AgentProfile:
    """Build a minimal valid AgentProfile with overrides."""
    defaults = {"name": "test", "description": "t"}
    defaults.update(kwargs)
    return AgentProfile(**defaults)


class TestProfileExplicitAllowlistWins:
    def test_profile_cao_tools_is_returned_as_is(self):
        profile = _profile(caoTools=["send_message", "load_skill"])
        result = resolve_cao_tool_allowlist(profile)
        assert result == ["send_message", "load_skill"]

    def test_empty_list_on_profile_is_respected_not_treated_as_none(self):
        """``caoTools: []`` explicitly means 'no tools allowed' — do not
        degrade to role lookup."""
        profile = _profile(caoTools=[], role="supervisor")
        with patch(
            "cli_agent_orchestrator.utils.cao_tool_allowlist.get_role_cao_tools"
        ) as mock_settings:
            mock_settings.return_value = ["assign", "handoff"]  # should NOT be used
            result = resolve_cao_tool_allowlist(profile)
        assert result == []

    def test_profile_allowlist_wins_over_role_defaults(self):
        profile = _profile(caoTools=["send_message"], role="supervisor")
        with patch(
            "cli_agent_orchestrator.utils.cao_tool_allowlist.get_role_cao_tools"
        ) as mock_settings:
            mock_settings.return_value = ["assign", "handoff"]
            result = resolve_cao_tool_allowlist(profile)
        assert result == ["send_message"]


class TestRoleFallback:
    def test_role_with_settings_match_returns_settings_value(self):
        profile = _profile(role="supervisor")
        with patch(
            "cli_agent_orchestrator.utils.cao_tool_allowlist.get_role_cao_tools"
        ) as mock_settings:
            mock_settings.return_value = ["assign", "handoff", "terminate"]
            result = resolve_cao_tool_allowlist(profile)
        assert result == ["assign", "handoff", "terminate"]
        mock_settings.assert_called_once_with("supervisor")

    def test_role_without_settings_match_returns_none(self):
        profile = _profile(role="supervisor")
        with patch(
            "cli_agent_orchestrator.utils.cao_tool_allowlist.get_role_cao_tools",
            return_value=None,
        ):
            result = resolve_cao_tool_allowlist(profile)
        assert result is None


class TestNothingConfigured:
    def test_no_cao_tools_no_role_returns_none(self):
        profile = _profile()
        with patch(
            "cli_agent_orchestrator.utils.cao_tool_allowlist.get_role_cao_tools",
            return_value=None,
        ):
            result = resolve_cao_tool_allowlist(profile)
        assert result is None

    def test_no_cao_tools_and_empty_role_string_returns_none(self):
        """An empty-string role (as opposed to None) should still fall through
        to None rather than triggering a settings lookup with ''."""
        profile = _profile(role="")
        with patch(
            "cli_agent_orchestrator.utils.cao_tool_allowlist.get_role_cao_tools"
        ) as mock_settings:
            result = resolve_cao_tool_allowlist(profile)
        assert result is None
        mock_settings.assert_not_called()


class TestGetRoleCaoToolsFromSettings:
    """settings_service.get_role_cao_tools reads settings.json's
    'role_cao_tools' section. Covers the happy paths and the shape
    contract with resolve_cao_tool_allowlist."""

    def test_returns_list_for_known_role(self, tmp_path, monkeypatch):
        import cli_agent_orchestrator.services.settings_service as svc

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            '{"role_cao_tools": {"supervisor": ["assign", "handoff"]}}'
        )
        monkeypatch.setattr(svc, "SETTINGS_FILE", settings_file)

        from cli_agent_orchestrator.services.settings_service import get_role_cao_tools

        assert get_role_cao_tools("supervisor") == ["assign", "handoff"]

    def test_returns_none_for_unknown_role(self, tmp_path, monkeypatch):
        import cli_agent_orchestrator.services.settings_service as svc

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            '{"role_cao_tools": {"supervisor": ["assign"]}}'
        )
        monkeypatch.setattr(svc, "SETTINGS_FILE", settings_file)

        from cli_agent_orchestrator.services.settings_service import get_role_cao_tools

        assert get_role_cao_tools("developer") is None

    def test_returns_none_when_section_missing(self, tmp_path, monkeypatch):
        import cli_agent_orchestrator.services.settings_service as svc

        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{}")
        monkeypatch.setattr(svc, "SETTINGS_FILE", settings_file)

        from cli_agent_orchestrator.services.settings_service import get_role_cao_tools

        assert get_role_cao_tools("supervisor") is None

    def test_returns_none_when_settings_file_missing(self, tmp_path, monkeypatch):
        import cli_agent_orchestrator.services.settings_service as svc

        monkeypatch.setattr(svc, "SETTINGS_FILE", tmp_path / "does_not_exist.json")

        from cli_agent_orchestrator.services.settings_service import get_role_cao_tools

        assert get_role_cao_tools("supervisor") is None

    def test_ignores_non_list_value(self, tmp_path, monkeypatch):
        """Defensive: if a user hand-edits settings.json and puts something
        weird (string, number, null) under a role, we must not crash and
        must not return nonsense."""
        import cli_agent_orchestrator.services.settings_service as svc

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            '{"role_cao_tools": {"supervisor": "not-a-list"}}'
        )
        monkeypatch.setattr(svc, "SETTINGS_FILE", settings_file)

        from cli_agent_orchestrator.services.settings_service import get_role_cao_tools

        assert get_role_cao_tools("supervisor") is None


class TestAgentProfileFieldSchema:
    """caoTools must be an optional list-of-strings field on AgentProfile."""

    def test_profile_accepts_cao_tools_list(self):
        profile = AgentProfile(
            name="x", description="y", caoTools=["send_message"]
        )
        assert profile.caoTools == ["send_message"]

    def test_profile_cao_tools_defaults_to_none(self):
        profile = AgentProfile(name="x", description="y")
        assert profile.caoTools is None

    def test_profile_accepts_empty_list(self):
        profile = AgentProfile(name="x", description="y", caoTools=[])
        assert profile.caoTools == []

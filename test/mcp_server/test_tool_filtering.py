"""Tests for startup-time MCP tool filtering.

The cao-mcp-server subprocess reads CAO_TERMINAL_ID, fetches the agent's
profile, resolves an allowlist, and only exposes the tools named in that
allowlist. ``None`` allowlist (nothing configured) falls back to
permissive — every deferred tool gets registered. This is the Phase 3
wiring that makes Phase 2's resolver actually do something.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from cli_agent_orchestrator.mcp_server import server


class TestDeferredToolRegistry:
    """Every @_deferred_tool decorator must record its function + metadata
    so _register_tools can later decide whether to apply @mcp.tool()."""

    def test_registry_includes_all_current_tools(self):
        """Sanity: after import, the pending registry contains every tool
        the server is expected to expose. If someone adds a new tool and
        forgets the deferred decorator, this catches it."""
        names = {name for name, _, _ in server._PENDING_TOOLS}
        expected = {
            "handoff",
            "assign",
            "send_message",
            "load_skill",
            "list_agent_profiles",
            "get_agent_profile",
            "terminate",
        }
        assert expected <= names

    def test_registry_entries_have_callable_functions(self):
        for name, fn, kwargs in server._PENDING_TOOLS:
            assert callable(fn), f"tool {name!r} is not callable"
            assert isinstance(kwargs, dict)


class TestRegisterTools:
    def _mock_mcp(self):
        mock = MagicMock()
        mock.tool.return_value = lambda f: f  # decorator returns the fn unchanged
        return mock

    def test_none_allowlist_registers_every_pending_tool(self):
        """Permissive default. Backward-compatible with agents that have
        no caoTools and no matching role."""
        pending = [("a", lambda: None, {}), ("b", lambda: None, {}), ("c", lambda: None, {})]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(pending, None, mcp_instance)

        assert set(registered) == {"a", "b", "c"}
        assert mcp_instance.tool.call_count == 3

    def test_explicit_allowlist_registers_only_matching_tools(self):
        pending = [("a", lambda: None, {}), ("b", lambda: None, {}), ("c", lambda: None, {})]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(pending, ["a", "c"], mcp_instance)

        assert set(registered) == {"a", "c"}
        assert mcp_instance.tool.call_count == 2

    def test_empty_allowlist_registers_nothing(self):
        """Distinct from None — user explicitly said 'this agent may not
        call any cao-mcp-server tool.'"""
        pending = [("a", lambda: None, {}), ("b", lambda: None, {})]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(pending, [], mcp_instance)

        assert registered == []
        assert mcp_instance.tool.call_count == 0

    def test_allowlist_names_not_in_registry_are_silently_ignored(self):
        """A typo in the allowlist doesn't crash startup. It just results
        in that tool not being registered — which is what would happen
        anyway if it existed in the allowlist but not the registry."""
        pending = [("a", lambda: None, {})]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(pending, ["a", "typo"], mcp_instance)

        assert registered == ["a"]

    def test_tool_kwargs_are_forwarded_to_mcp_tool_decorator(self):
        """E.g. load_skill passes description=<long string>; terminate
        passes nothing. Both paths must work."""
        pending = [("with_desc", lambda: None, {"description": "doc"})]
        mcp_instance = self._mock_mcp()

        server._register_tools(pending, None, mcp_instance)

        mcp_instance.tool.assert_called_once_with(description="doc")

    def test_baton_tools_are_hidden_when_feature_disabled(self, monkeypatch):
        monkeypatch.setenv("CAO_BATON_ENABLED", "false")
        pending = [
            ("send_message", lambda: None, {}),
            ("create_baton", lambda: None, {}),
            ("pass_baton", lambda: None, {}),
        ]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(pending, None, mcp_instance)

        assert registered == ["send_message"]
        assert mcp_instance.tool.call_count == 1

    def test_baton_tools_register_when_feature_enabled(self, monkeypatch):
        monkeypatch.setenv("CAO_BATON_ENABLED", "true")
        pending = [
            ("send_message", lambda: None, {}),
            ("create_baton", lambda: None, {}),
        ]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(pending, None, mcp_instance)

        assert registered == ["send_message", "create_baton"]
        assert mcp_instance.tool.call_count == 2


class TestResolveAllowlistForTerminal:
    @patch("cli_agent_orchestrator.mcp_server.server.load_agent_profile")
    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    def test_happy_path(self, mock_get, mock_load_profile):
        """Fetch terminal metadata, load profile, delegate to resolver."""
        mock_get.return_value.json.return_value = {"agent_profile": "some_profile"}
        mock_get.return_value.raise_for_status.return_value = None

        fake_profile = MagicMock()
        mock_load_profile.return_value = fake_profile

        with patch(
            "cli_agent_orchestrator.mcp_server.server.resolve_cao_tool_allowlist",
            return_value=["send_message"],
        ) as mock_resolve:
            result = server._resolve_allowlist_for_terminal("abc123")

        assert result == ["send_message"]
        mock_load_profile.assert_called_once_with("some_profile")
        mock_resolve.assert_called_once_with(fake_profile)

    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    def test_api_unreachable_returns_none_permissive(self, mock_get):
        """If cao-server can't be reached, we fail open in Phase 3 so
        existing agents (without caoTools configured) keep working. An
        error is logged; flipping to fail-closed is a later, opt-in
        choice (Phase 5)."""
        mock_get.side_effect = requests.ConnectionError("refused")

        result = server._resolve_allowlist_for_terminal("abc123")

        assert result is None

    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    def test_api_hang_is_bounded_and_fails_open(self, mock_get):
        """A hung API call at startup would exceed the provider MCP client's
        handshake timeout (codex kills after ~30s) and leave the agent with
        no MCP connection. We must cut the request off well under that and
        fail open, even though the filter won't apply for that spawn."""
        mock_get.side_effect = requests.Timeout("read timed out")

        result = server._resolve_allowlist_for_terminal("abc123")

        assert result is None
        # And we passed a short timeout, not 'no timeout'
        _, kwargs = mock_get.call_args
        assert kwargs.get("timeout") is not None
        assert kwargs["timeout"] <= 10

    @patch("cli_agent_orchestrator.mcp_server.server.load_agent_profile")
    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    def test_unknown_profile_returns_none_permissive(
        self, mock_get, mock_load_profile
    ):
        """If the profile can't be loaded (e.g. stale DB row referencing a
        deleted profile), fall back to permissive rather than leaving the
        agent with zero tools."""
        mock_get.return_value.json.return_value = {"agent_profile": "missing"}
        mock_get.return_value.raise_for_status.return_value = None
        mock_load_profile.side_effect = FileNotFoundError("no such profile")

        result = server._resolve_allowlist_for_terminal("abc123")

        assert result is None

    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    def test_missing_agent_profile_field_returns_none(self, mock_get):
        """Defensive against a malformed API response."""
        mock_get.return_value.json.return_value = {}  # no agent_profile key
        mock_get.return_value.raise_for_status.return_value = None

        result = server._resolve_allowlist_for_terminal("abc123")

        assert result is None


class TestMainStartupFiltering:
    """Integration of the pieces: main() reads CAO_TERMINAL_ID, resolves,
    registers. These tests exercise main() with mcp.run() patched so the
    server doesn't actually start."""

    @patch("cli_agent_orchestrator.mcp_server.server.mcp")
    @patch("cli_agent_orchestrator.mcp_server.server._register_tools")
    @patch("cli_agent_orchestrator.mcp_server.server._resolve_allowlist_for_terminal")
    def test_main_passes_resolved_allowlist_to_register(
        self, mock_resolve, mock_register, mock_mcp, monkeypatch
    ):
        monkeypatch.setenv("CAO_TERMINAL_ID", "term-xyz")
        mock_resolve.return_value = ["assign", "send_message"]

        server.main()

        mock_resolve.assert_called_once_with("term-xyz")
        # First arg = pending registry, second = allowlist, third = mcp instance
        args = mock_register.call_args[0]
        assert args[1] == ["assign", "send_message"]
        mock_mcp.run.assert_called_once()

    @patch("cli_agent_orchestrator.mcp_server.server.mcp")
    @patch("cli_agent_orchestrator.mcp_server.server._register_tools")
    def test_main_without_cao_terminal_id_registers_permissively(
        self, mock_register, mock_mcp, monkeypatch
    ):
        """If the server is started outside of CAO (developer invokes
        directly to test, etc.) there's no terminal context. Register all
        tools rather than erroring out."""
        monkeypatch.delenv("CAO_TERMINAL_ID", raising=False)

        server.main()

        args = mock_register.call_args[0]
        assert args[1] is None  # permissive
        mock_mcp.run.assert_called_once()


class TestRegressionExistingTestsStillPass:
    """After refactoring @mcp.tool() decorators to @_deferred_tool, the
    existing unit tests that import and call *_impl functions should still
    work because _impl functions are not the decorated ones."""

    def test_handoff_impl_still_importable(self):
        from cli_agent_orchestrator.mcp_server.server import _handoff_impl

        assert callable(_handoff_impl)

    def test_terminate_impl_still_importable(self):
        from cli_agent_orchestrator.mcp_server.server import _terminate_impl

        assert callable(_terminate_impl)

    def test_list_agent_profiles_impl_still_importable(self):
        from cli_agent_orchestrator.mcp_server.server import _list_agent_profiles_impl

        assert callable(_list_agent_profiles_impl)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for ToolService-owned MCP tool registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.mcp_server import server
from cli_agent_orchestrator.services.tool_service import ToolAccessDecision


class _Registration:
    def __init__(self, built_in_tools):
        self.built_in_tools = tuple(built_in_tools)


class _ToolService:
    def __init__(self, built_in_tools=None, deny_invocations=()):
        self.built_in_tools = None if built_in_tools is None else tuple(built_in_tools)
        self.deny_invocations = set(deny_invocations)
        self.invocation_checks = []
        self.registration_checks = []

    def registered_tools_for_terminal(self, terminal_id, *, built_in_tool_names=()):
        candidates = tuple(built_in_tool_names)
        self.registration_checks.append((terminal_id, candidates))
        if self.built_in_tools is None:
            allowed = candidates
        else:
            candidate_set = set(candidates)
            allowed = tuple(name for name in self.built_in_tools if name in candidate_set)
        return _Registration(allowed)

    def can_invoke_for_terminal(self, terminal_id, tool_ref, **kwargs):
        self.invocation_checks.append((terminal_id, tool_ref, kwargs))
        if tool_ref in self.deny_invocations:
            return ToolAccessDecision.deny("revoked")
        return ToolAccessDecision.allow()

    def can_invoke_for_terminal_target(
        self,
        terminal_id,
        tool_ref,
        *,
        target_terminal_id,
        **kwargs,
    ):
        self.invocation_checks.append(
            (terminal_id, tool_ref, {"target_terminal_id": target_terminal_id, **kwargs})
        )
        if tool_ref in self.deny_invocations:
            return ToolAccessDecision.deny("revoked")
        return ToolAccessDecision.allow()


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
            "read_inbox_message",
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

    def test_without_terminal_registers_no_tools(self):
        """Missing terminal context fails closed instead of registering locally."""
        pending = [("a", lambda: None, {}), ("b", lambda: None, {}), ("c", lambda: None, {})]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(pending, mcp_instance)

        assert registered == []
        assert mcp_instance.tool.call_count == 0

    def test_tool_service_registers_only_matching_tools_for_terminal(self):
        pending = [("a", lambda: None, {}), ("b", lambda: None, {}), ("c", lambda: None, {})]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(
            pending,
            mcp_instance,
            terminal_id="terminal-1",
            tool_service=_ToolService(("a", "c")),
        )

        assert set(registered) == {"a", "c"}
        assert mcp_instance.tool.call_count == 2

    def test_tool_service_empty_registration_registers_nothing(self):
        pending = [("a", lambda: None, {}), ("b", lambda: None, {})]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(
            pending,
            mcp_instance,
            terminal_id="terminal-1",
            tool_service=_ToolService(()),
        )

        assert registered == []
        assert mcp_instance.tool.call_count == 0

    def test_tool_service_registration_failure_registers_nothing(self):
        pending = [("a", lambda: None, {}), ("b", lambda: None, {})]
        mcp_instance = self._mock_mcp()
        tool_service = MagicMock()
        tool_service.registered_tools_for_terminal.side_effect = RuntimeError("boom")

        registered = server._register_tools(
            pending,
            mcp_instance,
            terminal_id="terminal-1",
            tool_service=tool_service,
        )

        assert registered == []
        assert mcp_instance.tool.call_count == 0

    def test_tool_service_names_not_in_registry_are_silently_ignored(self):
        pending = [("a", lambda: None, {})]
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(
            pending,
            mcp_instance,
            terminal_id="terminal-1",
            tool_service=_ToolService(("a", "typo")),
        )

        assert registered == ["a"]

    def test_tool_service_registration_includes_read_inbox_tool(self):
        mcp_instance = self._mock_mcp()

        registered = server._register_tools(
            server._PENDING_TOOLS,
            mcp_instance,
            terminal_id="terminal-1",
            tool_service=_ToolService(("read_inbox_message",)),
        )

        assert "read_inbox_message" in registered
        assert "reply_to_inbox_message" not in registered

    def test_tool_kwargs_are_forwarded_to_mcp_tool_decorator(self):
        """Tools with decorator kwargs pass them through; tools without kwargs
        passes nothing. Both paths must work."""
        pending = [("with_desc", lambda: None, {"description": "doc"})]
        mcp_instance = self._mock_mcp()

        server._register_tools(
            pending,
            mcp_instance,
            terminal_id="terminal-1",
            tool_service=_ToolService(("with_desc",)),
        )

        mcp_instance.tool.assert_called_once_with(description="doc")

    @pytest.mark.asyncio
    async def test_registered_tool_rechecks_tool_service_at_invocation(self):
        async def callable_tool():
            return {"ok": True}

        pending = [("a", callable_tool, {}), ("b", callable_tool, {})]
        captured = []
        mcp_instance = MagicMock()

        def _decorator(**kwargs):
            def _wrap(fn):
                captured.append(fn)
                return fn

            return _wrap

        mcp_instance.tool.side_effect = _decorator

        tool_service = _ToolService(("a",), deny_invocations=("a",))
        server._register_tools(
            pending,
            mcp_instance,
            terminal_id="terminal-1",
            tool_service=tool_service,
        )

        registered_callable = captured[0]
        with pytest.raises(PermissionError, match="revoked"):
            await registered_callable()
        assert tool_service.invocation_checks == [
            (
                "terminal-1",
                "a",
                {"built_in_tool_names": ("a", "b")},
            )
        ]

    @pytest.mark.asyncio
    async def test_registered_terminate_rechecks_target_terminal_policy(self):
        async def terminate_tool(terminal_id: str):
            return {"terminated": terminal_id}

        captured = []
        mcp_instance = MagicMock()

        def _decorator(**kwargs):
            def _wrap(fn):
                captured.append(fn)
                return fn

            return _wrap

        mcp_instance.tool.side_effect = _decorator

        tool_service = _ToolService(("terminate",))
        server._register_tools(
            [("terminate", terminate_tool, {})],
            mcp_instance,
            terminal_id="caller-terminal",
            tool_service=tool_service,
        )

        result = await captured[0](terminal_id="target-terminal")

        assert result == {"terminated": "target-terminal"}
        assert tool_service.invocation_checks == [
            (
                "caller-terminal",
                "terminate",
                {
                    "target_terminal_id": "target-terminal",
                    "built_in_tool_names": ("terminate",),
                },
            )
        ]

    def test_baton_tools_are_hidden_when_feature_disabled(self, monkeypatch):
        monkeypatch.setenv("CAO_BATON_ENABLED", "false")
        pending = [
            ("send_message", lambda: None, {}),
            ("create_baton", lambda: None, {}),
            ("pass_baton", lambda: None, {}),
        ]
        mcp_instance = self._mock_mcp()
        tool_service = _ToolService(("send_message", "create_baton", "pass_baton"))

        registered = server._register_tools(
            pending,
            mcp_instance,
            terminal_id="terminal-1",
            tool_service=tool_service,
        )

        assert registered == ["send_message"]
        assert tool_service.registration_checks == [
            ("terminal-1", ("send_message",))
        ]
        assert mcp_instance.tool.call_count == 1

    def test_baton_tools_register_when_feature_enabled(self, monkeypatch):
        monkeypatch.setenv("CAO_BATON_ENABLED", "true")
        pending = [
            ("send_message", lambda: None, {}),
            ("create_baton", lambda: None, {}),
        ]
        mcp_instance = self._mock_mcp()
        tool_service = _ToolService(("send_message", "create_baton"))

        registered = server._register_tools(
            pending,
            mcp_instance,
            terminal_id="terminal-1",
            tool_service=tool_service,
        )

        assert registered == ["send_message", "create_baton"]
        assert tool_service.registration_checks == [
            ("terminal-1", ("send_message", "create_baton"))
        ]
        assert mcp_instance.tool.call_count == 2

class TestMainStartupFiltering:
    """Integration of the pieces: main() reads CAO_AGENT_ID, resolves,
    registers. These tests exercise main() with mcp.run() patched so the
    server doesn't actually start."""

    @patch("cli_agent_orchestrator.mcp_server.server.mcp")
    @patch(
        "cli_agent_orchestrator.mcp_server.server.register_provider_mediated_mcp_tools_for_terminal"
    )
    @patch("cli_agent_orchestrator.mcp_server.server._register_tools")
    def test_main_passes_terminal_context_to_toolservice_registration(
        self, mock_register, mock_register_provider, mock_mcp, monkeypatch
    ):
        monkeypatch.setenv("CAO_AGENT_ID", "agent-xyz")
        monkeypatch.setattr(
            server.db_module,
            "list_terminals_by_agent",
            lambda agent_id: [{"id": "term-xyz", "agent_id": "agent-xyz"}]
            if agent_id == "agent-xyz"
            else [],
        )
        mock_register.return_value = ["assign", "send_message"]
        mock_register_provider.return_value = []

        server.main()

        args = mock_register.call_args[0]
        assert args[0] == server._PENDING_TOOLS
        assert args[1] == mock_mcp
        assert mock_register.call_args.kwargs["terminal_id"] == "term-xyz"
        assert mock_register.call_args.kwargs["tool_service"] is not None
        mock_register_provider.assert_called_once()
        assert mock_register_provider.call_args.kwargs["terminal_id"] == "term-xyz"
        assert mock_register_provider.call_args.kwargs[
            "reserved_tool_names"
        ] == server.built_in_cao_tool_names()
        mock_mcp.run.assert_called_once()

    @patch("cli_agent_orchestrator.mcp_server.server.mcp")
    @patch(
        "cli_agent_orchestrator.mcp_server.server.register_provider_mediated_mcp_tools_for_terminal"
    )
    @patch("cli_agent_orchestrator.mcp_server.server._register_tools")
    def test_main_without_cao_terminal_id_fails_closed(
        self, mock_register, mock_register_provider, mock_mcp, monkeypatch
    ):
        """If startup has no terminal context, registration remains fail-closed."""
        monkeypatch.delenv("CAO_AGENT_ID", raising=False)
        mock_register.return_value = []

        server.main()

        args = mock_register.call_args[0]
        assert args[1] == mock_mcp
        assert mock_register.call_args.kwargs["terminal_id"] is None
        mock_register_provider.assert_not_called()
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

    def test_provider_inbox_impl_still_importable(self):
        from cli_agent_orchestrator.mcp_server.server import _read_inbox_message_impl

        assert callable(_read_inbox_message_impl)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

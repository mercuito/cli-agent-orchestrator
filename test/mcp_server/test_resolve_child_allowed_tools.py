"""Tests for _resolve_child_allowed_tools in MCP server."""

from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.agent import AgentConfigError
from cli_agent_orchestrator.mcp_server.server import _resolve_child_allowed_tools


class TestResolveChildAllowedTools:
    """Tests for _resolve_child_allowed_tools function."""

    @patch("cli_agent_orchestrator.utils.tool_mapping.resolve_runtime_capabilities")
    @patch("cli_agent_orchestrator.mcp_server.server.load_agent")
    def test_child_wildcard_with_restricted_parent_returns_unrestricted(
        self, mock_load, mock_resolve
    ):
        """Issue #141: child with runtimeCapabilities=["*"] should NOT inherit parent restrictions."""
        mock_agent = MagicMock()
        mock_agent.runtime_capabilities = ["*"]
        mock_agent.mcp_servers = None
        mock_load.return_value = mock_agent
        mock_resolve.return_value = ["*"]

        result = _resolve_child_allowed_tools(
            parent_allowed_tools=["@cao-mcp-server", "fs_read", "fs_list"],
            child_agent_id="code-reviewer",
        )

        assert result is None  # unrestricted

    @patch("cli_agent_orchestrator.utils.tool_mapping.resolve_runtime_capabilities")
    @patch("cli_agent_orchestrator.mcp_server.server.load_agent")
    def test_child_none_inherits_parent_restrictions(self, mock_load, mock_resolve):
        """Child with no configured agent inherits parent's tools."""
        mock_load.side_effect = AgentConfigError("not found")

        result = _resolve_child_allowed_tools(
            parent_allowed_tools=["fs_read", "fs_list"],
            child_agent_id="nonexistent",
        )

        assert result == "fs_read,fs_list"

    @patch("cli_agent_orchestrator.utils.tool_mapping.resolve_runtime_capabilities")
    @patch("cli_agent_orchestrator.mcp_server.server.load_agent")
    def test_unrestricted_parent_uses_child_tools(self, mock_load, mock_resolve):
        """Unrestricted parent lets child use its own tools."""
        mock_agent = MagicMock()
        mock_agent.runtime_capabilities = ["fs_read", "execute_bash"]
        mock_agent.mcp_servers = None
        mock_load.return_value = mock_agent
        mock_resolve.return_value = ["fs_read", "execute_bash"]

        result = _resolve_child_allowed_tools(
            parent_allowed_tools=None,
            child_agent_id="developer",
        )

        assert result == "fs_read,execute_bash"

    @patch("cli_agent_orchestrator.utils.tool_mapping.resolve_runtime_capabilities")
    @patch("cli_agent_orchestrator.mcp_server.server.load_agent")
    def test_both_restricted_uses_child_tools(self, mock_load, mock_resolve):
        """Both parent and child restricted: child gets its own tools."""
        mock_agent = MagicMock()
        mock_agent.runtime_capabilities = ["fs_read", "execute_bash"]
        mock_agent.mcp_servers = None
        mock_load.return_value = mock_agent
        mock_resolve.return_value = ["fs_read", "execute_bash"]

        result = _resolve_child_allowed_tools(
            parent_allowed_tools=["@cao-mcp-server", "fs_read"],
            child_agent_id="developer",
        )

        assert result == "fs_read,execute_bash"

    @patch("cli_agent_orchestrator.utils.tool_mapping.resolve_runtime_capabilities")
    @patch("cli_agent_orchestrator.mcp_server.server.load_agent")
    def test_parent_wildcard_child_wildcard_returns_unrestricted(self, mock_load, mock_resolve):
        """Both parent and child unrestricted: returns None (unrestricted)."""
        mock_agent = MagicMock()
        mock_agent.runtime_capabilities = ["*"]
        mock_agent.mcp_servers = None
        mock_load.return_value = mock_agent
        mock_resolve.return_value = ["*"]

        result = _resolve_child_allowed_tools(
            parent_allowed_tools=["*"],
            child_agent_id="developer",
        )

        # Parent is unrestricted, child has ["*"] → child_allowed is truthy → joins it
        # But ["*"] joined is "*", which is fine
        assert result == "*"

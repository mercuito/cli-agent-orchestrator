"""Tests for the `terminate` MCP tool.

``terminate`` lets a supervisor-style agent gracefully shut down an existing
terminal (typically a worker it spawned via ``assign``). It wraps the
``POST /terminals/{id}/exit`` REST endpoint that ``handoff`` already uses
for its auto-cleanup step.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests


class TestTerminateImpl:
    @patch("cli_agent_orchestrator.mcp_server.server.requests.post")
    def test_terminate_posts_exit_endpoint(self, mock_post):
        """Happy path: POST /terminals/<id>/exit and return success."""
        from cli_agent_orchestrator.mcp_server.server import _terminate_impl

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = _terminate_impl("abc123")

        assert result["success"] is True
        assert "abc123" in result["message"]
        mock_post.assert_called_once()
        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/terminals/abc123/exit")

    @patch("cli_agent_orchestrator.mcp_server.server.requests.post")
    def test_terminate_unknown_terminal_returns_structured_error(self, mock_post):
        """404 from cao-server must become a structured error, not a raised exception.

        MCP tool callers rely on the dict payload to know what happened.
        Raising would surface as an opaque tool-call failure.
        """
        from cli_agent_orchestrator.mcp_server.server import _terminate_impl

        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = requests.HTTPError("404 Not Found")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_post.return_value = mock_response

        result = _terminate_impl("does-not-exist")

        assert result["success"] is False
        assert "error" in result
        assert "does-not-exist" in result.get("terminal_id", "")

    @patch("cli_agent_orchestrator.mcp_server.server.requests.post")
    def test_terminate_server_error_returns_structured_error(self, mock_post):
        """500 from cao-server must also degrade gracefully."""
        from cli_agent_orchestrator.mcp_server.server import _terminate_impl

        mock_response = MagicMock()
        mock_response.status_code = 500
        http_error = requests.HTTPError("500 Internal Server Error")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_post.return_value = mock_response

        result = _terminate_impl("abc123")

        assert result["success"] is False
        assert "error" in result

    @patch("cli_agent_orchestrator.mcp_server.server.requests.post")
    def test_terminate_network_failure_returns_structured_error(self, mock_post):
        """Connection refused etc. must not crash the tool call."""
        from cli_agent_orchestrator.mcp_server.server import _terminate_impl

        mock_post.side_effect = requests.ConnectionError("Connection refused")

        result = _terminate_impl("abc123")

        assert result["success"] is False
        assert "error" in result


class TestTerminateMcpTool:
    @pytest.mark.asyncio
    @patch("cli_agent_orchestrator.mcp_server.server._terminate_impl")
    async def test_terminate_tool_delegates_to_impl(self, mock_impl):
        """The @mcp.tool() wrapper should just forward to _terminate_impl."""
        from cli_agent_orchestrator.mcp_server import server

        mock_impl.return_value = {"success": True, "message": "ok"}

        result = await server.terminate(terminal_id="abc123")

        assert result == {"success": True, "message": "ok"}
        mock_impl.assert_called_once_with("abc123")

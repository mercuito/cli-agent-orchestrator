"""Tests for durable-agent terminal creation in the MCP server."""

import os
from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.constants import API_BASE_URL
from cli_agent_orchestrator.mcp_server import server


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@patch("cli_agent_orchestrator.mcp_server.server.requests.get")
@patch("cli_agent_orchestrator.mcp_server.server.requests.post")
def test_create_terminal_starts_named_agent(mock_post, mock_get):
    mock_post.return_value = _response({"terminal": {"id": "terminal-1", "provider": "codex"}})

    terminal_id, provider = server._create_terminal("implementation_partner")

    assert (terminal_id, provider) == ("terminal-1", "codex")
    mock_post.assert_called_once_with(f"{API_BASE_URL}/agents/implementation_partner/start")
    mock_get.assert_not_called()


@patch("cli_agent_orchestrator.mcp_server.server.requests.get")
@patch("cli_agent_orchestrator.mcp_server.server.requests.post")
def test_create_terminal_uses_agent_start_from_existing_terminal(mock_post, mock_get):
    mock_post.return_value = _response(
        {"terminal": {"id": "terminal-2", "provider": "claude_code"}}
    )

    with patch.dict(os.environ, {"CAO_TERMINAL_ID": "supervisor-1"}):
        terminal_id, provider = server._create_terminal("reviewer")

    assert (terminal_id, provider) == ("terminal-2", "claude_code")
    mock_post.assert_called_once_with(f"{API_BASE_URL}/agents/reviewer/start")
    mock_get.assert_not_called()


@patch("cli_agent_orchestrator.mcp_server.server.requests.post")
def test_create_terminal_rejects_working_directory_override(mock_post):
    with pytest.raises(ValueError, match="configure the agent workdir"):
        server._create_terminal("reviewer", working_directory="/tmp/project")

    mock_post.assert_not_called()

"""Tests for MCP server handoff logic."""

import asyncio
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig
from cli_agent_orchestrator.mcp_server.server import _handoff_impl


def _team_agent(agent_id: str) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/tmp",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(team="cao_delivery"),
    )


@contextmanager
def _same_team_guard(
    sender_terminal_id: str,
    *,
    sender_agent_id: str = "supervisor",
    receiver_agent_id: str = "developer",
):
    registry = AgentRegistry(
        {
            sender_agent_id: _team_agent(sender_agent_id),
            receiver_agent_id: _team_agent(receiver_agent_id),
        }
    )

    def _metadata(terminal_id: str):
        if terminal_id == sender_terminal_id:
            return {"id": terminal_id, "agent_id": sender_agent_id}
        return {"id": terminal_id, "agent_id": receiver_agent_id}

    with (
        patch(
            "cli_agent_orchestrator.mcp_server.server.load_agent_registry", return_value=registry
        ),
        patch(
            "cli_agent_orchestrator.mcp_server.server.db_module.get_terminal_metadata",
            side_effect=_metadata,
        ),
    ):
        yield


class TestHandoffMessageContext:
    """Tests for handoff message context prepended to worker agents."""

    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    @patch("cli_agent_orchestrator.mcp_server.server.wait_until_terminal_status")
    @patch("cli_agent_orchestrator.mcp_server.server._create_terminal")
    def test_codex_provider_prepends_handoff_context(self, mock_create, mock_wait, mock_send):
        """Codex provider should prepend [CAO Handoff] with supervisor ID."""
        mock_create.return_value = ("dev-terminal-1", "codex")
        # First call: wait for IDLE (True), second call: wait for COMPLETED (True)
        mock_wait.side_effect = [True, True]
        mock_send.return_value = None

        with (
            patch.dict(os.environ, {"CAO_TERMINAL_ID": "supervisor-abc123"}),
            _same_team_guard("supervisor-abc123"),
        ):
            with patch("cli_agent_orchestrator.mcp_server.server.requests") as mock_requests:
                mock_response = MagicMock()
                mock_response.json.return_value = {"output": "task done"}
                mock_response.raise_for_status.return_value = None
                mock_requests.get.return_value = mock_response
                mock_requests.post.return_value = mock_response

                result = asyncio.get_event_loop().run_until_complete(
                    _handoff_impl("developer", "Implement hello world")
                )

        # Verify _send_to_inbox was called with the handoff prefix
        mock_send.assert_called_once()
        sent_message = mock_send.call_args[0][1]
        assert sent_message.startswith("[CAO Handoff]")
        assert "supervisor-abc123" in sent_message
        assert "Implement hello world" in sent_message
        assert "Do NOT use send_message" in sent_message

    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    @patch("cli_agent_orchestrator.mcp_server.server.wait_until_terminal_status")
    @patch("cli_agent_orchestrator.mcp_server.server._create_terminal")
    def test_claude_code_provider_no_handoff_context(self, mock_create, mock_wait, mock_send):
        """Claude Code provider should NOT prepend any handoff context."""
        mock_create.return_value = ("dev-terminal-2", "claude_code")
        mock_wait.side_effect = [True, True]
        mock_send.return_value = None

        with (
            patch.dict(os.environ, {"CAO_TERMINAL_ID": "supervisor-abc123"}),
            _same_team_guard("supervisor-abc123"),
            patch("cli_agent_orchestrator.mcp_server.server.requests") as mock_requests,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = {"output": "task done"}
            mock_response.raise_for_status.return_value = None
            mock_requests.get.return_value = mock_response
            mock_requests.post.return_value = mock_response

            result = asyncio.get_event_loop().run_until_complete(
                _handoff_impl("developer", "Implement hello world")
            )

        # Verify message was sent unchanged
        mock_send.assert_called_once()
        sent_message = mock_send.call_args[0][1]
        assert sent_message == "Implement hello world"

    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    @patch("cli_agent_orchestrator.mcp_server.server.wait_until_terminal_status")
    @patch("cli_agent_orchestrator.mcp_server.server._create_terminal")
    def test_kiro_cli_provider_no_handoff_context(self, mock_create, mock_wait, mock_send):
        """Kiro CLI provider should NOT prepend any handoff context."""
        mock_create.return_value = ("dev-terminal-3", "kiro_cli")
        mock_wait.side_effect = [True, True]
        mock_send.return_value = None

        with (
            patch.dict(os.environ, {"CAO_TERMINAL_ID": "supervisor-abc123"}),
            _same_team_guard("supervisor-abc123"),
            patch("cli_agent_orchestrator.mcp_server.server.requests") as mock_requests,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = {"output": "task done"}
            mock_response.raise_for_status.return_value = None
            mock_requests.get.return_value = mock_response
            mock_requests.post.return_value = mock_response

            result = asyncio.get_event_loop().run_until_complete(
                _handoff_impl("developer", "Implement hello world")
            )

        mock_send.assert_called_once()
        sent_message = mock_send.call_args[0][1]
        assert sent_message == "Implement hello world"

    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    @patch("cli_agent_orchestrator.mcp_server.server.wait_until_terminal_status")
    @patch("cli_agent_orchestrator.mcp_server.server._create_terminal")
    def test_codex_handoff_context_includes_supervisor_id_from_env(
        self, mock_create, mock_wait, mock_send
    ):
        """Supervisor terminal ID should come from CAO_TERMINAL_ID env var."""
        mock_create.return_value = ("dev-terminal-4", "codex")
        mock_wait.side_effect = [True, True]
        mock_send.return_value = None

        with (
            patch.dict(os.environ, {"CAO_TERMINAL_ID": "sup-xyz789"}),
            _same_team_guard("sup-xyz789"),
        ):
            with patch("cli_agent_orchestrator.mcp_server.server.requests") as mock_requests:
                mock_response = MagicMock()
                mock_response.json.return_value = {"output": "done"}
                mock_response.raise_for_status.return_value = None
                mock_requests.get.return_value = mock_response
                mock_requests.post.return_value = mock_response

                asyncio.get_event_loop().run_until_complete(
                    _handoff_impl("developer", "Build feature X")
                )

        sent_message = mock_send.call_args[0][1]
        assert "sup-xyz789" in sent_message
        assert "Build feature X" in sent_message

    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    @patch("cli_agent_orchestrator.mcp_server.server.wait_until_terminal_status")
    @patch("cli_agent_orchestrator.mcp_server.server._create_terminal")
    def test_codex_handoff_context_fallback_when_no_env(self, mock_create, mock_wait, mock_send):
        """When CAO_TERMINAL_ID is not set, team-aware handoff is rejected."""
        mock_create.return_value = ("dev-terminal-5", "codex")
        mock_wait.side_effect = [True, True]
        mock_send.return_value = None

        with patch.dict(os.environ, {}, clear=True):
            result = asyncio.get_event_loop().run_until_complete(
                _handoff_impl("developer", "Do task")
            )

        assert result.success is False
        assert "sender terminal is unknown" in result.message
        mock_create.assert_not_called()
        mock_send.assert_not_called()

    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    @patch("cli_agent_orchestrator.mcp_server.server.wait_until_terminal_status")
    @patch("cli_agent_orchestrator.mcp_server.server._create_terminal")
    def test_codex_handoff_original_message_preserved(self, mock_create, mock_wait, mock_send):
        """Original message should appear in full after the handoff prefix."""
        mock_create.return_value = ("dev-terminal-6", "codex")
        mock_wait.side_effect = [True, True]
        mock_send.return_value = None

        original = "Implement the task described in /path/to/task.md. Write tests."
        with (
            patch.dict(os.environ, {"CAO_TERMINAL_ID": "sup-111"}),
            _same_team_guard("sup-111"),
        ):
            with patch("cli_agent_orchestrator.mcp_server.server.requests") as mock_requests:
                mock_response = MagicMock()
                mock_response.json.return_value = {"output": "done"}
                mock_response.raise_for_status.return_value = None
                mock_requests.get.return_value = mock_response
                mock_requests.post.return_value = mock_response

                asyncio.get_event_loop().run_until_complete(_handoff_impl("developer", original))

        sent_message = mock_send.call_args[0][1]
        assert sent_message.endswith(original)

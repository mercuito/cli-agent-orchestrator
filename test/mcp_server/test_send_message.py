"""Tests for send_message MCP tool."""

from contextlib import contextmanager
import os
from unittest.mock import patch

import pytest

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig


def _team_agent(agent_id: str, team: str) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/tmp",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(team=team),
    )


@contextmanager
def _terminal_team_guard(*, sender_team: str = "cao_delivery", receiver_team: str = "cao_delivery"):
    registry = AgentRegistry(
        {
            "sender": _team_agent("sender", sender_team),
            "receiver": _team_agent("receiver", receiver_team),
        }
    )

    def _metadata(terminal_id: str):
        if terminal_id == "sender-term":
            return {"id": terminal_id, "agent_id": "sender"}
        if terminal_id == "receiver-term":
            return {"id": terminal_id, "agent_id": "receiver"}
        return None

    with (
        patch("cli_agent_orchestrator.mcp_server.server.load_agent_registry", return_value=registry),
        patch(
            "cli_agent_orchestrator.mcp_server.server.db_module.get_terminal_metadata",
            side_effect=_metadata,
        ),
    ):
        yield


class TestSendMessageSenderIdInjection:
    """Tests for sender ID injection in _send_message_impl."""

    @patch("cli_agent_orchestrator.mcp_server.server.ENABLE_SENDER_ID_INJECTION", True)
    @patch("cli_agent_orchestrator.mcp_server.server._terminal_can_invoke_builtin")
    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    def test_send_message_appends_sender_id_when_injection_enabled(
        self, mock_inbox, mock_can_invoke
    ):
        """When injection is enabled, send_message should append sender ID suffix."""
        from cli_agent_orchestrator.mcp_server.server import _send_message_impl

        mock_inbox.return_value = {"success": True}
        mock_can_invoke.return_value = True

        with patch.dict(os.environ, {"CAO_TERMINAL_ID": "sender-xyz"}):
            result = _send_message_impl("receiver-123", "Here are the results")

        sent_message = mock_inbox.call_args[0][1]
        assert sent_message.startswith("Here are the results")
        assert "[Message from terminal sender-xyz" in sent_message
        assert "Use send_message MCP tool for any follow-up work.]" in sent_message

    @patch("cli_agent_orchestrator.mcp_server.server.ENABLE_SENDER_ID_INJECTION", True)
    @patch("cli_agent_orchestrator.mcp_server.server._terminal_can_invoke_builtin")
    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    def test_send_message_does_not_promise_hidden_send_message_tool(
        self, mock_inbox, mock_can_invoke
    ):
        """Injection should not promise send_message when receiver cannot invoke it."""
        from cli_agent_orchestrator.mcp_server.server import _send_message_impl

        mock_inbox.return_value = {"success": True}
        mock_can_invoke.return_value = False

        with patch.dict(os.environ, {"CAO_TERMINAL_ID": "sender-xyz"}):
            result = _send_message_impl("receiver-123", "Here are the results")

        sent_message = mock_inbox.call_args[0][1]
        assert result == {"success": True}
        assert sent_message.endswith("[Message from terminal sender-xyz.]")
        assert "Use send_message MCP tool" not in sent_message

    @patch("cli_agent_orchestrator.mcp_server.server.ENABLE_SENDER_ID_INJECTION", False)
    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    def test_send_message_no_suffix_when_injection_disabled(self, mock_inbox):
        """When injection is disabled, send_message should pass the message unchanged."""
        from cli_agent_orchestrator.mcp_server.server import _send_message_impl

        mock_inbox.return_value = {"success": True}

        with patch.dict(os.environ, {"CAO_TERMINAL_ID": "sender-xyz"}):
            result = _send_message_impl("receiver-123", "Here are the results")

        sent_message = mock_inbox.call_args[0][1]
        assert sent_message == "Here are the results"

    @patch("cli_agent_orchestrator.mcp_server.server.ENABLE_SENDER_ID_INJECTION", True)
    @patch("cli_agent_orchestrator.mcp_server.server._terminal_can_invoke_builtin")
    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    def test_send_message_sender_id_fallback_unknown(self, mock_inbox, mock_can_invoke):
        """When CAO_TERMINAL_ID is not set, suffix should use 'unknown'."""
        from cli_agent_orchestrator.mcp_server.server import _send_message_impl

        mock_inbox.return_value = {"success": True}
        mock_can_invoke.return_value = True

        with patch.dict(os.environ, {}, clear=True):
            result = _send_message_impl("receiver-123", "Status update")

        sent_message = mock_inbox.call_args[0][1]
        assert "[Message from terminal unknown" in sent_message

    @patch("cli_agent_orchestrator.mcp_server.server.ENABLE_SENDER_ID_INJECTION", True)
    @patch("cli_agent_orchestrator.mcp_server.server._terminal_can_invoke_builtin")
    @patch("cli_agent_orchestrator.mcp_server.server._send_to_inbox")
    def test_send_message_suffix_is_appended_not_prepended(self, mock_inbox, mock_can_invoke):
        """The sender ID should be a suffix, not a prefix."""
        from cli_agent_orchestrator.mcp_server.server import _send_message_impl

        mock_inbox.return_value = {"success": True}
        mock_can_invoke.return_value = True
        original = "Task complete. Here are the deliverables."

        with patch.dict(os.environ, {"CAO_TERMINAL_ID": "sender-999"}):
            _send_message_impl("receiver-123", original)

        sent_message = mock_inbox.call_args[0][1]
        assert sent_message.startswith(original)
        assert sent_message.index("[Message from terminal") > len(original)


class TestSendMessageTeamPolicy:
    def test_send_to_inbox_rejects_cross_team_before_http_post(self):
        from cli_agent_orchestrator.mcp_server.server import _send_to_inbox

        with (
            patch.dict(os.environ, {"CAO_TERMINAL_ID": "sender-term"}),
            _terminal_team_guard(receiver_team="other_team"),
            patch("cli_agent_orchestrator.mcp_server.server.requests.post") as mock_post,
        ):
            with pytest.raises(Exception) as exc_info:
                _send_to_inbox("receiver-term", "hello")

        assert "Workspace team collaboration rejected" in str(exc_info.value)
        mock_post.assert_not_called()

    def test_send_to_inbox_allows_same_team_after_policy_check(self):
        from cli_agent_orchestrator.mcp_server.server import _send_to_inbox

        with (
            patch.dict(os.environ, {"CAO_TERMINAL_ID": "sender-term"}),
            _terminal_team_guard(),
            patch("cli_agent_orchestrator.mcp_server.server.requests.post") as mock_post,
        ):
            response = mock_post.return_value
            response.json.return_value = {"success": True}
            response.raise_for_status.return_value = None

            result = _send_to_inbox("receiver-term", "hello")

        assert result == {"success": True}
        mock_post.assert_called_once()

"""Tests for terminal-related API endpoints including working directory and exit."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from cli_agent_orchestrator.agent import AgentConfigError
from cli_agent_orchestrator.api.main import app
from cli_agent_orchestrator.models.terminal import Terminal


class TestTerminalWebsocketAuthorization:
    def _websocket(self, *, host: str, query_params: dict[str, str] | None = None):
        return SimpleNamespace(client=SimpleNamespace(host=host), query_params=query_params or {})

    def test_loopback_websocket_is_authorized_without_token(self):
        from cli_agent_orchestrator.api import main

        websocket = self._websocket(host="127.0.0.1")

        assert main._terminal_ws_authorized(websocket, "term-1")

    def test_non_loopback_websocket_requires_valid_terminal_token(self):
        from cli_agent_orchestrator.api import main

        websocket = self._websocket(host="100.81.152.85")

        assert not main._terminal_ws_authorized(websocket, "term-1")

    def test_non_loopback_websocket_accepts_valid_terminal_token(self, monkeypatch):
        from cli_agent_orchestrator.api import main

        def validate(token: str, terminal_id: str) -> bool:
            return token == "signed-token" and terminal_id == "term-1"

        monkeypatch.setattr(main, "validate_terminal_dashboard_token", validate)
        websocket = self._websocket(
            host="100.81.152.85", query_params={"terminal_token": "signed-token"}
        )

        assert main._terminal_ws_authorized(websocket, "term-1")

    def test_non_loopback_websocket_rejects_token_for_different_terminal(self, monkeypatch):
        from cli_agent_orchestrator.api import main

        monkeypatch.setattr(
            main, "validate_terminal_dashboard_token", lambda _token, _terminal_id: False
        )
        websocket = self._websocket(
            host="100.81.152.85", query_params={"terminal_token": "signed-token"}
        )

        assert not main._terminal_ws_authorized(websocket, "term-2")


class TestTerminalWebsocketEnvironment:
    def test_tmux_attach_environment_replaces_dumb_term(self, monkeypatch):
        from cli_agent_orchestrator.api import main

        monkeypatch.setenv("TERM", "dumb")

        assert main._tmux_attach_environment()["TERM"] == "xterm-256color"

    def test_tmux_attach_environment_preserves_capable_term(self, monkeypatch):
        from cli_agent_orchestrator.api import main

        monkeypatch.setenv("TERM", "screen-256color")

        assert main._tmux_attach_environment()["TERM"] == "screen-256color"


class TestAgentRuntimeTerminalEndpoint:
    def test_resolves_agent_to_current_terminal_with_token(self, client, monkeypatch):
        from cli_agent_orchestrator.api import main

        agent_manager = MagicMock()
        agent_manager.status_for_agent.return_value = SimpleNamespace(active_terminal_id="abcd1234")

        monkeypatch.setattr(main, "default_agent_manager", lambda: agent_manager)
        monkeypatch.setattr(
            main, "validate_agent_dashboard_token", lambda token, agent_id: token == "agent-token"
        )
        monkeypatch.setattr(
            main, "create_terminal_dashboard_token", lambda terminal_id: "signed-token"
        )
        monkeypatch.setattr(
            main.terminal_service,
            "get_terminal",
            lambda terminal_id: {
                "id": terminal_id,
                "name": "developer-1234",
                "provider": "codex",
                "session_name": "cao-linear-discovery-partner",
                "agent_id": "discovery_partner",
                "workspace_context_id": "default",
                "allowed_tools": None,
                "status": "idle",
                "last_active": None,
            },
        )

        response = client.get("/agents/runtime/discovery_partner/terminal?agent_token=agent-token")

        assert response.status_code == 200
        assert response.json()["terminal"]["id"] == "abcd1234"
        assert response.json()["terminal"]["agent_id"] == "discovery_partner"
        assert response.json()["terminal_token"] == "signed-token"
        agent_manager.status_for_agent.assert_called_once_with("discovery_partner")

    def test_returns_404_when_agent_has_no_running_terminal(self, client, monkeypatch):
        from cli_agent_orchestrator.api import main

        agent_manager = MagicMock()
        agent_manager.status_for_agent.return_value = SimpleNamespace(active_terminal_id=None)

        monkeypatch.setattr(main, "default_agent_manager", lambda: agent_manager)
        monkeypatch.setattr(
            main, "validate_agent_dashboard_token", lambda token, agent_id: token == "agent-token"
        )

        response = client.get("/agents/runtime/discovery_partner/terminal?agent_token=agent-token")

        assert response.status_code == 404
        assert "no running terminal" in response.json()["detail"]

    def test_returns_404_for_unknown_agent(self, client, monkeypatch):
        from cli_agent_orchestrator.api import main

        monkeypatch.setattr(
            main,
            "validate_agent_dashboard_token",
            lambda token, agent_id: token == "agent-token",
        )
        agent_manager = MagicMock()
        agent_manager.status_for_agent.side_effect = AgentConfigError("Unknown CAO agent")
        monkeypatch.setattr(main, "default_agent_manager", lambda: agent_manager)

        response = client.get("/agents/runtime/missing/terminal?agent_token=agent-token")

        assert response.status_code == 404
        assert "Unknown CAO agent" in response.json()["detail"]

    def test_rejects_non_loopback_agent_resolution_without_valid_agent_token(
        self, client, monkeypatch
    ):
        from cli_agent_orchestrator.api import main

        agent_manager = MagicMock()
        monkeypatch.setattr(main, "default_agent_manager", lambda: agent_manager)
        monkeypatch.setattr(main, "validate_agent_dashboard_token", lambda token, agent_id: False)

        response = client.get("/agents/runtime/discovery_partner/terminal")

        assert response.status_code == 403
        agent_manager.status_for_agent.assert_not_called()

    def test_resolves_agent_from_workspace_provider_mapping(self, client, monkeypatch):
        from cli_agent_orchestrator.api import main

        agent_manager = MagicMock()
        agent_manager.status_for_agent.return_value = SimpleNamespace(active_terminal_id="abcd1234")

        monkeypatch.setattr(main, "default_agent_manager", lambda: agent_manager)
        monkeypatch.setattr(
            main, "validate_agent_dashboard_token", lambda token, agent_id: token == "agent-token"
        )
        monkeypatch.setattr(
            main, "create_terminal_dashboard_token", lambda terminal_id: "signed-token"
        )
        monkeypatch.setattr(
            main.terminal_service,
            "get_terminal",
            lambda terminal_id: {
                "id": terminal_id,
                "name": "developer-1234",
                "provider": "codex",
                "session_name": "cao-linear-discovery-partner",
                "agent_id": "discovery_partner",
                "workspace_context_id": "default",
                "allowed_tools": None,
                "status": "idle",
                "last_active": None,
            },
        )

        response = client.get("/agents/runtime/discovery_partner/terminal?agent_token=agent-token")

        assert response.status_code == 200
        assert response.json()["terminal"]["id"] == "abcd1234"
        agent_manager.status_for_agent.assert_called_once_with("discovery_partner")


class TestWorkingDirectoryEndpoint:
    """Test GET /terminals/{terminal_id}/working-directory endpoint."""

    def test_get_working_directory_success(self, client):
        """Test successful retrieval of working directory."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            mock_svc.get_working_directory.return_value = "/home/user/project"

            response = client.get("/terminals/abcd1234/working-directory")

            assert response.status_code == 200
            data = response.json()
            assert data["working_directory"] == "/home/user/project"
            mock_svc.get_working_directory.assert_called_once_with("abcd1234")

    def test_get_working_directory_returns_none(self, client):
        """Test when working directory is unavailable."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            mock_svc.get_working_directory.return_value = None

            response = client.get("/terminals/abcd1234/working-directory")

            assert response.status_code == 200
            assert response.json()["working_directory"] is None

    def test_get_working_directory_terminal_not_found(self, client):
        """Test 404 when terminal doesn't exist."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            mock_svc.get_working_directory.side_effect = ValueError("Terminal 'abcd5678' not found")

            response = client.get("/terminals/abcd5678/working-directory")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_get_working_directory_server_error(self, client):
        """Test 500 on internal error."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            mock_svc.get_working_directory.side_effect = Exception("TMux error")

            response = client.get("/terminals/abcd1234/working-directory")

            assert response.status_code == 500
            assert "Failed to get working directory" in response.json()["detail"]

    def test_get_working_directory_internal_error(self, client):
        """Test 500 when internal error occurs."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            mock_svc.get_working_directory.side_effect = RuntimeError("Internal service error")

            response = client.get("/terminals/abcd1234/working-directory")

            assert response.status_code == 500
            assert "Failed to get working directory" in response.json()["detail"]


class TestSessionCreationWithWorkingDirectory:
    """Removed anonymous session creation endpoint."""

    def test_create_session_passes_working_directory(self, client, tmp_path):
        """POST /sessions no longer creates anonymous terminals."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            response = client.post(
                "/sessions",
                params={
                    "provider": "q_cli",
                    "agent_id": "developer",
                    "working_directory": str(tmp_path),
                },
            )

            assert response.status_code == 405
            mock_svc.create_terminal.assert_not_called()

    def test_create_session_with_working_directory(self, client):
        """POST /sessions remains removed even with working_directory."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            response = client.post(
                "/sessions",
                params={
                    "provider": "q_cli",
                    "agent_id": "developer",
                    "working_directory": "/custom/path",
                },
            )

            assert response.status_code == 405
            mock_svc.create_terminal.assert_not_called()


class TestTerminalCreationWithWorkingDirectory:
    """Removed anonymous terminal creation endpoint."""

    def test_create_terminal_passes_working_directory(self, client, tmp_path):
        """POST /sessions/{session}/terminals no longer creates terminals."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            response = client.post(
                "/sessions/test-session/terminals",
                params={
                    "provider": "q_cli",
                    "agent_id": "analyst",
                    "working_directory": str(tmp_path),
                },
            )

            assert response.status_code == 405
            mock_svc.create_terminal.assert_not_called()

    def test_create_terminal_in_session_with_working_directory(self, client):
        """POST /sessions/{session}/terminals remains removed."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            response = client.post(
                "/sessions/test-session/terminals",
                params={
                    "provider": "q_cli",
                    "agent_id": "analyst",
                    "working_directory": "/session/path",
                },
            )

            assert response.status_code == 405
            mock_svc.create_terminal.assert_not_called()


class TestExitTerminalEndpoint:
    """Test POST /terminals/{terminal_id}/exit endpoint.

    Verifies that text commands (e.g., /exit) are sent via send_input()
    and tmux special key sequences (e.g., C-d) are sent via send_special_key().
    """

    def test_exit_terminal_text_command(self, client):
        """Text exit commands (e.g., /exit) should use send_input."""
        mock_provider = MagicMock()
        mock_provider.exit_cli.return_value = "/exit"

        with (
            patch("cli_agent_orchestrator.api.main.provider_manager") as mock_pm,
            patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc,
        ):
            mock_pm.get_provider.return_value = mock_provider

            response = client.post("/terminals/abcd1234/exit")

            assert response.status_code == 200
            assert response.json() == {"success": True}
            mock_svc.send_input.assert_called_once_with("abcd1234", "/exit")
            mock_svc.send_special_key.assert_not_called()

    def test_exit_terminal_special_key(self, client):
        """Tmux key sequences (e.g., C-d) should use send_special_key."""
        mock_provider = MagicMock()
        mock_provider.exit_cli.return_value = "C-d"

        with (
            patch("cli_agent_orchestrator.api.main.provider_manager") as mock_pm,
            patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc,
        ):
            mock_pm.get_provider.return_value = mock_provider

            response = client.post("/terminals/abcd1234/exit")

            assert response.status_code == 200
            assert response.json() == {"success": True}
            mock_svc.send_special_key.assert_called_once_with("abcd1234", "C-d")
            mock_svc.send_input.assert_not_called()

    def test_exit_terminal_meta_key(self, client):
        """Meta key sequences (M-x) should also use send_special_key."""
        mock_provider = MagicMock()
        mock_provider.exit_cli.return_value = "M-x"

        with (
            patch("cli_agent_orchestrator.api.main.provider_manager") as mock_pm,
            patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc,
        ):
            mock_pm.get_provider.return_value = mock_provider

            response = client.post("/terminals/abcd1234/exit")

            assert response.status_code == 200
            mock_svc.send_special_key.assert_called_once_with("abcd1234", "M-x")
            mock_svc.send_input.assert_not_called()

    def test_exit_terminal_provider_not_found(self, client):
        """Should return 404 when provider is not found."""
        with patch("cli_agent_orchestrator.api.main.provider_manager") as mock_pm:
            mock_pm.get_provider.side_effect = ValueError("Terminal not found in database")

            response = client.post("/terminals/deadbeef/exit")

            assert response.status_code == 404

    def test_exit_terminal_server_error(self, client):
        """Should return 500 on unexpected errors."""
        mock_provider = MagicMock()
        mock_provider.exit_cli.return_value = "/exit"

        with (
            patch("cli_agent_orchestrator.api.main.provider_manager") as mock_pm,
            patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc,
        ):
            mock_pm.get_provider.return_value = mock_provider
            mock_svc.send_input.side_effect = RuntimeError("TMux error")

            response = client.post("/terminals/abcd1234/exit")

            assert response.status_code == 500
            assert "Failed to exit terminal" in response.json()["detail"]

    def test_exit_terminal_provider_returns_none(self, client):
        """Should return 404 when get_provider returns None (not ValueError)."""
        with patch("cli_agent_orchestrator.api.main.provider_manager") as mock_pm:
            mock_pm.get_provider.return_value = None

            response = client.post("/terminals/deadbeef/exit")

            assert response.status_code == 404
            assert "Provider not found" in response.json()["detail"]


class TestDeleteTerminalEndpoint:
    """Test DELETE /terminals/{terminal_id} endpoint."""

    def test_delete_terminal_success(self, client):
        """DELETE /terminals/{terminal_id} deletes and returns success."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            mock_svc.delete_terminal.return_value = True

            response = client.delete("/terminals/abcd1234")

            assert response.status_code == 200
            assert response.json() == {"success": True}
            mock_svc.delete_terminal.assert_called_once_with("abcd1234")

    def test_delete_terminal_not_found(self, client):
        """DELETE /terminals/{terminal_id} returns 404 for missing terminal."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            mock_svc.delete_terminal.side_effect = ValueError("Terminal not found")

            response = client.delete("/terminals/deadbeef")

            assert response.status_code == 404

    def test_delete_terminal_server_error(self, client):
        """DELETE /terminals/{terminal_id} returns 500 on internal error."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            mock_svc.delete_terminal.side_effect = Exception("TMux error")

            response = client.delete("/terminals/abcd1234")

            assert response.status_code == 500
            assert "Failed to delete terminal" in response.json()["detail"]


class TestCreateInboxMessageEndpoint:
    """Test POST /terminals/{receiver_id}/inbox/messages endpoint."""

    def test_create_inbox_message_success(self, client):
        """POST creates an inbox message and returns success."""
        mock_delivery = MagicMock()
        mock_delivery.notification.id = 1
        mock_delivery.notification.receiver_id = "abcd1234"
        mock_delivery.notification.source_kind = "terminal"
        mock_delivery.notification.source_id = "sender1"
        mock_delivery.notification.created_at.isoformat.return_value = "2026-03-13T12:00:00"
        mock_delivery.message.id = 10
        mock_delivery.message.sender_id = "sender1"
        mock_delivery.message.source_kind = "terminal"
        mock_delivery.message.source_id = "sender1"

        with (
            patch("cli_agent_orchestrator.api.main._require_inbox_message_policy"),
            patch("cli_agent_orchestrator.api.main.create_inbox_delivery") as mock_create,
            patch("cli_agent_orchestrator.api.main.inbox_service") as mock_inbox,
        ):
            mock_create.return_value = mock_delivery

            response = client.post(
                "/terminals/abcd1234/inbox/messages",
                params={"sender_id": "sender1", "message": "hello"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["notification_id"] == 1
            assert data["message_id"] == 10
            assert data["sender_id"] == "sender1"
            assert data["source_kind"] == "terminal"
            assert data["source_id"] == "sender1"

    def test_create_inbox_message_delivery_failure_still_succeeds(self, client):
        """Immediate delivery failure should not fail the API response."""
        mock_delivery = MagicMock()
        mock_delivery.notification.id = 2
        mock_delivery.notification.receiver_id = "abcd1234"
        mock_delivery.notification.source_kind = "terminal"
        mock_delivery.notification.source_id = "sender1"
        mock_delivery.notification.created_at.isoformat.return_value = "2026-03-13T12:00:00"
        mock_delivery.message.id = 20
        mock_delivery.message.sender_id = "sender1"
        mock_delivery.message.source_kind = "terminal"
        mock_delivery.message.source_id = "sender1"

        with (
            patch("cli_agent_orchestrator.api.main._require_inbox_message_policy"),
            patch("cli_agent_orchestrator.api.main.create_inbox_delivery") as mock_create,
            patch("cli_agent_orchestrator.api.main.inbox_service") as mock_inbox,
        ):
            mock_create.return_value = mock_delivery
            mock_inbox.check_and_send_pending_messages.side_effect = Exception("TMux busy")

            response = client.post(
                "/terminals/abcd1234/inbox/messages",
                params={"sender_id": "sender1", "message": "hello"},
            )

            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_create_inbox_message_not_found(self, client):
        """POST returns 404 when terminal not found."""
        with (
            patch("cli_agent_orchestrator.api.main._require_inbox_message_policy"),
            patch("cli_agent_orchestrator.api.main.create_inbox_delivery") as mock_create,
        ):
            mock_create.side_effect = ValueError("Terminal not found")

            response = client.post(
                "/terminals/deadbeef/inbox/messages",
                params={"sender_id": "sender1", "message": "hello"},
            )

            assert response.status_code == 404

    def test_create_inbox_message_server_error(self, client):
        """POST returns 500 on internal error."""
        with (
            patch("cli_agent_orchestrator.api.main._require_inbox_message_policy"),
            patch("cli_agent_orchestrator.api.main.create_inbox_delivery") as mock_create,
        ):
            mock_create.side_effect = Exception("DB error")

            response = client.post(
                "/terminals/abcd1234/inbox/messages",
                params={"sender_id": "sender1", "message": "hello"},
            )

            assert response.status_code == 500
            assert "Failed to create inbox message" in response.json()["detail"]


class TestWebSocketLocalhostRestriction:
    """Test that WebSocket endpoint rejects non-loopback clients."""

    def test_websocket_rejects_non_loopback(self, client):
        """WebSocket should close with 4003 for non-localhost clients."""
        # TestClient uses "testclient" as host, which is not in the allowlist
        with pytest.raises(Exception):
            with client.websocket_connect("/terminals/abcd1234/ws"):
                pass


class TestRemovedAnonymousProviderResolution:
    """Anonymous creation routes no longer perform provider resolution."""

    def test_create_terminal_uses_profile_provider(self, client):
        """POST /sessions/{session}/terminals is removed."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            response = client.post(
                "/sessions/test-session/terminals",
                params={
                    "provider": "kiro_cli",
                    "agent_id": "developer",
                },
            )

            assert response.status_code == 405
            mock_svc.create_terminal.assert_not_called()

    def test_create_terminal_falls_back_when_no_profile_provider(self, client):
        """Removed terminal creation route has no provider fallback path."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            response = client.post(
                "/sessions/test-session/terminals",
                params={
                    "provider": "kiro_cli",
                    "agent_id": "reviewer",
                },
            )

            assert response.status_code == 405
            mock_svc.create_terminal.assert_not_called()

    def test_create_session_does_not_resolve_provider(self, client):
        """POST /sessions is removed and does not dispatch creation."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            response = client.post(
                "/sessions",
                params={
                    "provider": "kiro_cli",
                    "agent_id": "supervisor",
                },
            )

            assert response.status_code == 405
            mock_svc.create_terminal.assert_not_called()

    def test_create_terminal_returns_500_on_resolve_error(self, client):
        """Removed terminal creation route cannot surface provider resolution errors."""
        with patch("cli_agent_orchestrator.api.main.terminal_service") as mock_svc:
            response = client.post(
                "/sessions/test-session/terminals",
                params={
                    "provider": "kiro_cli",
                    "agent_id": "developer",
                },
            )

            assert response.status_code == 405
            mock_svc.create_terminal.assert_not_called()

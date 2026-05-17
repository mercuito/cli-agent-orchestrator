"""Full tests for terminal service."""

from dataclasses import replace
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from test.support.agent_factory import Agent
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.base import ProviderRuntimePreparation
from cli_agent_orchestrator.services.terminal_service import (
    OutputMode,
    create_terminal,
    create_terminal_for_agent,
    delete_terminal,
    get_output,
    get_terminal,
    get_working_directory,
    send_input,
)


@pytest.fixture(autouse=True)
def _isolate_agent_runtime_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("cli_agent_orchestrator.agent.AGENTS_ROOT", tmp_path / "agents")


def _bound_agent(*, provider: str = "kiro_cli", session_name: str = "developer"):
    return replace(
        Agent(name="developer", description="Developer", system_prompt="Base prompt"),
        cli_provider=provider,
        workdir="/repo",
        session_name=session_name,
    ).for_workspace_context("wctx_dev")


class TestCreateTerminal:
    """Tests for create_terminal function."""

    @patch("cli_agent_orchestrator.services.terminal_service.TERMINAL_LOG_DIR")
    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal")
    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_window_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_session_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_terminal_id")
    @patch("cli_agent_orchestrator.services.terminal_service.load_agent")
    def test_create_terminal_new_session(
        self,
        mock_load_profile,
        mock_gen_id,
        mock_gen_session,
        mock_gen_window,
        mock_tmux,
        mock_db_create,
        mock_provider_manager,
        mock_log_dir,
    ):
        """Test creating terminal with new session."""
        mock_gen_id.return_value = "test1234"
        mock_gen_session.return_value = "cao-session"
        mock_gen_window.return_value = "developer-abcd"
        mock_tmux.session_exists.return_value = False
        mock_load_profile.return_value = _bound_agent()
        mock_provider = MagicMock()
        mock_provider_manager.prepare_terminal_runtime.return_value = ProviderRuntimePreparation()
        mock_provider_manager.runtime_state_capability.return_value = None
        mock_provider_manager.create_provider.return_value = mock_provider
        mock_log_path = MagicMock()
        mock_log_dir.__truediv__.return_value = mock_log_path

        result = create_terminal_for_agent(_bound_agent())

        assert result.id == "test1234"
        mock_tmux.create_session.assert_called_once()
        mock_provider.initialize.assert_called_once()

    @patch("cli_agent_orchestrator.services.terminal_service.TERMINAL_LOG_DIR")
    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal")
    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_window_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_session_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_terminal_id")
    @patch("cli_agent_orchestrator.services.terminal_service.load_agent")
    def test_create_terminal_existing_session(
        self,
        mock_load_profile,
        mock_gen_id,
        mock_gen_session,
        mock_gen_window,
        mock_tmux,
        mock_db_create,
        mock_provider_manager,
        mock_log_dir,
    ):
        """Test creating terminal in existing session."""
        mock_gen_id.return_value = "test1234"
        mock_gen_session.return_value = "cao-session"
        mock_gen_window.return_value = "developer-abcd"
        mock_tmux.session_exists.return_value = True
        mock_tmux.create_window.return_value = "developer-abcd"
        mock_load_profile.return_value = _bound_agent(session_name="existing")
        mock_provider = MagicMock()
        mock_provider_manager.prepare_terminal_runtime.return_value = ProviderRuntimePreparation()
        mock_provider_manager.runtime_state_capability.return_value = None
        mock_provider_manager.create_provider.return_value = mock_provider
        mock_log_path = MagicMock()
        mock_log_dir.__truediv__.return_value = mock_log_path

        result = create_terminal_for_agent(_bound_agent(session_name="existing"))

        assert result.id == "test1234"
        mock_tmux.create_window.assert_called_once()

    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_window_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_session_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_terminal_id")
    @patch("cli_agent_orchestrator.services.terminal_service.load_agent")
    def test_create_terminal_session_not_found(
        self, mock_load_profile, mock_gen_id, mock_gen_session, mock_gen_window, mock_tmux
    ):
        """Test creating terminal when session not found."""
        mock_gen_id.return_value = "test1234"
        mock_gen_session.return_value = "cao-session"
        mock_gen_window.return_value = "developer-abcd"
        mock_tmux.session_exists.side_effect = [True, False]
        mock_load_profile.return_value = _bound_agent(session_name="nonexistent")

        with pytest.raises(ValueError, match="not found"):
            create_terminal_for_agent(_bound_agent(session_name="nonexistent"))

    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_window_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_session_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_terminal_id")
    @patch("cli_agent_orchestrator.services.terminal_service.load_agent")
    def test_create_terminal_session_already_exists(
        self, mock_load_profile, mock_gen_id, mock_gen_session, mock_gen_window, mock_tmux
    ):
        """Test creating terminal when session already exists."""
        mock_gen_id.return_value = "test1234"
        mock_gen_session.return_value = "cao-session"
        mock_gen_window.return_value = "developer-abcd"
        mock_tmux.session_exists.side_effect = [False, True]
        mock_load_profile.return_value = _bound_agent(session_name="existing")

        with pytest.raises(ValueError, match="already exists"):
            create_terminal_for_agent(_bound_agent(session_name="existing"))

    @patch("cli_agent_orchestrator.services.terminal_service.TERMINAL_LOG_DIR")
    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal")
    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_window_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_session_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_terminal_id")
    @patch("cli_agent_orchestrator.services.terminal_service.load_agent")
    def test_create_terminal_does_not_append_cao_skill_catalog(
        self,
        mock_load_profile,
        mock_gen_id,
        mock_gen_session,
        mock_gen_window,
        mock_tmux,
        mock_db_create,
        mock_provider_manager,
        mock_log_dir,
    ):
        """Skills are provider-native now, so CAO does not pass skill prompt text."""
        mock_gen_id.return_value = "test1234"
        mock_gen_session.return_value = "cao-session"
        mock_gen_window.return_value = "developer-abcd"
        mock_tmux.session_exists.return_value = False
        mock_load_profile.return_value = _bound_agent(provider="codex")
        mock_provider = MagicMock()
        mock_provider_manager.prepare_terminal_runtime.return_value = ProviderRuntimePreparation()
        mock_provider_manager.runtime_state_capability.return_value = None
        mock_provider_manager.create_provider.return_value = mock_provider
        mock_log_path = MagicMock()
        mock_log_dir.__truediv__.return_value = mock_log_path

        create_terminal_for_agent(_bound_agent(provider="codex"))

        assert "skill_prompt" not in mock_provider_manager.create_provider.call_args.kwargs

    @pytest.mark.parametrize("provider_name", ["kiro_cli", "q_cli", "copilot_cli", "codex"])
    @patch("cli_agent_orchestrator.services.terminal_service.TERMINAL_LOG_DIR")
    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal")
    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_window_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_session_name")
    @patch("cli_agent_orchestrator.services.terminal_service.generate_terminal_id")
    @patch("cli_agent_orchestrator.services.terminal_service.load_agent")
    def test_create_terminal_does_not_pass_skill_prompt_to_provider(
        self,
        mock_load_profile,
        mock_gen_id,
        mock_gen_session,
        mock_gen_window,
        mock_tmux,
        mock_db_create,
        mock_provider_manager,
        mock_log_dir,
        provider_name,
    ):
        """CAO should not expose provider-neutral skills as prompt text."""
        mock_gen_id.return_value = "test1234"
        mock_gen_session.return_value = "cao-session"
        mock_gen_window.return_value = "developer-abcd"
        mock_tmux.session_exists.return_value = False
        mock_load_profile.return_value = _bound_agent(provider=provider_name)
        mock_provider = MagicMock()
        mock_provider_manager.prepare_terminal_runtime.return_value = ProviderRuntimePreparation()
        mock_provider_manager.runtime_state_capability.return_value = None
        mock_provider_manager.create_provider.return_value = mock_provider
        mock_log_path = MagicMock()
        mock_log_dir.__truediv__.return_value = mock_log_path

        create_terminal_for_agent(_bound_agent(provider=provider_name))

        assert "skill_prompt" not in mock_provider_manager.create_provider.call_args.kwargs


class TestGetTerminal:
    """Tests for get_terminal function."""

    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_get_terminal_success(self, mock_get_metadata, mock_provider_manager):
        """Test getting terminal successfully."""
        mock_get_metadata.return_value = {
            "id": "test1234",
            "tmux_window": "developer-abcd",
            "provider": "kiro_cli",
            "tmux_session": "cao-session",
            "agent_id": "developer",
            "last_active": datetime.now(),
        }
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = TerminalStatus.IDLE
        mock_provider_manager.get_provider.return_value = mock_provider

        result = get_terminal("test1234")

        assert result["id"] == "test1234"
        assert result["status"] == TerminalStatus.IDLE.value

    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_get_terminal_not_found(self, mock_get_metadata):
        """Test getting non-existent terminal."""
        mock_get_metadata.return_value = None

        with pytest.raises(ValueError, match="not found"):
            get_terminal("nonexistent")

    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_get_terminal_no_provider(self, mock_get_metadata, mock_provider_manager):
        """Test getting terminal when provider not found."""
        mock_get_metadata.return_value = {
            "id": "test1234",
            "tmux_window": "developer-abcd",
            "provider": "kiro_cli",
            "tmux_session": "cao-session",
            "agent_id": "developer",
            "last_active": datetime.now(),
        }
        mock_provider_manager.get_provider.return_value = None

        with pytest.raises(ValueError, match="Provider not found"):
            get_terminal("test1234")


class TestGetWorkingDirectory:
    """Tests for get_working_directory function."""

    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_get_working_directory_success(self, mock_get_metadata, mock_tmux):
        """Test getting working directory successfully."""
        mock_get_metadata.return_value = {
            "tmux_session": "cao-session",
            "tmux_window": "developer-abcd",
        }
        mock_tmux.get_pane_working_directory.return_value = "/home/user/project"

        result = get_working_directory("test1234")

        assert result == "/home/user/project"

    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_get_working_directory_not_found(self, mock_get_metadata):
        """Test getting working directory for non-existent terminal."""
        mock_get_metadata.return_value = None

        with pytest.raises(ValueError, match="not found"):
            get_working_directory("nonexistent")


class TestSendInput:
    """Tests for send_input function."""

    @patch("cli_agent_orchestrator.services.terminal_service.update_last_active")
    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_send_input_success(self, mock_get_metadata, mock_tmux, mock_pm, mock_update):
        """Test sending input successfully."""
        mock_get_metadata.return_value = {
            "tmux_session": "cao-session",
            "tmux_window": "developer-abcd",
        }
        mock_provider = mock_pm.get_provider.return_value
        mock_provider.paste_enter_count = 2

        result = send_input("test1234", "test message")

        assert result is True
        mock_tmux.send_keys.assert_called_once_with(
            "cao-session", "developer-abcd", "test message", enter_count=2
        )
        mock_update.assert_called_once_with("test1234")

    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_send_input_not_found(self, mock_get_metadata):
        """Test sending input to non-existent terminal."""
        mock_get_metadata.return_value = None

        with pytest.raises(ValueError, match="not found"):
            send_input("nonexistent", "message")


class TestGetOutput:
    """Tests for get_output function."""

    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_get_output_full(self, mock_get_metadata, mock_tmux):
        """Test getting full output."""
        mock_get_metadata.return_value = {
            "tmux_session": "cao-session",
            "tmux_window": "developer-abcd",
        }
        mock_tmux.get_history.return_value = "full terminal output"

        result = get_output("test1234", OutputMode.FULL)

        assert result == "full terminal output"

    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_get_output_last(self, mock_get_metadata, mock_tmux, mock_provider_manager):
        """Test getting last message."""
        mock_get_metadata.return_value = {
            "tmux_session": "cao-session",
            "tmux_window": "developer-abcd",
        }
        mock_tmux.get_history.return_value = "full terminal output"
        mock_provider = MagicMock()
        mock_provider.extract_last_message_from_script.return_value = "last message"
        mock_provider_manager.get_provider.return_value = mock_provider

        result = get_output("test1234", OutputMode.LAST)

        assert result == "last message"

    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_get_output_not_found(self, mock_get_metadata):
        """Test getting output from non-existent terminal."""
        mock_get_metadata.return_value = None

        with pytest.raises(ValueError, match="not found"):
            get_output("nonexistent")

    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_get_output_last_no_provider(self, mock_get_metadata, mock_tmux, mock_provider_manager):
        """Test getting last message when provider not found."""
        mock_get_metadata.return_value = {
            "tmux_session": "cao-session",
            "tmux_window": "developer-abcd",
        }
        mock_tmux.get_history.return_value = "full output"
        mock_provider_manager.get_provider.return_value = None

        with pytest.raises(ValueError, match="Provider not found"):
            get_output("test1234", OutputMode.LAST)


class TestDeleteTerminal:
    """Tests for delete_terminal function."""

    @patch("cli_agent_orchestrator.services.terminal_service.db_delete_terminal")
    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_delete_terminal_success(
        self, mock_get_metadata, mock_tmux, mock_provider_manager, mock_db_delete
    ):
        """Test deleting terminal successfully."""
        mock_get_metadata.return_value = {
            "tmux_session": "cao-session",
            "tmux_window": "developer-abcd",
        }
        mock_db_delete.return_value = True

        result = delete_terminal("test1234")

        assert result is True
        mock_tmux.stop_pipe_pane.assert_called_once()
        mock_provider_manager.cleanup_provider.assert_called_once_with("test1234")

    @patch("cli_agent_orchestrator.services.terminal_service.db_delete_terminal")
    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.tmux_client")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_delete_terminal_pipe_pane_error(
        self, mock_get_metadata, mock_tmux, mock_provider_manager, mock_db_delete
    ):
        """Test deleting terminal when stop_pipe_pane fails."""
        mock_get_metadata.return_value = {
            "tmux_session": "cao-session",
            "tmux_window": "developer-abcd",
        }
        mock_tmux.stop_pipe_pane.side_effect = Exception("Pipe error")
        mock_db_delete.return_value = True

        # Should not raise, just warn
        result = delete_terminal("test1234")

        assert result is True

    @patch("cli_agent_orchestrator.services.terminal_service.db_delete_terminal")
    @patch("cli_agent_orchestrator.services.terminal_service.provider_manager")
    @patch("cli_agent_orchestrator.services.terminal_service.get_terminal_metadata")
    def test_delete_terminal_no_metadata(
        self, mock_get_metadata, mock_provider_manager, mock_db_delete
    ):
        """Test deleting terminal when metadata not found."""
        mock_get_metadata.return_value = None
        mock_db_delete.return_value = True

        result = delete_terminal("test1234")

        assert result is True

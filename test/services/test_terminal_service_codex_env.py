from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def test_create_terminal_codex_sets_codex_home_env(tmp_path: Path):
    from cli_agent_orchestrator.models.terminal import TerminalStatus
    from cli_agent_orchestrator.services import terminal_service

    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)

    provider = MagicMock()
    provider.initialize.return_value = True

    with patch("cli_agent_orchestrator.services.terminal_service.generate_terminal_id", return_value="abcd1234"), patch(
        "cli_agent_orchestrator.services.terminal_service.generate_session_name",
        return_value="cao-test",
    ), patch(
        "cli_agent_orchestrator.services.terminal_service.generate_window_name",
        return_value="codex_developer-0000",
    ), patch(
        "cli_agent_orchestrator.services.terminal_service.db_create_terminal"
    ), patch(
        "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
        return_value=provider,
    ), patch(
        "cli_agent_orchestrator.services.terminal_service.tmux_client"
    ) as mock_tmux, patch(
        "cli_agent_orchestrator.services.terminal_service.prepare_codex_home",
        return_value=codex_home,
    ):
        mock_tmux.session_exists.return_value = False

        terminal = terminal_service.create_terminal(
            provider="codex",
            agent_profile="codex_developer",
            session_name=None,
            new_session=True,
            working_directory=str(tmp_path),
        )

        assert terminal.id == "abcd1234"
        assert terminal.status == TerminalStatus.IDLE

        # Expect CODEX_HOME env to be passed through to tmux create_session
        create_kwargs = mock_tmux.create_session.call_args.kwargs
        assert create_kwargs["environment"]["CODEX_HOME"] == str(codex_home)

from __future__ import annotations

from unittest.mock import call, patch


def test_delete_session_cleans_up_codex_homes():
    from cli_agent_orchestrator.services import session_service

    terminals = [
        {"id": "t1", "provider": "codex"},
        {"id": "t2", "provider": "q_cli"},
    ]

    with patch(
        "cli_agent_orchestrator.services.session_service.tmux_client"
    ) as mock_tmux, patch(
        "cli_agent_orchestrator.services.session_service.list_terminals_by_session",
        return_value=terminals,
    ), patch(
        "cli_agent_orchestrator.services.session_service.delete_terminals_by_session"
    ), patch(
        "cli_agent_orchestrator.services.session_service.provider_manager.cleanup_provider"
    ), patch(
        "cli_agent_orchestrator.services.session_service.cleanup_codex_home",
        create=True,
    ) as mock_cleanup:
        mock_tmux.session_exists.return_value = True

        assert session_service.delete_session("cao-test") is True

        # Best-effort: always attempt per-terminal Codex home cleanup.
        assert mock_cleanup.call_args_list == [call("t1"), call("t2")]


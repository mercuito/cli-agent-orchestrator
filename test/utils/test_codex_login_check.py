from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def test_codex_login_ok_uses_login_status_first(tmp_path: Path):
    from cli_agent_orchestrator.utils.codex_home import _codex_login_ok

    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True)

    with (
        patch("cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"),
        patch(
            "cli_agent_orchestrator.utils.codex_home.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="Logged in"),
        ) as mock_run,
    ):
        assert _codex_login_ok(codex_home) is True
        assert mock_run.call_args[0][0][1:3] == ["login", "status"]


def test_codex_login_ok_falls_back_to_auth_status_when_login_missing(tmp_path: Path):
    from cli_agent_orchestrator.utils.codex_home import _codex_login_ok

    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True)

    runs = [
        SimpleNamespace(returncode=2, stdout="unrecognized subcommand 'login'"),
        SimpleNamespace(returncode=0, stdout="ok"),
    ]

    with (
        patch("cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"),
        patch(
            "cli_agent_orchestrator.utils.codex_home.subprocess.run",
            side_effect=runs,
        ) as mock_run,
    ):
        assert _codex_login_ok(codex_home) is True
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0].args[0][1:3] == ["login", "status"]
        assert mock_run.call_args_list[1].args[0][1:3] == ["auth", "status"]


def test_codex_login_ok_returns_false_when_output_indicates_logged_out(tmp_path: Path):
    from cli_agent_orchestrator.utils.codex_home import _codex_login_ok

    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True)

    with (
        patch("cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"),
        patch(
            "cli_agent_orchestrator.utils.codex_home.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="Not logged in"),
        ),
    ):
        assert _codex_login_ok(codex_home) is False

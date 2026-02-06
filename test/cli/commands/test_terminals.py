import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner

from cli_agent_orchestrator.cli.commands.terminals import terminals


@dataclass
class _FakeResponse:
    status_code: int = 200
    payload: Optional[Any] = None
    text: str = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            http_error = requests.HTTPError(self.text)
            http_error.response = self  # type: ignore[attr-defined]
            raise http_error

    def json(self) -> Any:
        return self.payload


def test_terminals_get_human_output():
    runner = CliRunner()

    terminal_payload: Dict[str, Any] = {
        "id": "abcd1234",
        "name": "w0",
        "provider": "codex",
        "session_name": "cao-test",
        "agent_profile": "developer",
        "status": "idle",
        "last_active": "2026-02-06T00:00:00",
    }

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(payload=terminal_payload)
        result = runner.invoke(terminals, ["get", "abcd1234"])

    assert result.exit_code == 0
    assert "id=abcd1234" in result.output
    assert "status=idle" in result.output
    assert "provider=codex" in result.output
    assert "session=cao-test" in result.output
    assert "agent_profile=developer" in result.output


def test_terminals_get_json_output():
    runner = CliRunner()

    terminal_payload: Dict[str, Any] = {
        "id": "abcd1234",
        "name": "w0",
        "provider": "codex",
        "session_name": "cao-test",
        "agent_profile": "developer",
        "status": "idle",
    }

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(payload=terminal_payload)
        result = runner.invoke(terminals, ["get", "abcd1234", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == terminal_payload


def test_terminals_output_human_defaults_to_full():
    runner = CliRunner()

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(payload={"output": "HELLO\nWORLD", "mode": "full"})
        result = runner.invoke(terminals, ["output", "abcd1234"])

    assert result.exit_code == 0
    assert result.output == "HELLO\nWORLD\n"


def test_terminals_output_mode_last_json():
    runner = CliRunner()

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(payload={"output": "DONE", "mode": "last"})
        result = runner.invoke(terminals, ["output", "abcd1234", "--mode", "last", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"terminal_id": "abcd1234", "mode": "last", "output": "DONE"}


def test_terminals_exit_human_output():
    runner = CliRunner()

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.post") as mock_post:
        mock_post.return_value = _FakeResponse(payload={"success": True})
        result = runner.invoke(terminals, ["exit", "abcd1234"])

    assert result.exit_code == 0
    assert "exit sent" in result.output.lower()
    assert "abcd1234" in result.output


def test_terminals_exit_json_output():
    runner = CliRunner()

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.post") as mock_post:
        mock_post.return_value = _FakeResponse(payload={"success": True})
        result = runner.invoke(terminals, ["exit", "abcd1234", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"terminal_id": "abcd1234", "success": True}


def test_terminals_list_human_output():
    runner = CliRunner()

    terminals_payload: List[Dict[str, Any]] = [
        {
            "id": "abcd1234",
            "tmux_session": "cao-test",
            "tmux_window": "w0",
            "provider": "codex",
            "agent_profile": "developer",
            "last_active": "2026-02-06T00:00:00",
        }
    ]

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(payload=terminals_payload)
        result = runner.invoke(terminals, ["list", "--session", "cao-test"])

    assert result.exit_code == 0
    assert "id" in result.output.lower()
    assert "provider" in result.output.lower()
    assert "abcd1234" in result.output
    assert "codex" in result.output


def test_terminals_list_json_output():
    runner = CliRunner()

    terminals_payload: List[Dict[str, Any]] = [
        {
            "id": "abcd1234",
            "tmux_session": "cao-test",
            "tmux_window": "w0",
            "provider": "codex",
            "agent_profile": "developer",
            "last_active": "2026-02-06T00:00:00",
        }
    ]

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(payload=terminals_payload)
        result = runner.invoke(terminals, ["list", "--session", "cao-test", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"session_name": "cao-test", "terminals": terminals_payload}


def test_terminals_connection_error_is_click_exception():
    runner = CliRunner()

    with patch(
        "cli_agent_orchestrator.cli.commands.terminals.requests.get",
        side_effect=requests.RequestException("nope"),
    ):
        result = runner.invoke(terminals, ["get", "abcd1234"])

    assert result.exit_code != 0
    assert "failed to connect to cao-server" in result.output.lower()


def test_terminals_http_error_includes_status_code():
    runner = CliRunner()

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(status_code=404, text="not found", payload={})
        result = runner.invoke(terminals, ["get", "abcd1234"])

    assert result.exit_code != 0
    assert "cao-server error" in result.output.lower()
    assert "404" in result.output


def test_terminals_output_invalid_mode_rejected_by_click_without_http_call():
    runner = CliRunner()

    with patch("cli_agent_orchestrator.cli.commands.terminals.requests.get") as mock_get:
        result = runner.invoke(terminals, ["output", "abcd1234", "--mode", "nope"])

    assert result.exit_code != 0
    assert mock_get.call_count == 0


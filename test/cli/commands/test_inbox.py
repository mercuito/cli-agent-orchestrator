import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import requests
from click.testing import CliRunner

from cli_agent_orchestrator.cli.commands.inbox import inbox


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


def test_inbox_list_human_output():
    runner = CliRunner()

    messages_payload: List[Dict[str, Any]] = [
        {
            "id": 1,
            "sender_id": "aaaa1111",
            "receiver_id": "bbbb2222",
            "message": "Hello",
            "status": "delivered",
            "created_at": "2026-02-06T00:00:00",
        }
    ]

    with patch("cli_agent_orchestrator.cli.commands.inbox.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(payload=messages_payload)
        result = runner.invoke(inbox, ["list", "bbbb2222"])

    assert result.exit_code == 0
    assert "Hello" in result.output
    assert "aaaa1111" in result.output


def test_inbox_list_passes_query_params():
    runner = CliRunner()

    with patch("cli_agent_orchestrator.cli.commands.inbox.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(payload=[])
        result = runner.invoke(inbox, ["list", "bbbb2222", "--status", "pending", "--limit", "5"])

    assert result.exit_code == 0
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["status"] == "pending"
    assert kwargs["params"]["limit"] == 5


def test_inbox_list_json_output():
    runner = CliRunner()

    messages_payload: List[Dict[str, Any]] = [
        {
            "id": 1,
            "sender_id": "aaaa1111",
            "receiver_id": "bbbb2222",
            "message": "Hello",
            "status": "delivered",
            "created_at": "2026-02-06T00:00:00",
        }
    ]

    with patch("cli_agent_orchestrator.cli.commands.inbox.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(payload=messages_payload)
        result = runner.invoke(inbox, ["list", "bbbb2222", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"terminal_id": "bbbb2222", "messages": messages_payload}


def test_inbox_connection_error_is_click_exception():
    runner = CliRunner()

    with patch(
        "cli_agent_orchestrator.cli.commands.inbox.requests.get",
        side_effect=requests.RequestException("nope"),
    ):
        result = runner.invoke(inbox, ["list", "bbbb2222"])

    assert result.exit_code != 0
    assert "failed to connect to cao-server" in result.output.lower()


def test_inbox_http_error_includes_status_code():
    runner = CliRunner()

    with patch("cli_agent_orchestrator.cli.commands.inbox.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse(status_code=404, text="not found", payload=[])
        result = runner.invoke(inbox, ["list", "bbbb2222"])

    assert result.exit_code != 0
    assert "cao-server error" in result.output.lower()
    assert "404" in result.output


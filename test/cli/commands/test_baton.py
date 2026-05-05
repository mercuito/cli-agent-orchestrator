"""Tests for ``cao baton`` CLI commands."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from unittest.mock import patch

import requests
from click.testing import CliRunner

from cli_agent_orchestrator.cli.commands.baton import baton

MODULE = "cli_agent_orchestrator.cli.commands.baton"


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


def _baton_payload(
    baton_id: str = "baton-1",
    status: str = "active",
    holder: Optional[str] = "impl",
) -> Dict[str, Any]:
    return {
        "id": baton_id,
        "title": "T06",
        "status": status,
        "originator_id": "originator",
        "current_holder_id": holder,
        "return_stack": ["reviewer"],
        "expected_next_action": "inspect",
        "created_at": "2026-05-04T10:00:00",
        "updated_at": "2026-05-04T10:05:00",
        "last_nudged_at": None,
        "completed_at": None,
    }


def _event_payload() -> Dict[str, Any]:
    return {
        "id": 1,
        "baton_id": "baton-1",
        "event_type": "create",
        "actor_id": "originator",
        "from_holder_id": None,
        "to_holder_id": "impl",
        "message": "start",
        "created_at": "2026-05-04T10:00:00",
    }


class TestList:
    def test_list_uses_server_default_active_status(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=[_baton_payload()])
            result = runner.invoke(baton, ["list"])

        assert result.exit_code == 0
        assert "baton-1 [active]" in result.output
        params = mock_get.call_args.kwargs["params"]
        assert params == {"limit": 50, "offset": 0}

    def test_list_filters_forwarded(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=[])
            result = runner.invoke(
                baton,
                [
                    "list",
                    "--status",
                    "blocked",
                    "--holder",
                    "impl",
                    "--originator",
                    "originator",
                    "--limit",
                    "10",
                    "--offset",
                    "20",
                ],
            )

        assert result.exit_code == 0
        params = mock_get.call_args.kwargs["params"]
        assert params["status"] == "blocked"
        assert params["holder_id"] == "impl"
        assert params["originator_id"] == "originator"
        assert params["limit"] == 10
        assert params["offset"] == 20

    def test_json_output(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=[_baton_payload()])
            result = runner.invoke(baton, ["list", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.output)[0]["id"] == "baton-1"

    def test_invalid_status_rejected_by_click(self):
        runner = CliRunner()
        result = runner.invoke(baton, ["list", "--status", "bogus"])
        assert result.exit_code != 0


class TestShowAndLog:
    def test_show_prints_details(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=_baton_payload())
            result = runner.invoke(baton, ["show", "baton-1"])

        assert result.exit_code == 0
        assert "current_holder_id: impl" in result.output
        assert mock_get.call_args.args[0].endswith("/batons/baton-1")

    def test_show_json(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=_baton_payload())
            result = runner.invoke(baton, ["show", "baton-1", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.output)["id"] == "baton-1"

    def test_log_prints_events(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=[_event_payload()])
            result = runner.invoke(baton, ["log", "baton-1"])

        assert result.exit_code == 0
        assert "create actor=originator" in result.output
        assert "message=start" in result.output
        assert mock_get.call_args.args[0].endswith("/batons/baton-1/events")

    def test_log_json(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=[_event_payload()])
            result = runner.invoke(baton, ["log", "baton-1", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.output)[0]["event_type"] == "create"


class TestRecovery:
    def test_cancel_posts_message(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse(
                payload=_baton_payload(status="canceled", holder=None)
            )
            result = runner.invoke(
                baton,
                ["cancel", "baton-1", "--message", "cleanup"],
            )

        assert result.exit_code == 0
        assert "baton-1 [canceled]" in result.output
        assert mock_post.call_args.args[0].endswith("/batons/baton-1/cancel")
        assert mock_post.call_args.kwargs["json"] == {"message": "cleanup"}

    def test_reassign_posts_holder_and_expected_action(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse(payload=_baton_payload(holder="new"))
            result = runner.invoke(
                baton,
                [
                    "reassign",
                    "baton-1",
                    "--holder",
                    "new",
                    "--message",
                    "recover",
                    "--expected-next-action",
                    "resume",
                ],
            )

        assert result.exit_code == 0
        assert "holder=new" in result.output
        assert mock_post.call_args.args[0].endswith("/batons/baton-1/reassign")
        assert mock_post.call_args.kwargs["json"] == {
            "holder_id": "new",
            "message": "recover",
            "expected_next_action": "resume",
        }

    def test_reassign_requires_holder(self):
        runner = CliRunner()
        result = runner.invoke(baton, ["reassign", "baton-1"])
        assert result.exit_code != 0

    def test_http_error_surfaces(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(status_code=404, text="missing")
            result = runner.invoke(baton, ["show", "missing"])

        assert result.exit_code != 0
        assert "404" in result.output


class TestConnectionAndRegistration:
    def test_connection_error_surfaces_clickexception(self):
        runner = CliRunner()
        with patch(
            f"{MODULE}.requests.get",
            side_effect=requests.RequestException("server down"),
        ):
            result = runner.invoke(baton, ["list"])

        assert result.exit_code != 0
        assert "failed to connect to cao-server" in result.output.lower()

    def test_baton_is_registered_on_cli(self):
        from cli_agent_orchestrator.cli.main import cli
        from cli_agent_orchestrator.services.baton_feature import is_baton_enabled

        assert ("baton" in cli.commands) is is_baton_enabled()

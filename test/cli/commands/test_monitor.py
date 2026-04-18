"""Tests for ``cao monitor`` CLI commands.

Phase 5 of the monitoring sessions feature. See docs/plans/monitoring-sessions.md.

Mirrors the testing style of ``test_inbox.py``: fake HTTP responses via a
``_FakeResponse`` dataclass, patches on ``requests.<method>`` at the module
level, and ``CliRunner`` to drive the command group.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner

from cli_agent_orchestrator.cli.commands.monitor import monitor

MODULE = "cli_agent_orchestrator.cli.commands.monitor"


@dataclass
class _FakeResponse:
    status_code: int = 200
    payload: Optional[Any] = None
    text: str = ""
    headers: Dict[str, str] = field(default_factory=dict)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            http_error = requests.HTTPError(self.text)
            http_error.response = self  # type: ignore[attr-defined]
            raise http_error

    def json(self) -> Any:
        return self.payload


def _session_payload(
    session_id: str = "sess-1",
    terminal_id: str = "term-A",
    peer_terminal_ids: Optional[List[str]] = None,
    label: Optional[str] = None,
    started_at: str = "2026-04-18T10:00:00",
    ended_at: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": session_id,
        "terminal_id": terminal_id,
        "peer_terminal_ids": peer_terminal_ids or [],
        "label": label,
        "started_at": started_at,
        "ended_at": ended_at,
        "status": "ended" if ended_at else "active",
    }


# ---------------------------------------------------------------------------
# cao monitor start
# ---------------------------------------------------------------------------


class TestStart:
    def test_minimal_prints_session_id(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse(
                status_code=201, payload=_session_payload()
            )
            result = runner.invoke(monitor, ["start", "--terminal", "term-A"])

        assert result.exit_code == 0
        assert "sess-1" in result.output
        _, kwargs = mock_post.call_args
        # Endpoint + body wiring
        assert mock_post.call_args.args[0].endswith("/monitoring/sessions")
        assert kwargs["json"] == {
            "terminal_id": "term-A",
            "peer_terminal_ids": None,
            "label": None,
        }

    def test_with_peers_and_label_forwards_all_fields(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse(
                status_code=201,
                payload=_session_payload(peer_terminal_ids=["P1", "P2"], label="rev"),
            )
            result = runner.invoke(
                monitor,
                [
                    "start",
                    "--terminal", "term-A",
                    "--peer", "P1",
                    "--peer", "P2",
                    "--label", "rev",
                ],
            )

        assert result.exit_code == 0
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["peer_terminal_ids"] == ["P1", "P2"]
        assert kwargs["json"]["label"] == "rev"

    def test_json_output(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse(
                status_code=201, payload=_session_payload()
            )
            result = runner.invoke(
                monitor, ["start", "--terminal", "term-A", "--json"]
            )

        assert result.exit_code == 0
        # Output is full session dict, not just the id
        assert json.loads(result.output)["id"] == "sess-1"


# ---------------------------------------------------------------------------
# cao monitor end
# ---------------------------------------------------------------------------


class TestEnd:
    def test_end_returns_zero_on_success(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse(
                status_code=200,
                payload=_session_payload(ended_at="2026-04-18T11:00:00"),
            )
            result = runner.invoke(monitor, ["end", "sess-1"])

        assert result.exit_code == 0
        assert mock_post.call_args.args[0].endswith("/monitoring/sessions/sess-1/end")

    def test_end_409_surfaces_as_error(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse(
                status_code=409, text="already ended"
            )
            result = runner.invoke(monitor, ["end", "sess-1"])

        assert result.exit_code != 0
        assert "409" in result.output


# ---------------------------------------------------------------------------
# cao monitor add-peer / remove-peer
# ---------------------------------------------------------------------------


class TestAddPeer:
    def test_adds_single_peer(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse(
                status_code=200,
                payload=_session_payload(peer_terminal_ids=["P1"]),
            )
            result = runner.invoke(monitor, ["add-peer", "sess-1", "P1"])

        assert result.exit_code == 0
        assert mock_post.call_args.args[0].endswith(
            "/monitoring/sessions/sess-1/peers"
        )
        assert mock_post.call_args.kwargs["json"] == {"peer_terminal_ids": ["P1"]}


class TestRemovePeer:
    def test_removes_peer(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.delete") as mock_delete:
            mock_delete.return_value = _FakeResponse(
                status_code=200,
                payload=_session_payload(peer_terminal_ids=[]),
            )
            result = runner.invoke(monitor, ["remove-peer", "sess-1", "P1"])

        assert result.exit_code == 0
        assert mock_delete.call_args.args[0].endswith(
            "/monitoring/sessions/sess-1/peers/P1"
        )


# ---------------------------------------------------------------------------
# cao monitor list
# ---------------------------------------------------------------------------


class TestList:
    def test_list_with_no_filters(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(
                payload=[_session_payload(session_id="a"), _session_payload(session_id="b")]
            )
            result = runner.invoke(monitor, ["list"])

        assert result.exit_code == 0
        assert "a" in result.output
        assert "b" in result.output

    def test_active_flag_translates_to_status_filter(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=[])
            result = runner.invoke(monitor, ["list", "--active"])

        assert result.exit_code == 0
        assert mock_get.call_args.kwargs["params"]["status"] == "active"

    def test_limit_and_offset_forwarded(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=[])
            result = runner.invoke(
                monitor, ["list", "--limit", "25", "--offset", "50"]
            )
        assert result.exit_code == 0
        params = mock_get.call_args.kwargs["params"]
        assert params["limit"] == 25
        assert params["offset"] == 50

    def test_active_and_ended_are_mutually_exclusive(self):
        runner = CliRunner()
        result = runner.invoke(monitor, ["list", "--active", "--ended"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_filter_flags_forwarded(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(payload=[])
            result = runner.invoke(
                monitor,
                [
                    "list",
                    "--terminal", "T",
                    "--peer", "P",
                    "--involves", "X",
                    "--label", "rev",
                ],
            )

        assert result.exit_code == 0
        params = mock_get.call_args.kwargs["params"]
        assert params["terminal_id"] == "T"
        assert params["peer_terminal_id"] == "P"
        assert params["involves"] == "X"
        assert params["label"] == "rev"


# ---------------------------------------------------------------------------
# cao monitor show
# ---------------------------------------------------------------------------


class TestShow:
    def test_show_prints_session(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(
                payload=_session_payload(label="rev", peer_terminal_ids=["P1"])
            )
            result = runner.invoke(monitor, ["show", "sess-1"])

        assert result.exit_code == 0
        assert "sess-1" in result.output
        assert "rev" in result.output

    def test_show_missing_returns_nonzero(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(status_code=404, text="nope")
            result = runner.invoke(monitor, ["show", "missing"])

        assert result.exit_code != 0
        assert "404" in result.output


# ---------------------------------------------------------------------------
# cao monitor log
# ---------------------------------------------------------------------------


class TestLog:
    def test_default_format_is_markdown(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(
                payload=None,
                text="# Monitoring session: sess-1\n**Monitored:** term-A\n",
                headers={"content-type": "text/markdown; charset=utf-8"},
            )
            result = runner.invoke(monitor, ["log", "sess-1"])

        assert result.exit_code == 0
        assert "# Monitoring session:" in result.output
        assert mock_get.call_args.kwargs["params"]["format"] == "markdown"

    def test_json_format(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(
                payload={"session": _session_payload(), "messages": []},
                headers={"content-type": "application/json"},
            )
            result = runner.invoke(monitor, ["log", "sess-1", "--format", "json"])

        assert result.exit_code == 0
        body = json.loads(result.output)
        assert "session" in body and "messages" in body
        assert mock_get.call_args.kwargs["params"]["format"] == "json"

    def test_log_missing_session_returns_nonzero(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.get") as mock_get:
            mock_get.return_value = _FakeResponse(status_code=404, text="nope")
            result = runner.invoke(monitor, ["log", "missing"])
        assert result.exit_code != 0
        assert "404" in result.output

    def test_invalid_format_rejected_by_click(self):
        runner = CliRunner()
        result = runner.invoke(monitor, ["log", "sess-1", "--format", "xml"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# cao monitor delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_succeeds_on_204(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.delete") as mock_delete:
            mock_delete.return_value = _FakeResponse(status_code=204, payload=None)
            result = runner.invoke(monitor, ["delete", "sess-1"])

        assert result.exit_code == 0
        assert mock_delete.call_args.args[0].endswith("/monitoring/sessions/sess-1")

    def test_delete_missing_returns_nonzero(self):
        runner = CliRunner()
        with patch(f"{MODULE}.requests.delete") as mock_delete:
            mock_delete.return_value = _FakeResponse(status_code=404, text="nope")
            result = runner.invoke(monitor, ["delete", "sess-1"])

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Connection errors surface as ClickException across all commands
# ---------------------------------------------------------------------------


class TestConnectionError:
    def test_connection_error_on_get_surfaces_clickexception(self):
        runner = CliRunner()
        with patch(
            f"{MODULE}.requests.get",
            side_effect=requests.RequestException("server down"),
        ):
            result = runner.invoke(monitor, ["list"])

        assert result.exit_code != 0
        assert "failed to connect to cao-server" in result.output.lower()


# ---------------------------------------------------------------------------
# Group registered on the main cli
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_monitor_is_registered_on_cli(self):
        from cli_agent_orchestrator.cli.main import cli

        assert "monitor" in cli.commands

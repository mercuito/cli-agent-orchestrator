"""Tests for monitoring routes.

Phase 3 of the monitoring sessions feature. See docs/plans/monitoring-sessions.md.

These tests mock individual ``monitoring_service`` functions while leaving the
exception classes (``SessionNotFound``, ``SessionAlreadyEnded``) intact. That
matters because the routes' ``except monitoring_service.X`` clauses in api/main.py
need the real classes to be importable during dispatch. Phase 2 already
verified service-level correctness against real SQLite; these tests focus on
the HTTP contract — status codes, payload shapes, exception-to-HTTP mapping,
query-parameter plumbing.

The ``/log`` endpoint is deferred to Phase 4 where it will be wired to the
formatter module.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from cli_agent_orchestrator.services import monitoring_service


def _session_dict(
    session_id="sess-1",
    terminal_id="term-A",
    label=None,
    peer_terminal_ids=None,
    started_at=None,
    ended_at=None,
):
    return {
        "id": session_id,
        "terminal_id": terminal_id,
        "label": label,
        "peer_terminal_ids": peer_terminal_ids or [],
        "started_at": started_at or datetime(2026, 4, 18, 10, 0, 0),
        "ended_at": ended_at,
        "status": "ended" if ended_at is not None else "active",
    }


# ---------------------------------------------------------------------------
# POST /monitoring/sessions
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_minimal_body_returns_201_with_session(self, client):
        with patch.object(
            monitoring_service, "create_session", return_value=_session_dict()
        ) as mock_fn:
            resp = client.post(
                "/monitoring/sessions",
                json={"terminal_id": "term-A"},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == "sess-1"
        assert body["status"] == "active"
        mock_fn.assert_called_once_with(
            terminal_id="term-A", peer_terminal_ids=None, label=None
        )

    def test_full_body_forwarded_to_service(self, client):
        with patch.object(
            monitoring_service,
            "create_session",
            return_value=_session_dict(
                label="review-v2", peer_terminal_ids=["P1", "P2"]
            ),
        ) as mock_fn:
            resp = client.post(
                "/monitoring/sessions",
                json={
                    "terminal_id": "term-A",
                    "peer_terminal_ids": ["P1", "P2"],
                    "label": "review-v2",
                },
            )

        assert resp.status_code == 201
        mock_fn.assert_called_once_with(
            terminal_id="term-A",
            peer_terminal_ids=["P1", "P2"],
            label="review-v2",
        )

    def test_missing_terminal_id_returns_422(self, client):
        """FastAPI/Pydantic returns 422 on required-field omission, not 400."""
        resp = client.post("/monitoring/sessions", json={})
        assert resp.status_code == 422

    def test_wrong_type_in_body_returns_422(self, client):
        resp = client.post(
            "/monitoring/sessions",
            json={"terminal_id": "term-A", "peer_terminal_ids": "not-a-list"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /monitoring/sessions/{id}
# ---------------------------------------------------------------------------


class TestGetSession:
    def test_existing_session_returns_200(self, client):
        with patch.object(
            monitoring_service, "get_session", return_value=_session_dict()
        ) as mock_fn:
            resp = client.get("/monitoring/sessions/sess-1")

        assert resp.status_code == 200
        assert resp.json()["id"] == "sess-1"
        mock_fn.assert_called_once_with("sess-1")

    def test_missing_session_returns_404(self, client):
        with patch.object(monitoring_service, "get_session", return_value=None):
            resp = client.get("/monitoring/sessions/missing")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /monitoring/sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_no_filters_returns_200_with_list(self, client):
        with patch.object(
            monitoring_service,
            "list_sessions",
            return_value=[
                _session_dict(session_id="a"),
                _session_dict(session_id="b"),
            ],
        ) as mock_fn:
            resp = client.get("/monitoring/sessions")

        assert resp.status_code == 200
        assert [s["id"] for s in resp.json()] == ["a", "b"]
        mock_fn.assert_called_once_with(
            terminal_id=None,
            peer_terminal_id=None,
            involves=None,
            status=None,
            label=None,
            started_after=None,
            started_before=None,
            limit=50,
            offset=0,
        )

    def test_all_filter_params_forwarded(self, client):
        with patch.object(
            monitoring_service, "list_sessions", return_value=[]
        ) as mock_fn:
            resp = client.get(
                "/monitoring/sessions",
                params={
                    "terminal_id": "T",
                    "peer_terminal_id": "P",
                    "involves": "X",
                    "status": "active",
                    "label": "rev",
                    "started_after": "2026-01-01T00:00:00",
                    "started_before": "2026-12-31T00:00:00",
                    "limit": 10,
                    "offset": 20,
                },
            )

        assert resp.status_code == 200
        kwargs = mock_fn.call_args.kwargs
        assert kwargs["terminal_id"] == "T"
        assert kwargs["peer_terminal_id"] == "P"
        assert kwargs["involves"] == "X"
        assert kwargs["status"] == "active"
        assert kwargs["label"] == "rev"
        assert kwargs["started_after"] == datetime(2026, 1, 1)
        assert kwargs["started_before"] == datetime(2026, 12, 31)
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 20

    def test_invalid_status_returns_422(self, client):
        resp = client.get("/monitoring/sessions", params={"status": "bogus"})
        assert resp.status_code == 422

    def test_limit_below_minimum_returns_422(self, client):
        resp = client.get("/monitoring/sessions", params={"limit": 0})
        assert resp.status_code == 422

    def test_limit_above_maximum_returns_422(self, client):
        resp = client.get("/monitoring/sessions", params={"limit": 501})
        assert resp.status_code == 422

    def test_malformed_datetime_param_returns_422(self, client):
        resp = client.get(
            "/monitoring/sessions", params={"started_after": "not-a-date"}
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /monitoring/sessions/{id}/end
# ---------------------------------------------------------------------------


class TestEndSession:
    def test_end_active_returns_200(self, client):
        ended_dict = _session_dict(ended_at=datetime(2026, 4, 18, 11))
        with patch.object(
            monitoring_service, "end_session", return_value=ended_dict
        ):
            resp = client.post("/monitoring/sessions/sess-1/end")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ended"

    def test_end_missing_returns_404(self, client):
        with patch.object(
            monitoring_service,
            "end_session",
            side_effect=monitoring_service.SessionNotFound("nope"),
        ):
            resp = client.post("/monitoring/sessions/nope/end")

        assert resp.status_code == 404

    def test_end_already_ended_returns_409(self, client):
        with patch.object(
            monitoring_service,
            "end_session",
            side_effect=monitoring_service.SessionAlreadyEnded("sess-1"),
        ):
            resp = client.post("/monitoring/sessions/sess-1/end")

        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /monitoring/sessions/{id}/peers
# ---------------------------------------------------------------------------


class TestAddPeers:
    def test_add_peers_returns_200_with_updated_session(self, client):
        with patch.object(monitoring_service, "add_peers", return_value=None) as add_fn, \
             patch.object(
                 monitoring_service,
                 "get_session",
                 return_value=_session_dict(peer_terminal_ids=["P1", "P2"]),
             ):
            resp = client.post(
                "/monitoring/sessions/sess-1/peers",
                json={"peer_terminal_ids": ["P1", "P2"]},
            )

        assert resp.status_code == 200
        assert resp.json()["peer_terminal_ids"] == ["P1", "P2"]
        add_fn.assert_called_once_with("sess-1", ["P1", "P2"])

    def test_empty_peer_list_returns_422(self, client):
        """An add-peers call with nothing to add is ambiguous at the API
        level — reject rather than silently no-op."""
        resp = client.post(
            "/monitoring/sessions/sess-1/peers",
            json={"peer_terminal_ids": []},
        )
        assert resp.status_code == 422

    def test_missing_body_returns_422(self, client):
        resp = client.post("/monitoring/sessions/sess-1/peers", json={})
        assert resp.status_code == 422

    def test_session_not_found_returns_404(self, client):
        with patch.object(
            monitoring_service,
            "add_peers",
            side_effect=monitoring_service.SessionNotFound("nope"),
        ):
            resp = client.post(
                "/monitoring/sessions/nope/peers",
                json={"peer_terminal_ids": ["P1"]},
            )

        assert resp.status_code == 404

    def test_session_ended_returns_409(self, client):
        with patch.object(
            monitoring_service,
            "add_peers",
            side_effect=monitoring_service.SessionAlreadyEnded("sess-1"),
        ):
            resp = client.post(
                "/monitoring/sessions/sess-1/peers",
                json={"peer_terminal_ids": ["P1"]},
            )

        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /monitoring/sessions/{id}/peers/{peer_id}
# ---------------------------------------------------------------------------


class TestRemovePeer:
    def test_remove_peer_returns_200_with_updated_session(self, client):
        with patch.object(monitoring_service, "remove_peer", return_value=None) as rm_fn, \
             patch.object(
                 monitoring_service,
                 "get_session",
                 return_value=_session_dict(peer_terminal_ids=["P2"]),
             ):
            resp = client.delete("/monitoring/sessions/sess-1/peers/P1")

        assert resp.status_code == 200
        assert resp.json()["peer_terminal_ids"] == ["P2"]
        rm_fn.assert_called_once_with("sess-1", "P1")

    def test_session_not_found_returns_404(self, client):
        with patch.object(
            monitoring_service,
            "remove_peer",
            side_effect=monitoring_service.SessionNotFound("nope"),
        ):
            resp = client.delete("/monitoring/sessions/nope/peers/P1")

        assert resp.status_code == 404

    def test_session_ended_returns_409(self, client):
        with patch.object(
            monitoring_service,
            "remove_peer",
            side_effect=monitoring_service.SessionAlreadyEnded("sess-1"),
        ):
            resp = client.delete("/monitoring/sessions/sess-1/peers/P1")

        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /monitoring/sessions/{id}/messages
# ---------------------------------------------------------------------------


class TestGetMessages:
    def test_returns_ordered_list(self, client):
        msgs = [
            {
                "id": 1,
                "sender_id": "A",
                "receiver_id": "B",
                "message": "hi",
                "status": "DELIVERED",
                "created_at": datetime(2026, 4, 18, 10, 0, 0),
            },
            {
                "id": 2,
                "sender_id": "B",
                "receiver_id": "A",
                "message": "back",
                "status": "DELIVERED",
                "created_at": datetime(2026, 4, 18, 10, 0, 5),
            },
        ]
        with patch.object(
            monitoring_service, "get_session_messages", return_value=msgs
        ):
            resp = client.get("/monitoring/sessions/sess-1/messages")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["message"] == "hi"
        assert body[1]["message"] == "back"

    def test_session_not_found_returns_404(self, client):
        with patch.object(
            monitoring_service,
            "get_session_messages",
            side_effect=monitoring_service.SessionNotFound("nope"),
        ):
            resp = client.get("/monitoring/sessions/nope/messages")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /monitoring/sessions/{id}/log
# ---------------------------------------------------------------------------


class TestGetLog:
    """The /log endpoint composes get_session + get_session_messages and runs
    the result through the formatter. 404 on missing session; format defaults
    to markdown; JSON available via ?format=json."""

    def _session_dict_ended(self):
        return _session_dict(
            label="review-v2",
            peer_terminal_ids=["R1"],
            started_at=datetime(2026, 4, 18, 10, 0, 0),
            ended_at=datetime(2026, 4, 18, 10, 5, 0),
        )

    def _one_message(self):
        return [
            {
                "id": 1,
                "sender_id": "A",
                "receiver_id": "B",
                "message": "hi",
                "status": "DELIVERED",
                "created_at": datetime(2026, 4, 18, 10, 0, 5),
            }
        ]

    def test_default_format_is_markdown(self, client):
        with patch.object(
            monitoring_service, "get_session", return_value=self._session_dict_ended()
        ), patch.object(
            monitoring_service, "get_session_messages", return_value=self._one_message()
        ):
            resp = client.get("/monitoring/sessions/sess-1/log")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        body = resp.text
        assert body.startswith("# Monitoring session: review-v2")
        assert "> hi" in body

    def test_explicit_markdown_format(self, client):
        with patch.object(
            monitoring_service, "get_session", return_value=self._session_dict_ended()
        ), patch.object(
            monitoring_service, "get_session_messages", return_value=[]
        ):
            resp = client.get(
                "/monitoring/sessions/sess-1/log", params={"format": "markdown"}
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")

    def test_json_format_returns_structured_payload(self, client):
        with patch.object(
            monitoring_service, "get_session", return_value=self._session_dict_ended()
        ), patch.object(
            monitoring_service, "get_session_messages", return_value=self._one_message()
        ):
            resp = client.get(
                "/monitoring/sessions/sess-1/log", params={"format": "json"}
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        body = resp.json()
        assert set(body.keys()) == {"session", "messages"}
        assert body["session"]["id"] == "sess-1"
        assert len(body["messages"]) == 1

    def test_missing_session_returns_404(self, client):
        with patch.object(monitoring_service, "get_session", return_value=None):
            resp = client.get("/monitoring/sessions/missing/log")
        assert resp.status_code == 404

    def test_invalid_format_returns_422(self, client):
        resp = client.get(
            "/monitoring/sessions/sess-1/log", params={"format": "xml"}
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /monitoring/sessions/{id}
# ---------------------------------------------------------------------------


class TestDeleteSession:
    def test_delete_returns_204(self, client):
        with patch.object(
            monitoring_service, "delete_session", return_value=None
        ) as mock_fn:
            resp = client.delete("/monitoring/sessions/sess-1")

        assert resp.status_code == 204
        mock_fn.assert_called_once_with("sess-1")

    def test_delete_missing_returns_404(self, client):
        with patch.object(
            monitoring_service,
            "delete_session",
            side_effect=monitoring_service.SessionNotFound("nope"),
        ):
            resp = client.delete("/monitoring/sessions/nope")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Not registered as MCP tools (design decision #2)
# ---------------------------------------------------------------------------


class TestNotExposedAsMcpTool:
    """Design decision #2: monitoring APIs must NOT be exposed as @mcp.tool().
    The MCP server's ``_PENDING_TOOLS`` registry is where agent-facing tools
    are declared. Assert none of ours leaked in there."""

    def test_monitoring_tools_absent_from_mcp_pending_registry(self):
        from cli_agent_orchestrator.mcp_server import server

        names = {name for name, _, _ in server._PENDING_TOOLS}
        banned = {
            "create_monitoring_session",
            "end_monitoring_session",
            "delete_monitoring_session",
            "add_monitoring_peers",
            "remove_monitoring_peer",
            "list_monitoring_sessions",
            "get_monitoring_session",
            "get_monitoring_messages",
            "get_monitoring_log",
        }
        assert names.isdisjoint(banned), (
            f"Monitoring endpoints leaked into MCP tool surface: "
            f"{names & banned}"
        )

"""Tests for monitoring routes under the single-session, query-time-filter
model. See docs/plans/monitoring-sessions.md.

Route tests mock individual ``monitoring_service`` functions while leaving
the exception classes intact so ``except monitoring_service.X`` clauses in
api/main.py dispatch correctly.
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
    started_at=None,
    ended_at=None,
):
    return {
        "id": session_id,
        "terminal_id": terminal_id,
        "label": label,
        "started_at": started_at or datetime(2026, 4, 18, 10, 0, 0),
        "ended_at": ended_at,
        "status": "ended" if ended_at is not None else "active",
    }


# ---------------------------------------------------------------------------
# POST /monitoring/sessions
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_minimal_body_returns_201(self, client):
        with patch.object(
            monitoring_service, "create_session", return_value=_session_dict()
        ) as mock_fn:
            resp = client.post(
                "/monitoring/sessions", json={"terminal_id": "term-A"}
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == "sess-1"
        assert body["status"] == "active"
        # Response no longer carries peer_terminal_ids
        assert "peer_terminal_ids" not in body
        mock_fn.assert_called_once_with(terminal_id="term-A", label=None)

    def test_body_with_label_forwarded(self, client):
        with patch.object(
            monitoring_service,
            "create_session",
            return_value=_session_dict(label="review-v2"),
        ) as mock_fn:
            resp = client.post(
                "/monitoring/sessions",
                json={"terminal_id": "term-A", "label": "review-v2"},
            )

        assert resp.status_code == 201
        mock_fn.assert_called_once_with(terminal_id="term-A", label="review-v2")

    def test_legacy_peer_field_silently_ignored(self, client):
        """Clients on the old shape still work: Pydantic v2 default is to
        ignore extra fields. Pin this so a future switch to
        ``extra='forbid'`` on the request model has to be a conscious
        breaking-change decision, not a silent one."""
        with patch.object(
            monitoring_service, "create_session", return_value=_session_dict()
        ) as mock_fn:
            resp = client.post(
                "/monitoring/sessions",
                json={"terminal_id": "term-A", "peer_terminal_ids": ["legacy"]},
            )
        assert resp.status_code == 201
        # The service call must not receive the legacy field
        assert "peer_terminal_ids" not in mock_fn.call_args.kwargs

    def test_missing_terminal_id_returns_422(self, client):
        resp = client.post("/monitoring/sessions", json={})
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
    def test_no_filters(self, client):
        with patch.object(
            monitoring_service,
            "list_sessions",
            return_value=[_session_dict(session_id="a"), _session_dict(session_id="b")],
        ) as mock_fn:
            resp = client.get("/monitoring/sessions")

        assert resp.status_code == 200
        assert [s["id"] for s in resp.json()] == ["a", "b"]
        mock_fn.assert_called_once_with(
            terminal_id=None,
            status=None,
            label=None,
            started_after=None,
            started_before=None,
            limit=50,
            offset=0,
        )

    def test_supported_filters_forwarded(self, client):
        with patch.object(
            monitoring_service, "list_sessions", return_value=[]
        ) as mock_fn:
            resp = client.get(
                "/monitoring/sessions",
                params={
                    "terminal_id": "T",
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
        assert kwargs["status"] == "active"
        assert kwargs["label"] == "rev"
        assert kwargs["started_after"] == datetime(2026, 1, 1)
        assert kwargs["started_before"] == datetime(2026, 12, 31)
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 20

    def test_peer_and_involves_filters_removed_from_list(self, client):
        """These query params used to exist and are now gone. FastAPI
        silently ignores unknown query params, so we can't assert 422 —
        we can assert the service is NOT called with them."""
        with patch.object(
            monitoring_service, "list_sessions", return_value=[]
        ) as mock_fn:
            client.get(
                "/monitoring/sessions",
                params={"peer_terminal_id": "P", "involves": "X"},
            )

        kwargs = mock_fn.call_args.kwargs
        assert "peer_terminal_id" not in kwargs
        assert "involves" not in kwargs

    def test_invalid_status_returns_422(self, client):
        resp = client.get("/monitoring/sessions", params={"status": "bogus"})
        assert resp.status_code == 422

    def test_limit_below_minimum_returns_422(self, client):
        resp = client.get("/monitoring/sessions", params={"limit": 0})
        assert resp.status_code == 422

    def test_limit_above_maximum_returns_422(self, client):
        resp = client.get("/monitoring/sessions", params={"limit": 501})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /monitoring/sessions/{id}/end
# ---------------------------------------------------------------------------


class TestEndSession:
    def test_end_active_returns_200(self, client):
        ended = _session_dict(ended_at=datetime(2026, 4, 18, 11))
        with patch.object(
            monitoring_service, "end_session", return_value=ended
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
# Peer endpoints are gone
# ---------------------------------------------------------------------------


class TestPeerEndpointsRemoved:
    """Under the single-session model there is no per-session peer set to
    add/remove. The routes should 404 or 405 — confirm they're not
    accidentally still registered."""

    def test_add_peer_endpoint_gone(self, client):
        resp = client.post(
            "/monitoring/sessions/sess-1/peers",
            json={"peer_terminal_ids": ["P1"]},
        )
        assert resp.status_code in (404, 405)

    def test_remove_peer_endpoint_gone(self, client):
        resp = client.delete("/monitoring/sessions/sess-1/peers/P1")
        assert resp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# GET /monitoring/sessions/{id}/messages
# ---------------------------------------------------------------------------


class TestGetMessages:
    def _msg(self, **overrides):
        base = {
            "id": 1,
            "sender_id": "A",
            "receiver_id": "B",
            "message": "hi",
            "status": "DELIVERED",
            "created_at": datetime(2026, 4, 18, 10, 0, 0),
        }
        base.update(overrides)
        return base

    def test_returns_ordered_list(self, client):
        msgs = [self._msg(id=1, message="hi"), self._msg(id=2, message="back")]
        with patch.object(
            monitoring_service, "get_session_messages", return_value=msgs
        ) as mock_fn:
            resp = client.get("/monitoring/sessions/sess-1/messages")

        assert resp.status_code == 200
        assert [m["message"] for m in resp.json()] == ["hi", "back"]
        mock_fn.assert_called_once_with(
            "sess-1", peers=[], started_after=None, started_before=None
        )

    def test_peer_filter_forwarded_as_list(self, client):
        with patch.object(
            monitoring_service, "get_session_messages", return_value=[]
        ) as mock_fn:
            resp = client.get(
                "/monitoring/sessions/sess-1/messages",
                params=[("peer", "R1"), ("peer", "R2")],
            )

        assert resp.status_code == 200
        mock_fn.assert_called_once_with(
            "sess-1", peers=["R1", "R2"], started_after=None, started_before=None
        )

    def test_time_window_filter_forwarded(self, client):
        with patch.object(
            monitoring_service, "get_session_messages", return_value=[]
        ) as mock_fn:
            resp = client.get(
                "/monitoring/sessions/sess-1/messages",
                params={
                    "started_after": "2026-04-18T10:00:00",
                    "started_before": "2026-04-18T10:05:00",
                },
            )

        assert resp.status_code == 200
        kwargs = mock_fn.call_args.kwargs
        assert kwargs["started_after"] == datetime(2026, 4, 18, 10, 0, 0)
        assert kwargs["started_before"] == datetime(2026, 4, 18, 10, 5, 0)

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
    def _session_ended(self):
        return _session_dict(
            label="review-v2",
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
            monitoring_service, "get_session", return_value=self._session_ended()
        ), patch.object(
            monitoring_service, "get_session_messages", return_value=self._one_message()
        ):
            resp = client.get("/monitoring/sessions/sess-1/log")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        body = resp.text
        assert body.startswith("# Monitoring session: review-v2")
        # No filter applied → no Filter line
        assert "Filter:" not in body

    def test_json_format_without_filter_omits_filter_key(self, client):
        with patch.object(
            monitoring_service, "get_session", return_value=self._session_ended()
        ), patch.object(
            monitoring_service, "get_session_messages", return_value=self._one_message()
        ):
            resp = client.get(
                "/monitoring/sessions/sess-1/log", params={"format": "json"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"session", "messages"}

    def test_peer_filter_forwarded_and_reflected_in_artifact(self, client):
        with patch.object(
            monitoring_service, "get_session", return_value=self._session_ended()
        ), patch.object(
            monitoring_service,
            "get_session_messages",
            return_value=self._one_message(),
        ) as mock_msgs:
            resp = client.get(
                "/monitoring/sessions/sess-1/log",
                params=[("peer", "R1"), ("peer", "R2")],
            )

        assert resp.status_code == 200
        # Filter reached the service
        mock_msgs.assert_called_once_with(
            "sess-1", peers=["R1", "R2"], started_after=None, started_before=None
        )
        # And is declared in the rendered artifact
        assert "**Filter:** peers = R1, R2" in resp.text

    def test_json_format_with_filter_includes_filter_key(self, client):
        with patch.object(
            monitoring_service, "get_session", return_value=self._session_ended()
        ), patch.object(
            monitoring_service, "get_session_messages", return_value=[]
        ):
            resp = client.get(
                "/monitoring/sessions/sess-1/log",
                params=[("format", "json"), ("peer", "R1")],
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "filter" in body
        assert body["filter"]["peers"] == ["R1"]

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
# Not registered as MCP tools
# ---------------------------------------------------------------------------


class TestNotExposedAsMcpTool:
    def test_monitoring_tools_absent_from_mcp_pending_registry(self):
        from cli_agent_orchestrator.mcp_server import server

        names = {name for name, _, _ in server._PENDING_TOOLS}
        banned = {
            "create_monitoring_session",
            "end_monitoring_session",
            "delete_monitoring_session",
            "list_monitoring_sessions",
            "get_monitoring_session",
            "get_monitoring_messages",
            "get_monitoring_log",
        }
        assert names.isdisjoint(banned)

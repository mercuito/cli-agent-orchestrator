"""Tests for operator baton HTTP routes."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from cli_agent_orchestrator.models.baton import Baton, BatonEvent, BatonStatus
from cli_agent_orchestrator.services import baton_service


def _baton(**overrides):
    base = {
        "id": "baton-1",
        "title": "T06",
        "status": BatonStatus.ACTIVE,
        "originator_id": "originator",
        "current_holder_id": "impl",
        "return_stack": ["reviewer"],
        "expected_next_action": "inspect",
        "created_at": datetime(2026, 5, 4, 10, 0, 0),
        "updated_at": datetime(2026, 5, 4, 10, 5, 0),
        "last_nudged_at": None,
        "completed_at": None,
    }
    base.update(overrides)
    return Baton(**base)


def _event(**overrides):
    base = {
        "id": 1,
        "baton_id": "baton-1",
        "event_type": "create",
        "actor_id": "originator",
        "from_holder_id": None,
        "to_holder_id": "impl",
        "message": "start",
        "created_at": datetime(2026, 5, 4, 10, 0, 0),
    }
    base.update(overrides)
    return BatonEvent(**base)


class TestListBatons:
    def test_defaults_to_active_batons_for_dashboard_visibility(self, client):
        with patch("cli_agent_orchestrator.api.main.list_batons", return_value=[]) as mock_fn:
            resp = client.get("/batons")

        assert resp.status_code == 200
        mock_fn.assert_called_once_with(
            status=BatonStatus.ACTIVE,
            holder_id=None,
            originator_id=None,
            limit=50,
            offset=0,
        )

    def test_filters_are_forwarded(self, client):
        with patch(
            "cli_agent_orchestrator.api.main.list_batons",
            return_value=[_baton(status=BatonStatus.BLOCKED)],
        ) as mock_fn:
            resp = client.get(
                "/batons",
                params={
                    "status": "blocked",
                    "holder_id": "impl",
                    "originator_id": "originator",
                    "limit": 10,
                    "offset": 20,
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["status"] == "blocked"
        mock_fn.assert_called_once_with(
            status=BatonStatus.BLOCKED,
            holder_id="impl",
            originator_id="originator",
            limit=10,
            offset=20,
        )

    def test_invalid_status_returns_422(self, client):
        resp = client.get("/batons", params={"status": "bogus"})
        assert resp.status_code == 422


class TestGetBaton:
    def test_existing_baton_returns_shape(self, client):
        with patch(
            "cli_agent_orchestrator.api.main.get_baton_record",
            return_value=_baton(),
        ):
            resp = client.get("/batons/baton-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "baton-1"
        assert body["current_holder_id"] == "impl"
        assert body["originator_id"] == "originator"
        assert body["return_stack"] == ["reviewer"]
        assert body["expected_next_action"] == "inspect"
        assert "created_at" in body
        assert "updated_at" in body
        assert "last_nudged_at" in body
        assert "completed_at" in body

    def test_missing_baton_returns_404(self, client):
        with patch("cli_agent_orchestrator.api.main.get_baton_record", return_value=None):
            resp = client.get("/batons/missing")
        assert resp.status_code == 404


class TestBatonEvents:
    def test_events_return_audit_shape(self, client):
        with patch("cli_agent_orchestrator.api.main.get_baton_record", return_value=_baton()):
            with patch(
                "cli_agent_orchestrator.api.main.list_baton_events",
                return_value=[_event()],
            ):
                resp = client.get("/batons/baton-1/events")

        assert resp.status_code == 200
        body = resp.json()[0]
        assert body["event_type"] == "create"
        assert body["actor_id"] == "originator"
        assert body["from_holder_id"] is None
        assert body["to_holder_id"] == "impl"
        assert body["message"] == "start"
        assert "created_at" in body

    def test_missing_baton_returns_404(self, client):
        with patch("cli_agent_orchestrator.api.main.get_baton_record", return_value=None):
            resp = client.get("/batons/missing/events")
        assert resp.status_code == 404


class TestRecoveryRoutes:
    def test_cancel_uses_operator_recovery_and_default_actor(self, client):
        canceled = _baton(
            status=BatonStatus.CANCELED,
            current_holder_id=None,
            expected_next_action=None,
        )
        with patch.object(baton_service, "cancel_baton", return_value=canceled) as mock_fn:
            resp = client.post(
                "/batons/baton-1/cancel",
                json={"message": "operator cleanup"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "canceled"
        mock_fn.assert_called_once_with(
            baton_id="baton-1",
            actor_id="operator",
            message="operator cleanup",
            operator_recovery=True,
        )

    def test_reassign_uses_operator_recovery_and_explicit_actor(self, client):
        reassigned = _baton(current_holder_id="new-holder", expected_next_action="resume")
        with patch.object(baton_service, "reassign_baton", return_value=reassigned) as mock_fn:
            resp = client.post(
                "/batons/baton-1/reassign",
                json={
                    "actor_id": "ops",
                    "holder_id": "new-holder",
                    "message": "recover",
                    "expected_next_action": "resume",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["current_holder_id"] == "new-holder"
        mock_fn.assert_called_once_with(
            baton_id="baton-1",
            actor_id="ops",
            receiver_id="new-holder",
            message="recover",
            expected_next_action="resume",
            operator_recovery=True,
        )

    def test_reassign_requires_holder(self, client):
        resp = client.post("/batons/baton-1/reassign", json={})
        assert resp.status_code == 422

    def test_missing_baton_maps_to_404(self, client):
        with patch.object(
            baton_service,
            "cancel_baton",
            side_effect=baton_service.BatonNotFound("missing"),
        ):
            resp = client.post("/batons/missing/cancel", json={})
        assert resp.status_code == 404

    def test_invalid_transition_maps_to_409(self, client):
        with patch.object(
            baton_service,
            "cancel_baton",
            side_effect=baton_service.BatonInvalidTransition("final"),
        ):
            resp = client.post("/batons/baton-1/cancel", json={})
        assert resp.status_code == 409

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cli_agent_orchestrator.agent_identity import AgentIdentityConfigError
from cli_agent_orchestrator.services.agent_identity_manager import AgentIdentityStatus


@dataclass
class _FakeIdentityManager:
    statuses: tuple[AgentIdentityStatus, ...]

    def list_statuses(self, *, active=None):
        if active is None:
            return self.statuses
        return tuple(status for status in self.statuses if status.active is active)

    def status_for_identity(self, agent_id: str):
        for status in self.statuses:
            if status.agent_identity_id == agent_id:
                return status
        raise AgentIdentityConfigError(f"Unknown CAO agent identity: {agent_id}")


def _status(
    agent_id: str = "implementation_partner",
    *,
    active: bool = False,
) -> AgentIdentityStatus:
    return AgentIdentityStatus(
        agent_identity_id=agent_id,
        display_name="Implementation Partner",
        agent_profile="developer",
        cli_provider="codex",
        active=active,
        active_terminal_id="abcd1234" if active else None,
        active_workspace_context_id="wctx_abc" if active else None,
        last_active_at=datetime(2026, 5, 13, 12, 0, 0) if active else None,
    )


def test_list_agent_identities_returns_stable_status_shape(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_identity_manager",
        lambda: _FakeIdentityManager((_status(active=True), _status("reviewer"))),
    )

    response = client.get("/agents/identities")

    assert response.status_code == 200
    assert response.json() == [
        {
            "agent_identity_id": "implementation_partner",
            "display_name": "Implementation Partner",
            "agent_profile": "developer",
            "cli_provider": "codex",
            "active": True,
            "active_terminal_id": "abcd1234",
            "active_workspace_context_id": "wctx_abc",
            "last_active_at": "2026-05-13T12:00:00",
        },
        {
            "agent_identity_id": "reviewer",
            "display_name": "Implementation Partner",
            "agent_profile": "developer",
            "cli_provider": "codex",
            "active": False,
            "active_terminal_id": None,
            "active_workspace_context_id": None,
            "last_active_at": None,
        },
    ]


def test_list_agent_identities_active_filter(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_identity_manager",
        lambda: _FakeIdentityManager((_status(active=True), _status("reviewer"))),
    )

    response = client.get("/agents/identities?active=true")

    assert response.status_code == 200
    assert [row["agent_identity_id"] for row in response.json()] == [
        "implementation_partner"
    ]


def test_get_agent_identity_unknown_returns_404(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_identity_manager",
        lambda: _FakeIdentityManager((_status(active=True),)),
    )

    response = client.get("/agents/identities/missing")

    assert response.status_code == 404
    assert "Unknown CAO agent identity" in response.json()["detail"]


def test_runtime_terminal_endpoint_uses_identity_manager_status(client, monkeypatch):
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.default_agent_identity_manager",
        lambda: _FakeIdentityManager((_status(active=True),)),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.terminal_service.get_terminal",
        lambda terminal_id: {
            "id": terminal_id,
            "name": "developer-0000",
            "provider": "codex",
            "session_name": "cao-implementation-partner",
            "agent_profile": "developer",
            "agent_identity_id": "implementation_partner",
            "workspace_context_id": "wctx_abc",
            "status": "idle",
            "last_active": datetime(2026, 5, 13, 12, 0, 0),
        },
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main.create_terminal_dashboard_token",
        lambda terminal_id: f"token-{terminal_id}",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.api.main._agent_dashboard_request_authorized",
        lambda request, agent_id, agent_token: True,
    )

    response = client.get("/agents/runtime/implementation_partner/terminal")

    assert response.status_code == 200
    assert response.json()["terminal"]["id"] == "abcd1234"
    assert response.json()["terminal_token"] == "token-abcd1234"

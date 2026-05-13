from __future__ import annotations

from datetime import datetime

import pytest

from cli_agent_orchestrator.agent_identity import (
    AgentIdentity,
    AgentIdentityConfigError,
    AgentIdentityRegistry,
)
from cli_agent_orchestrator.services.agent_identity_manager import AgentIdentityManager


def _identity(identity_id: str = "identity_a", **overrides: str) -> AgentIdentity:
    values = {
        "id": identity_id,
        "display_name": identity_id.replace("_", " ").title(),
        "agent_profile": "developer",
        "cli_provider": "codex",
        "workdir": "/repo",
        "session_name": identity_id.replace("_", "-"),
    }
    values.update(overrides)
    return AgentIdentity(**values)


def _manager(
    *,
    identities: dict[str, AgentIdentity] | None = None,
    providers=(),
    terminals=None,
) -> AgentIdentityManager:
    return AgentIdentityManager(
        configured_identities=AgentIdentityRegistry(identities or {}),
        identity_providers=providers,
        terminal_lister=lambda: list(terminals or []),
        terminal_metadata_resolver=lambda terminal_id: {
            terminal["id"]: terminal for terminal in terminals or []
        }.get(terminal_id),
        profile_loader=lambda profile: object(),
    )


class _Provider:
    def __init__(self, *identities: AgentIdentity) -> None:
        self.identities = {identity.id: identity for identity in identities}

    def resolve_identity_for_agent_id(self, agent_id: str) -> AgentIdentity:
        try:
            return self.identities[agent_id]
        except KeyError as exc:
            raise AgentIdentityConfigError(agent_id) from exc

    def list_agent_identities(self) -> tuple[AgentIdentity, ...]:
        return tuple(self.identities.values())


def test_configured_identities_register_list_and_resolve_through_manager():
    identity = _identity()
    manager = _manager(identities={identity.id: identity})

    assert manager.resolve_identity("identity_a") == identity
    assert [status.agent_identity_id for status in manager.list_statuses()] == ["identity_a"]
    assert manager.status_for_identity("identity_a").active is False


def test_invalid_identity_registration_is_rejected_at_manager_boundary():
    manager = _manager()

    with pytest.raises(AgentIdentityConfigError, match="supported provider"):
        manager.register_identity(_identity(cli_provider="not-a-provider"))

    with pytest.raises(AgentIdentityConfigError, match="agent_identity_id"):
        manager.register_identity(_identity(""))


def test_provider_resolved_identity_enters_manager_registration_boundary():
    identity = _identity("provider_identity")
    manager = _manager(providers=(_Provider(identity),))

    assert manager.resolve_identity("provider_identity") == identity
    assert manager.list_identities() == (identity,)


def test_require_registered_identity_rejects_raw_mismatch_before_terminal_boundary():
    configured = _identity("identity_a", workdir="/configured")
    raw = _identity("identity_a", workdir="/raw")
    manager = _manager(identities={configured.id: configured})

    with pytest.raises(AgentIdentityConfigError, match="does not match"):
        manager.require_registered_identity(raw)


def test_active_and_inactive_status_derive_from_terminal_rows():
    active_identity = _identity("identity_a")
    inactive_identity = _identity("identity_b")
    last_active = datetime(2026, 5, 13, 12, 0, 0)
    manager = _manager(
        identities={
            active_identity.id: active_identity,
            inactive_identity.id: inactive_identity,
        },
        terminals=[
            {
                "id": "terminal-a",
                "agent_identity_id": "identity_a",
                "workspace_context_id": "wctx-a",
                "last_active": last_active,
            }
        ],
    )

    active = manager.status_for_identity("identity_a")
    inactive = manager.status_for_identity("identity_b")

    assert active.active is True
    assert active.active_terminal_id == "terminal-a"
    assert active.active_workspace_context_id == "wctx-a"
    assert active.last_active_at == last_active
    assert inactive.active is False
    assert inactive.active_terminal_id is None
    assert [status.agent_identity_id for status in manager.list_statuses(active=True)] == [
        "identity_a"
    ]


def test_orphaned_terminal_references_are_diagnostic_not_valid_identities():
    manager = _manager(
        identities={"identity_a": _identity("identity_a")},
        terminals=[
            {
                "id": "terminal-a",
                "agent_identity_id": "identity_a",
                "workspace_context_id": "wctx-a",
            },
            {
                "id": "terminal-orphan",
                "agent_identity_id": "missing",
                "workspace_context_id": "wctx-orphan",
            },
        ],
    )

    assert [status.agent_identity_id for status in manager.list_statuses(active=True)] == [
        "identity_a"
    ]
    orphan = manager.orphaned_terminal_references()[0]
    assert orphan.terminal_id == "terminal-orphan"
    assert orphan.agent_identity_id == "missing"


def test_terminal_identity_resolution_fails_for_unknown_mapping():
    manager = _manager(
        terminals=[
            {
                "id": "terminal-orphan",
                "agent_identity_id": "missing",
                "workspace_context_id": "wctx-orphan",
            }
        ],
    )

    with pytest.raises(AgentIdentityConfigError, match="references unknown"):
        manager.identity_for_terminal("terminal-orphan")

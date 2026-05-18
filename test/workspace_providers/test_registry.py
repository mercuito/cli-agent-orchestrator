"""Tests for workspace-provider startup and registry behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import ClassVar

import pytest

from cli_agent_orchestrator.agent import (
    Agent,
    AgentWorkspaceConfig,
    LinearConfig,
    LinearToolAccessConfig,
    write_agent,
)
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearWorkspaceProvider,
    get_linear_workspace_provider,
)
from cli_agent_orchestrator.workspace_providers import (
    UnknownWorkspaceProviderError,
    WorkspaceProviderEvent,
    WorkspaceProviderEventDispatcher,
    WorkspaceProviderRegistry,
    initialize_enabled_workspace_providers,
    load_enabled_provider_tool_access_policies,
)


def _future_token_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def _agents_root(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    return agents


def _write_agent(
    agents_root,
    agent_id: str,
    *,
    workspace_setup: str | None = None,
    app_key: str | None = None,
    app_user_id: str | None = None,
    app_user_name: str | None = None,
    access_token: str | None = None,
    token_expires_at: str | None = None,
    tool_access: tuple[LinearToolAccessConfig, ...] = (),
) -> None:
    write_agent(
        Agent(
            id=agent_id,
            display_name=agent_id.replace("_", " ").title(),
            cli_provider="codex",
            workdir="/repo",
            session_name=agent_id.replace("_", "-"),
            prompt="",
            workspace=AgentWorkspaceConfig(setup=workspace_setup),
            linear=(
                LinearConfig(
                    app_key=app_key,
                    app_user_id=app_user_id,
                    app_user_name=app_user_name,
                    access_token=access_token,
                    token_expires_at=token_expires_at,
                    tool_access=tool_access,
                )
                if app_key
                else None
            ),
        ),
        agents_root=agents_root,
    )


def test_unknown_enabled_workspace_provider_fails_clearly(tmp_path):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["jira"]\n')
    agents = _agents_root(tmp_path)

    with pytest.raises(UnknownWorkspaceProviderError, match="jira"):
        initialize_enabled_workspace_providers(
            enabled_config_path=enabled,
            agents_config_path=agents,
        )


def test_initialize_enabled_workspace_providers_loads_linear_provider(tmp_path, monkeypatch):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["linear"]\n')
    agents = _agents_root(tmp_path)
    _write_agent(
        agents,
        "implementation_partner",
        app_key="implementation_partner",
        app_user_id="app-user-impl",
        app_user_name="Implementation Partner",
        access_token="access-token",
        token_expires_at=_future_token_expires_at(),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider._default_check_linear_presence_credentials",
        lambda presence: {"id": presence.app_user_id, "name": presence.app_user_name},
    )

    providers = initialize_enabled_workspace_providers(
        enabled_config_path=enabled,
        agents_config_path=agents,
    )

    assert len(providers) == 1
    assert isinstance(providers[0], LinearWorkspaceProvider)
    resolved = get_linear_workspace_provider().resolve_event(
        {"_cao_linear_app_key": "implementation_partner"}
    )
    assert resolved.presence.app_user_id == "app-user-impl"
    assert resolved.agent.session_name == "implementation-partner"


def test_initialize_enabled_workspace_providers_defers_linear_credential_preflight(
    tmp_path, monkeypatch
):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["linear"]\n')
    agents = _agents_root(tmp_path)
    _write_agent(
        agents,
        "implementation_partner",
        app_key="implementation_partner",
        app_user_id="app-user-impl",
        app_user_name="Implementation Partner",
        access_token="expired-access-token",
        token_expires_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider._default_check_linear_presence_credentials",
        lambda presence: (_ for _ in ()).throw(AssertionError("credential preflight called")),
    )

    providers = initialize_enabled_workspace_providers(
        enabled_config_path=enabled,
        agents_config_path=agents,
    )

    assert len(providers) == 1
    assert isinstance(providers[0], LinearWorkspaceProvider)


def test_initialize_enabled_workspace_providers_registers_declared_provider_events(
    tmp_path, monkeypatch
):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["example"]\n')
    agents = _agents_root(tmp_path)
    dispatcher = WorkspaceProviderEventDispatcher()

    @dataclass(frozen=True)
    class ExampleEvent(WorkspaceProviderEvent):
        provider_name: ClassVar[str] = "example"
        event_name: ClassVar[str] = "created"

    class ExampleProvider:
        name = "example"

        def initialize(self):
            pass

        def published_events(self):
            return (ExampleEvent,)

    registry = WorkspaceProviderRegistry({"example": lambda agent_registry: ExampleProvider()})
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_providers.registry.default_workspace_provider_event_dispatcher",
        lambda: dispatcher,
    )

    initialize_enabled_workspace_providers(
        enabled_config_path=enabled,
        agents_config_path=agents,
        registry=registry,
    )

    assert dispatcher.published_events("example") == (ExampleEvent,)


def test_initialize_workspace_providers_does_not_start_linear_when_unconfigured(
    tmp_path,
):
    enabled = tmp_path / "missing-workspace-providers.toml"
    agents = _agents_root(tmp_path)
    initialized = []

    providers = initialize_enabled_workspace_providers(
        enabled_config_path=enabled,
        agents_config_path=agents,
    )

    assert providers == initialized


def test_provider_tool_policy_loading_does_not_initialize_linear_without_tool_access(
    tmp_path, monkeypatch
):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["linear"]\n')
    agents = _agents_root(tmp_path)
    _write_agent(
        agents,
        "discovery_partner",
        app_key="discovery_partner",
        app_user_id="app-user-discovery",
        app_user_name="Discovery Partner",
        access_token="access-token",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider._default_check_linear_presence_credentials",
        lambda presence: (_ for _ in ()).throw(AssertionError("credential preflight called")),
    )

    policies = load_enabled_provider_tool_access_policies(
        enabled_config_path=enabled,
        agents_config_path=agents,
    )

    assert policies == {}


def test_provider_tool_policy_loading_prunes_linear_access_outside_workspace_setup(
    tmp_path, monkeypatch
):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["linear"]\n')
    agents = _agents_root(tmp_path)
    _write_agent(
        agents,
        "implementation_partner",
        workspace_setup="cao_delivery",
        app_key="implementation_partner",
        access_token="access-token",
        tool_access=(
            LinearToolAccessConfig(
                access_id="impl_reads",
                tools=("cao_linear.get_issue",),
                issues=("CAO-1",),
            ),
        ),
    )
    _write_agent(
        agents,
        "discovery_partner",
        app_key="discovery_partner",
        access_token="access-token",
        tool_access=(
            LinearToolAccessConfig(
                access_id="discovery_reads",
                tools=("cao_linear.get_issue",),
                issues=("CAO-2",),
            ),
        ),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider._default_check_linear_presence_credentials",
        lambda presence: (_ for _ in ()).throw(AssertionError("credential preflight called")),
    )

    policies = load_enabled_provider_tool_access_policies(
        enabled_config_path=enabled,
        agents_config_path=agents,
    )

    assert [entry.agent_id for entry in policies["linear"].access] == ["implementation_partner"]

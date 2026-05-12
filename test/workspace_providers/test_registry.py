"""Tests for workspace-provider startup and registry behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import ClassVar

import pytest

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


def test_unknown_enabled_workspace_provider_fails_clearly(tmp_path):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["jira"]\n')
    agents = tmp_path / "agents.toml"
    agents.write_text("")

    with pytest.raises(UnknownWorkspaceProviderError, match="jira"):
        initialize_enabled_workspace_providers(
            enabled_config_path=enabled,
            agents_config_path=agents,
        )


def test_initialize_enabled_workspace_providers_loads_linear_provider(tmp_path, monkeypatch):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["linear"]\n')
    agents = tmp_path / "agents.toml"
    agents.write_text("""
[agents.implementation_partner]
display_name = "Implementation Partner"
agent_profile = "developer"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"
""")
    linear_config = tmp_path / "workspace-providers" / "linear.toml"
    linear_config.parent.mkdir(parents=True)
    linear_config.write_text(f"""
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
app_user_id = "app-user-impl"
app_user_name = "Implementation Partner"
access_token = "access-token"
token_expires_at = "{_future_token_expires_at()}"
""")
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.LINEAR_PROVIDER_CONFIG_PATH",
        linear_config,
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
    assert resolved.identity.session_name == "implementation-partner"


def test_initialize_enabled_workspace_providers_registers_declared_provider_events(
    tmp_path, monkeypatch
):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["example"]\n')
    agents = tmp_path / "agents.toml"
    agents.write_text("")
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


def test_initialize_workspace_providers_starts_legacy_linear_provider_when_unconfigured(
    tmp_path, monkeypatch
):
    enabled = tmp_path / "missing-workspace-providers.toml"
    agents = tmp_path / "agents.toml"
    agents.write_text("")
    initialized = []

    class FakeLinearProvider:
        name = "linear"

        def __init__(self, *, agent_registry):
            self.agent_registry = agent_registry

        def initialize(self):
            initialized.append(self)

    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.has_legacy_linear_provider_config",
        lambda: True,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.LinearWorkspaceProvider",
        FakeLinearProvider,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.set_default_linear_workspace_provider",
        lambda provider: None,
    )

    providers = initialize_enabled_workspace_providers(
        enabled_config_path=enabled,
        agents_config_path=agents,
    )

    assert providers == initialized
    assert len(providers) == 1


def test_provider_tool_policy_loading_does_not_initialize_linear_without_tool_access(
    tmp_path, monkeypatch
):
    enabled = tmp_path / "workspace-providers.toml"
    enabled.write_text('enabled = ["linear"]\n')
    agents = tmp_path / "agents.toml"
    agents.write_text("""
[agents.discovery_partner]
display_name = "Discovery Partner"
agent_profile = "developer"
cli_provider = "codex"
workdir = "/repo"
session_name = "discovery-partner"
""")
    linear_config = tmp_path / "workspace-providers" / "linear.toml"
    linear_config.parent.mkdir(parents=True)
    linear_config.write_text("""
[presences.discovery_partner]
agent_id = "discovery_partner"
app_key = "discovery_partner"
app_user_id = "app-user-discovery"
app_user_name = "Discovery Partner"
access_token = "access-token"
""")
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.LINEAR_PROVIDER_CONFIG_PATH",
        linear_config,
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

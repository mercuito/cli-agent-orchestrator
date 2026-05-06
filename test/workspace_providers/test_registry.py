"""Tests for workspace-provider startup and registry behavior."""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.linear.workspace_provider import (
    LinearWorkspaceProvider,
    get_linear_workspace_provider,
)
from cli_agent_orchestrator.workspace_providers import (
    UnknownWorkspaceProviderError,
    initialize_enabled_workspace_providers,
)


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
    linear_config.write_text("""
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
app_user_id = "app-user-impl"
app_user_name = "Implementation Partner"
""")
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.LINEAR_PROVIDER_CONFIG_PATH",
        linear_config,
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

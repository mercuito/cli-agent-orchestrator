"""Tests for Linear workspace-provider config and presence resolution."""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.agent_identity import AgentIdentity, AgentIdentityRegistry
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearWorkspaceProvider,
    LinearWorkspaceProviderConfigError,
    configured_app_keys,
    load_linear_provider_config,
    linear_app_env,
    persist_linear_oauth_install,
)


def _agents() -> AgentIdentityRegistry:
    return AgentIdentityRegistry(
        {
            "implementation_partner": AgentIdentity(
                id="implementation_partner",
                display_name="Implementation Partner",
                agent_profile="developer",
                cli_provider="codex",
                workdir="/repo",
                session_name="implementation-partner",
            ),
            "discovery_partner": AgentIdentity(
                id="discovery_partner",
                display_name="Discovery Partner",
                agent_profile="reviewer",
                cli_provider="claude_code",
                workdir="/other",
                session_name="discovery-partner",
            ),
        }
    )


def _linear_config(tmp_path, body: str):
    path = tmp_path / "workspace-providers" / "linear.toml"
    path.parent.mkdir(parents=True)
    path.write_text(body)
    return path


def test_configured_linear_app_key_resolves_to_cao_identity(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
app_user_id = "app-user-impl"
app_user_name = "Implementation Partner"
""",
    )
    provider = LinearWorkspaceProvider(agent_registry=_agents(), config_path=config)
    provider.initialize()

    resolved = provider.resolve_event({"_cao_linear_app_key": "implementation_partner"})

    assert resolved.presence.agent_id == "implementation_partner"
    assert resolved.identity.session_name == "implementation-partner"


def test_configured_linear_app_user_id_resolves_to_cao_identity(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
app_user_id = "app-user-impl"
""",
    )
    provider = LinearWorkspaceProvider(agent_registry=_agents(), config_path=config)
    provider.initialize()

    resolved = provider.resolve_event({"data": {"appUserId": "app-user-impl"}})

    assert resolved.presence.app_key == "implementation_partner"
    assert resolved.identity.id == "implementation_partner"


def test_unknown_linear_app_key_is_rejected(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
""",
    )
    provider = LinearWorkspaceProvider(agent_registry=_agents(), config_path=config)
    provider.initialize()

    with pytest.raises(LinearWorkspaceProviderConfigError, match="Unknown Linear app key"):
        provider.resolve_event({"_cao_linear_app_key": "unknown"})


def test_duplicate_linear_app_key_mapping_is_rejected(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.impl]
agent_id = "implementation_partner"
app_key = "same"

[presences.discovery]
agent_id = "discovery_partner"
app_key = "same"
""",
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="Duplicate Linear app_key"):
        load_linear_provider_config(config_path=config, agent_registry=_agents())


def test_duplicate_linear_app_user_id_mapping_is_rejected(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.impl]
agent_id = "implementation_partner"
app_key = "impl"
app_user_id = "same-user"

[presences.discovery]
agent_id = "discovery_partner"
app_key = "discovery"
app_user_id = "same-user"
""",
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="Duplicate Linear app_user_id"):
        load_linear_provider_config(config_path=config, agent_registry=_agents())


def test_duplicate_linear_app_user_name_mapping_is_rejected(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.impl]
agent_id = "implementation_partner"
app_key = "impl"
app_user_name = "Same User"

[presences.discovery]
agent_id = "discovery_partner"
app_key = "discovery"
app_user_name = "Same User"
""",
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="Duplicate Linear app_user_name"):
        load_linear_provider_config(config_path=config, agent_registry=_agents())


def test_duplicate_linear_oauth_state_mapping_is_rejected(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.impl]
agent_id = "implementation_partner"
app_key = "impl"
oauth_state = "same-state"

[presences.discovery]
agent_id = "discovery_partner"
app_key = "discovery"
oauth_state = "same-state"
""",
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="Duplicate Linear oauth_state"):
        load_linear_provider_config(config_path=config, agent_registry=_agents())


def test_duplicate_linear_webhook_secret_mapping_is_rejected(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.impl]
agent_id = "implementation_partner"
app_key = "impl"
webhook_secret = "same-secret"

[presences.discovery]
agent_id = "discovery_partner"
app_key = "discovery"
webhook_secret = "same-secret"
""",
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="Duplicate Linear webhook_secret"):
        load_linear_provider_config(config_path=config, agent_registry=_agents())


def test_missing_cao_agent_reference_is_rejected(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.impl]
agent_id = "missing_agent"
app_key = "impl"
""",
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="references missing CAO agent"):
        load_linear_provider_config(config_path=config, agent_registry=_agents())


def test_structured_config_is_primary_over_legacy_linear_app_env(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.impl]
agent_id = "implementation_partner"
app_key = "impl"
client_id = "structured-client"
""",
    )
    env = {
        "LINEAR_APP_KEYS": "legacy",
        "LINEAR_APP_IMPL_CLIENT_ID": "legacy-client",
    }

    assert configured_app_keys(config_path=config, env_reader=env.get) == ["impl"]
    assert linear_app_env("impl", "CLIENT_ID", config_path=config, env_reader=env.get) == (
        "structured-client"
    )


def test_structured_config_missing_field_does_not_fall_back_to_legacy_env(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.impl]
agent_id = "implementation_partner"
app_key = "impl"
client_id = "structured-client"
""",
    )
    env = {
        "LINEAR_APP_IMPL_CLIENT_SECRET": "legacy-secret",
        "LINEAR_CLIENT_SECRET": "legacy-global-secret",
    }

    assert linear_app_env("impl", "CLIENT_SECRET", config_path=config, env_reader=env.get) is None


def test_enabled_linear_provider_requires_config(tmp_path):
    missing_config = tmp_path / "workspace-providers" / "linear.toml"
    provider = LinearWorkspaceProvider(
        agent_registry=_agents(),
        config_path=missing_config,
        env_reader=lambda name: None,
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="no Linear config"):
        provider.initialize()


def test_legacy_discovery_partner_env_fallback_is_at_linear_config_edge(tmp_path):
    missing_config = tmp_path / "workspace-providers" / "linear.toml"
    env = {
        "LINEAR_WEBHOOK_SECRET": "legacy-secret",
        "LINEAR_DISCOVERY_SESSION_NAME": "linear-discovery-partner",
        "LINEAR_DISCOVERY_AGENT_PROFILE": "developer",
        "LINEAR_DISCOVERY_PROVIDER": "codex",
        "LINEAR_DISCOVERY_WORKDIR": "/repo",
    }

    config = load_linear_provider_config(config_path=missing_config, env_reader=env.get)

    assert config is not None
    assert config.source == "legacy_env"
    presence = config.presence_by_app_key("discovery_partner")
    assert presence is not None
    assert presence.webhook_secret == "legacy-secret"


def test_persist_linear_oauth_install_uses_legacy_global_env_at_provider_edge(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.update_linear_presence_tokens",
        lambda *args, **kwargs: False,
    )

    structured = persist_linear_oauth_install(
        app_key=None,
        access_token="access-token",
        refresh_token="refresh-token",
        app_user_id="app-user-1",
        app_user_name="Discovery Partner",
        token_expires_at="2026-05-06T00:00:00+00:00",
        env_writer=lambda key, value: saved.update({key: value}),
    )

    assert structured is False
    assert saved == {
        "LINEAR_ACCESS_TOKEN": "access-token",
        "LINEAR_REFRESH_TOKEN": "refresh-token",
        "LINEAR_APP_USER_ID": "app-user-1",
        "LINEAR_APP_USER_NAME": "Discovery Partner",
        "LINEAR_TOKEN_EXPIRES_AT": "2026-05-06T00:00:00+00:00",
    }


def test_persist_linear_oauth_install_uses_legacy_app_env_at_provider_edge(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "cli_agent_orchestrator.linear.workspace_provider.update_linear_presence_tokens",
        lambda *args, **kwargs: False,
    )

    structured = persist_linear_oauth_install(
        app_key="implementation_partner",
        access_token="implementation-access-token",
        app_user_id="impl-user-1",
        app_user_name="Implementation Partner",
        env_writer=lambda key, value: saved.update({key: value}),
    )

    assert structured is False
    assert saved == {
        "LINEAR_APP_IMPLEMENTATION_PARTNER_ACCESS_TOKEN": "implementation-access-token",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_APP_USER_ID": "impl-user-1",
        "LINEAR_APP_IMPLEMENTATION_PARTNER_APP_USER_NAME": "Implementation Partner",
    }

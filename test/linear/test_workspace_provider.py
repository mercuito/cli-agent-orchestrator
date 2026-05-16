"""Tests for Linear provider config loaded from durable agents."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cli_agent_orchestrator.agent import (
    Agent,
    AgentRegistry,
    LinearConfig,
    LinearToolAccessConfig,
    load_agent,
    write_agent,
)
from cli_agent_orchestrator.linear.workspace_events import (
    LinearAgentMentionedEvent,
    LinearAgentSessionLifecycleActivityEvent,
    LinearAgentSessionPromptedEvent,
    LinearAgentSessionStopRequestedEvent,
    LinearIssueCreatedEvent,
    LinearIssueDelegatedToAgentEvent,
)
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearWorkspaceProvider,
    LinearWorkspaceProviderConfigError,
    configured_app_keys,
    linear_app_env,
    load_linear_provider_config,
    persist_linear_oauth_install,
)


def _future_token_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def _agent(agent_id: str = "implementation_partner", **overrides: object) -> Agent:
    values = {
        "id": agent_id,
        "display_name": agent_id.replace("_", " ").title(),
        "cli_provider": "codex",
        "workdir": "/repo",
        "session_name": agent_id.replace("_", "-"),
        "prompt": "# Agent\n",
        "linear": LinearConfig(app_key=agent_id),
    }
    values.update(overrides)
    return Agent(**values)


def _registry(*agents: Agent) -> AgentRegistry:
    return AgentRegistry({agent.id: agent for agent in agents})


def _write_agents(tmp_path, *agents: Agent):
    agents_root = tmp_path / "agents"
    for agent in agents:
        write_agent(agent, agents_root=agents_root)
    return agents_root


def test_configured_linear_app_key_resolves_to_cao_agent():
    agent = _agent(
        "implementation_partner",
        linear=LinearConfig(
            app_key="implementation_partner",
            app_user_id="app-user-impl",
            app_user_name="Implementation Partner",
        ),
    )
    provider = LinearWorkspaceProvider(
        agent_registry=_registry(agent),
        preflight_credentials=False,
    )
    provider.initialize()

    resolved = provider.resolve_event({"_cao_linear_app_key": "implementation_partner"})

    assert resolved.presence.agent_id == "implementation_partner"
    assert resolved.identity.session_name == "implementation-partner"


def test_linear_workspace_provider_declares_subscribable_cao_events():
    provider = LinearWorkspaceProvider(
        agent_registry=_registry(_agent()),
        preflight_credentials=False,
    )

    event_types = set(provider.published_cao_events())

    assert event_types == {
        LinearAgentMentionedEvent,
        LinearIssueDelegatedToAgentEvent,
        LinearAgentSessionPromptedEvent,
        LinearAgentSessionLifecycleActivityEvent,
        LinearAgentSessionStopRequestedEvent,
        LinearIssueCreatedEvent,
    }


def test_linear_agent_policies_default_disabled():
    loaded = load_linear_provider_config(agent_registry=_registry(_agent()))

    assert loaded is not None
    assert loaded.agent_policies_enabled is False


def test_configured_linear_app_user_id_resolves_to_cao_agent():
    agent = _agent(
        linear=LinearConfig(app_key="implementation_partner", app_user_id="app-user-impl")
    )
    provider = LinearWorkspaceProvider(
        agent_registry=_registry(agent),
        preflight_credentials=False,
    )
    provider.initialize()

    resolved = provider.resolve_event({"data": {"appUserId": "app-user-impl"}})

    assert resolved.presence.app_key == "implementation_partner"
    assert resolved.identity.id == "implementation_partner"


def test_configured_linear_app_key_tolerates_unstored_app_user_id():
    provider = LinearWorkspaceProvider(
        agent_registry=_registry(_agent()),
        preflight_credentials=False,
    )
    provider.initialize()

    resolved = provider.resolve_event(
        {
            "_cao_linear_app_key": "implementation_partner",
            "appUserId": "fresh-linear-app-user-id",
        }
    )

    assert resolved.presence.app_key == "implementation_partner"
    assert resolved.identity.id == "implementation_partner"


def test_configured_linear_app_key_rejects_conflicting_app_user_id():
    provider = LinearWorkspaceProvider(
        agent_registry=_registry(
            _agent(
                "implementation_partner",
                linear=LinearConfig(app_key="implementation_partner", app_user_id="app-user-impl"),
            ),
            _agent(
                "discovery_partner",
                linear=LinearConfig(app_key="discovery_partner", app_user_id="app-user-discovery"),
            ),
        ),
        preflight_credentials=False,
    )
    provider.initialize()

    with pytest.raises(
        LinearWorkspaceProviderConfigError,
        match="app key and app user id resolve to different CAO identities",
    ):
        provider.resolve_event(
            {
                "_cao_linear_app_key": "implementation_partner",
                "appUserId": "app-user-discovery",
            }
        )


def test_unknown_linear_app_key_is_rejected():
    provider = LinearWorkspaceProvider(
        agent_registry=_registry(_agent()),
        preflight_credentials=False,
    )
    provider.initialize()

    with pytest.raises(LinearWorkspaceProviderConfigError, match="Unknown Linear app key"):
        provider.resolve_event({"_cao_linear_app_key": "unknown"})


def test_duplicate_linear_app_key_mapping_is_rejected():
    with pytest.raises(LinearWorkspaceProviderConfigError, match="Duplicate Linear app_key"):
        load_linear_provider_config(
            agent_registry=_registry(
                _agent("implementation_partner", linear=LinearConfig(app_key="same")),
                _agent("discovery_partner", linear=LinearConfig(app_key="same")),
            )
        )


def test_duplicate_linear_app_user_id_mapping_is_rejected():
    with pytest.raises(LinearWorkspaceProviderConfigError, match="Duplicate Linear app_user_id"):
        load_linear_provider_config(
            agent_registry=_registry(
                _agent(
                    "implementation_partner",
                    linear=LinearConfig(app_key="impl", app_user_id="same-user"),
                ),
                _agent(
                    "discovery_partner",
                    linear=LinearConfig(app_key="discovery", app_user_id="same-user"),
                ),
            )
        )


def test_duplicate_linear_app_user_name_mapping_is_rejected():
    with pytest.raises(LinearWorkspaceProviderConfigError, match="Duplicate Linear app_user_name"):
        load_linear_provider_config(
            agent_registry=_registry(
                _agent(
                    "implementation_partner",
                    linear=LinearConfig(app_key="impl", app_user_name="Same User"),
                ),
                _agent(
                    "discovery_partner",
                    linear=LinearConfig(app_key="discovery", app_user_name="Same User"),
                ),
            )
        )


def test_duplicate_linear_oauth_state_mapping_is_rejected():
    with pytest.raises(LinearWorkspaceProviderConfigError, match="Duplicate Linear oauth_state"):
        load_linear_provider_config(
            agent_registry=_registry(
                _agent(
                    "implementation_partner",
                    linear=LinearConfig(app_key="impl", oauth_state="same-state"),
                ),
                _agent(
                    "discovery_partner",
                    linear=LinearConfig(app_key="discovery", oauth_state="same-state"),
                ),
            )
        )


def test_agent_linear_config_is_primary_over_legacy_linear_app_env(tmp_path):
    agents_root = _write_agents(
        tmp_path,
        _agent(
            "implementation_partner", linear=LinearConfig(app_key="impl", client_id="agent-client")
        ),
    )
    env = {
        "LINEAR_APP_KEYS": "legacy",
        "LINEAR_APP_IMPL_CLIENT_ID": "legacy-client",
    }

    assert configured_app_keys(agents_root=agents_root, env_reader=env.get) == ["impl"]
    assert (
        linear_app_env("impl", "CLIENT_ID", agents_root=agents_root, env_reader=env.get)
        == "agent-client"
    )


def test_agent_linear_config_missing_field_does_not_fall_back_to_legacy_env(tmp_path):
    agents_root = _write_agents(
        tmp_path,
        _agent(
            "implementation_partner", linear=LinearConfig(app_key="impl", client_id="agent-client")
        ),
    )
    env = {
        "LINEAR_APP_IMPL_CLIENT_SECRET": "legacy-secret",
        "LINEAR_CLIENT_SECRET": "legacy-global-secret",
    }

    assert (
        linear_app_env("impl", "CLIENT_SECRET", agents_root=agents_root, env_reader=env.get) is None
    )


def test_enabled_linear_provider_requires_config(tmp_path):
    provider = LinearWorkspaceProvider(
        agents_root=tmp_path / "agents", env_reader=lambda name: None
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="no Linear config"):
        provider.initialize()


def test_linear_provider_preflight_rejects_missing_access_token():
    provider = LinearWorkspaceProvider(agent_registry=_registry(_agent()))

    with pytest.raises(LinearWorkspaceProviderConfigError, match="missing access_token"):
        provider.initialize()


def test_linear_provider_preflight_rejects_expired_access_token():
    provider = LinearWorkspaceProvider(
        agent_registry=_registry(
            _agent(
                linear=LinearConfig(
                    app_key="implementation_partner",
                    access_token="access-token",
                    token_expires_at="2026-05-01T00:00:00+00:00",
                )
            )
        )
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="access token expired"):
        provider.initialize()


def test_linear_provider_preflight_rejects_authenticated_app_user_mismatch():
    provider = LinearWorkspaceProvider(
        agent_registry=_registry(
            _agent(
                linear=LinearConfig(
                    app_key="implementation_partner",
                    app_user_id="expected-app-user",
                    access_token="access-token",
                    token_expires_at=_future_token_expires_at(),
                )
            )
        ),
        credential_checker=lambda presence: {"id": "other-app-user", "name": "Wrong App"},
    )

    with pytest.raises(LinearWorkspaceProviderConfigError, match="app_user_id does not match"):
        provider.initialize()


def test_linear_provider_preflight_accepts_authenticated_credentials():
    checked = []
    provider = LinearWorkspaceProvider(
        agent_registry=_registry(
            _agent(
                linear=LinearConfig(
                    app_key="implementation_partner",
                    app_user_id="app-user-impl",
                    access_token="access-token",
                    token_expires_at=_future_token_expires_at(),
                )
            )
        ),
        credential_checker=lambda presence: checked.append(presence.app_key)
        or {"id": "app-user-impl", "name": "Implementation Partner"},
    )
    provider.initialize()

    assert checked == ["implementation_partner"]


def test_agent_tool_access_is_loaded_per_agent_without_profile_targeting():
    agent = _agent(
        linear=LinearConfig(
            app_key="implementation_partner",
            tool_access=(
                LinearToolAccessConfig(
                    access_id="reads",
                    tools=("cao_linear.get_issue", "cao_linear.list_comments"),
                    issues=("CAO-28", "issue-28"),
                    reason="Implementation Partner is limited to the bridge planning issue.",
                ),
            ),
        )
    )

    loaded = load_linear_provider_config(agent_registry=_registry(agent))

    assert loaded is not None
    access = loaded.tool_access["agents.implementation_partner.linear.tool_access.reads"]
    assert access.agent_id == "implementation_partner"
    assert access.agent_profile is None
    assert access.tools == ("cao_linear.get_issue", "cao_linear.list_comments")
    assert access.issues == ("CAO-28", "issue-28")


def test_agent_tool_access_ids_are_agent_local():
    loaded = load_linear_provider_config(
        agent_registry=_registry(
            _agent(
                "implementation_partner",
                linear=LinearConfig(
                    app_key="implementation_partner",
                    tool_access=(
                        LinearToolAccessConfig(
                            access_id="reads",
                            tools=("cao_linear.get_issue",),
                            issues=("CAO-28",),
                        ),
                    ),
                ),
            ),
            _agent(
                "discovery_partner",
                linear=LinearConfig(
                    app_key="discovery_partner",
                    tool_access=(
                        LinearToolAccessConfig(
                            access_id="reads",
                            tools=("cao_linear.list_comments",),
                            issues=("CAO-29",),
                        ),
                    ),
                ),
            ),
        )
    )

    assert loaded is not None
    assert set(loaded.tool_access) == {
        "agents.implementation_partner.linear.tool_access.reads",
        "agents.discovery_partner.linear.tool_access.reads",
    }
    assert (
        loaded.tool_access["agents.implementation_partner.linear.tool_access.reads"].agent_id
        == "implementation_partner"
    )
    assert (
        loaded.tool_access["agents.discovery_partner.linear.tool_access.reads"].agent_id
        == "discovery_partner"
    )


def test_oauth_install_patches_matching_agent_linear_section(tmp_path):
    agents_root = _write_agents(
        tmp_path,
        _agent(
            linear=LinearConfig(
                app_key="implementation_partner",
                access_token="old-token",
                tool_access=(
                    LinearToolAccessConfig(
                        access_id="reads",
                        tools=("cao_linear.get_issue",),
                        issues=("CAO-28",),
                    ),
                ),
            )
        ),
    )

    updated = persist_linear_oauth_install(
        app_key="implementation_partner",
        access_token="new-token",
        refresh_token="refresh-token",
        app_user_id="app-user-1",
        app_user_name="Implementation Partner",
        token_expires_at="2026-05-06T00:00:00+00:00",
        agents_root=agents_root,
    )

    reloaded = load_agent("implementation_partner", agents_root=agents_root)
    assert updated is True
    assert reloaded.linear is not None
    assert reloaded.linear.access_token == "new-token"
    assert reloaded.linear.refresh_token == "refresh-token"
    assert reloaded.linear.app_user_id == "app-user-1"
    assert reloaded.linear.app_user_name == "Implementation Partner"
    assert reloaded.linear.token_expires_at == "2026-05-06T00:00:00+00:00"
    assert reloaded.linear.tool_access[0].tools == ("cao_linear.get_issue",)

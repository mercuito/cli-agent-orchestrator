"""Tests for workspace-tool-provider startup and registry behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from cli_agent_orchestrator.agent import Agent, AgentWorkspaceConfig, write_agent
from cli_agent_orchestrator.workspace_tool_providers import (
    UnknownWorkspaceToolProviderError,
    WorkspaceToolProviderConfigError,
    WorkspaceToolProviderEvent,
    WorkspaceToolProviderEventDispatcher,
    WorkspaceToolProviderRegistry,
    default_workspace_tool_provider_registry,
    initialize_enabled_workspace_tool_providers,
    load_enabled_provider_tool_access_policies,
    load_enabled_workspace_tool_providers,
    workspace_tool_provider_config_exists,
)
from cli_agent_orchestrator.workspace_tool_providers.tool_access import (
    ProviderMediatedToolDefinition,
    ProviderToolAccess,
    ProviderToolAccessPolicy,
)


def _agents_root(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    return agents


def _write_agent(agents_root, agent_id: str, *, workspace: str | None = None) -> None:
    write_agent(
        Agent(
            id=agent_id,
            display_name=agent_id.replace("_", " ").title(),
            cli_provider="codex",
            workdir="/repo",
            session_name=agent_id.replace("_", "-"),
            prompt="",
            workspace=AgentWorkspaceConfig(team=workspace),
        ),
        agents_root=agents_root,
    )


def test_unknown_enabled_workspace_tool_provider_fails_clearly(tmp_path):
    enabled = tmp_path / "workspace-tool-providers.toml"
    enabled.write_text('enabled = ["jira"]\n')
    agents = _agents_root(tmp_path)

    with pytest.raises(UnknownWorkspaceToolProviderError, match="jira"):
        initialize_enabled_workspace_tool_providers(
            enabled_config_path=enabled,
            agents_config_path=agents,
        )


def test_default_config_migrates_old_workspace_provider_file(tmp_path, monkeypatch):
    old_config = tmp_path / "workspace-providers.toml"
    new_config = tmp_path / "workspace-tool-providers.toml"
    old_config.write_text('enabled = ["example"]\n')
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_tool_providers.registry._OLD_WORKSPACE_PROVIDERS_CONFIG_PATH",
        old_config,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_tool_providers.registry.WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH",
        new_config,
    )

    enabled = load_enabled_workspace_tool_providers()

    assert enabled == ["example"]
    assert not old_config.exists()
    assert new_config.read_text() == 'enabled = ["example"]\n'


def test_default_config_fails_when_old_and_new_files_both_exist(tmp_path, monkeypatch):
    old_config = tmp_path / "workspace-providers.toml"
    new_config = tmp_path / "workspace-tool-providers.toml"
    old_config.write_text('enabled = ["example"]\n')
    new_config.write_text('enabled = ["example"]\n')
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_tool_providers.registry._OLD_WORKSPACE_PROVIDERS_CONFIG_PATH",
        old_config,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_tool_providers.registry.WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH",
        new_config,
    )

    with pytest.raises(WorkspaceToolProviderConfigError, match="Both default"):
        load_enabled_workspace_tool_providers()


def test_explicit_old_config_path_is_not_migrated(tmp_path, monkeypatch):
    old_config = tmp_path / "workspace-providers.toml"
    default_new_config = tmp_path / "workspace-tool-providers.toml"
    old_config.write_text('enabled = ["example"]\n')
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_tool_providers.registry.WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH",
        default_new_config,
    )

    enabled = load_enabled_workspace_tool_providers(old_config)

    assert enabled == ["example"]
    assert old_config.exists()
    assert not default_new_config.exists()


def test_default_config_exists_migrates_old_workspace_provider_file(tmp_path, monkeypatch):
    old_config = tmp_path / "workspace-providers.toml"
    new_config = tmp_path / "workspace-tool-providers.toml"
    old_config.write_text('enabled = ["example"]\n')
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_tool_providers.registry._OLD_WORKSPACE_PROVIDERS_CONFIG_PATH",
        old_config,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_tool_providers.registry.WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH",
        new_config,
    )

    assert workspace_tool_provider_config_exists()
    assert not old_config.exists()
    assert new_config.exists()


def test_initialize_enabled_workspace_tool_providers_registers_declared_provider_events(
    tmp_path, monkeypatch
):
    enabled = tmp_path / "workspace-tool-providers.toml"
    enabled.write_text('enabled = ["example"]\n')
    agents = _agents_root(tmp_path)
    dispatcher = WorkspaceToolProviderEventDispatcher()

    @dataclass(frozen=True)
    class ExampleEvent(WorkspaceToolProviderEvent):
        provider_name: ClassVar[str] = "example"
        event_name: ClassVar[str] = "created"

    class ExampleProvider:
        name = "example"

        def initialize(self):
            return None

        def published_events(self):
            return (ExampleEvent,)

    registry = WorkspaceToolProviderRegistry({"example": lambda _agent_registry: ExampleProvider()})
    monkeypatch.setattr(
        "cli_agent_orchestrator.workspace_tool_providers.registry.default_workspace_tool_provider_event_dispatcher",
        lambda: dispatcher,
    )

    initialize_enabled_workspace_tool_providers(
        enabled_config_path=enabled,
        agents_config_path=agents,
        registry=registry,
    )

    assert dispatcher.published_events("example") == (ExampleEvent,)


def test_initialize_workspace_tool_providers_starts_none_when_unconfigured(tmp_path):
    enabled = tmp_path / "missing-workspace-tool-providers.toml"
    agents = _agents_root(tmp_path)

    providers = initialize_enabled_workspace_tool_providers(
        enabled_config_path=enabled,
        agents_config_path=agents,
    )

    assert providers == []


def test_provider_tool_policy_loading_uses_explicit_provider_registry(tmp_path):
    enabled = tmp_path / "workspace-tool-providers.toml"
    enabled.write_text('enabled = ["example"]\n')
    agents = _agents_root(tmp_path)
    _write_agent(agents, "developer")

    class ExampleProvider:
        name = "example"

        def initialize(self):
            return None

        def provider_tool_access(self):
            return ProviderToolAccessPolicy(
                provider_name="example",
                tools={
                    "example.read": ProviderMediatedToolDefinition(
                        name="example.read",
                        description="Read example data.",
                        input_schema={},
                        handler=lambda _context, _arguments: {"ok": True},
                    )
                },
                hooks={},
                access=(
                    ProviderToolAccess(
                        provider_name="example",
                        tool_name="example.read",
                        agent_id="developer",
                        pre_hooks=(),
                        post_hooks=(),
                        source_location="example.access.developer",
                    ),
                ),
            )

    registry = WorkspaceToolProviderRegistry({"example": lambda _agent_registry: ExampleProvider()})

    policies = load_enabled_provider_tool_access_policies(
        enabled_config_path=enabled,
        agents_config_path=agents,
        registry=registry,
    )

    assert tuple(policies) == ("example",)
    assert policies["example"].access[0].agent_id == "developer"


def test_candidate_provider_registry_is_empty_until_providers_register_explicitly():
    with pytest.raises(UnknownWorkspaceToolProviderError, match="example"):
        default_workspace_tool_provider_registry().create("example", agent_registry=None)  # type: ignore[arg-type]

"""Tests for CAO-owned agent identity config."""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.agent_identity import (
    AgentIdentityConfigError,
    AgentIdentityPathError,
    agent_identity_data_dir,
    ensure_agent_workspace_context_runtime_paths,
    load_agent_identity_registry,
    workspace_context_data_dir,
    workspace_context_provider_data_dir,
)


def test_load_agent_identity_registry_maps_runtime_config(tmp_path):
    agents = tmp_path / "agents.toml"
    agents.write_text("""
[agents.implementation_partner]
display_name = "Implementation Partner"
agent_profile = "developer"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"

[agents.implementation_partner.workspace_context]
enabled = true
resolver_id = "linear_planning"
""")

    registry = load_agent_identity_registry(agents)

    identity = registry.get("implementation_partner")
    assert identity.display_name == "Implementation Partner"
    assert identity.agent_profile == "developer"
    assert identity.cli_provider == "codex"
    assert identity.workdir == "/repo"
    assert identity.session_name == "implementation-partner"
    assert identity.workspace_context.enabled is True
    assert identity.workspace_context.resolver_id == "linear_planning"


def test_load_agent_identity_registry_rejects_missing_runtime_field(tmp_path):
    agents = tmp_path / "agents.toml"
    agents.write_text("""
[agents.implementation_partner]
display_name = "Implementation Partner"
agent_profile = "developer"
cli_provider = "codex"
workdir = "/repo"
""")

    with pytest.raises(AgentIdentityConfigError, match="session_name"):
        load_agent_identity_registry(agents)


def test_load_agent_identity_registry_rejects_path_unsafe_agent_id(tmp_path):
    agents = tmp_path / "agents.toml"
    agents.write_text("""
[agents."../escape"]
display_name = "Implementation Partner"
agent_profile = "developer"
cli_provider = "codex"
workdir = "/repo"
session_name = "implementation-partner"
""")

    with pytest.raises(AgentIdentityConfigError, match="single path segment"):
        load_agent_identity_registry(agents)


def test_workspace_context_runtime_paths_are_deterministic_and_provider_scoped(
    implementation_partner_identity_factory,
    tmp_path,
):
    identity = implementation_partner_identity_factory()
    paths = ensure_agent_workspace_context_runtime_paths(
        identity,
        "wctx_123",
        "codex",
        cao_home_dir=tmp_path,
    )

    context_root = tmp_path / "agents" / "implementation_partner" / "contexts" / "wctx_123"
    assert paths.identity_data_dir == tmp_path / "agents" / "implementation_partner"
    assert paths.context_data_dir == context_root
    assert paths.provider_data_dir == context_root / "runtime" / "codex"
    assert paths.provider_data_dir.is_dir()
    assert workspace_context_data_dir(identity, "wctx_123", cao_home_dir=tmp_path) == context_root
    assert (
        workspace_context_provider_data_dir(
            identity,
            "wctx_123",
            "codex",
            cao_home_dir=tmp_path,
        )
        == paths.provider_data_dir
    )


def test_identity_runtime_paths_reject_nested_agent_or_provider_segments(
    implementation_partner_identity_factory,
    tmp_path,
):
    identity = implementation_partner_identity_factory(id="../escape")

    with pytest.raises(AgentIdentityPathError, match="single path segment"):
        agent_identity_data_dir(identity, cao_home_dir=tmp_path)

    identity = implementation_partner_identity_factory()
    with pytest.raises(AgentIdentityPathError, match="single path segment"):
        workspace_context_data_dir(identity, "../wctx", cao_home_dir=tmp_path)
    with pytest.raises(AgentIdentityPathError, match="single path segment"):
        workspace_context_provider_data_dir(identity, "wctx_123", "../codex", cao_home_dir=tmp_path)

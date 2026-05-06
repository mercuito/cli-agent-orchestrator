"""Tests for CAO-owned agent identity config."""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.agent_identity import (
    AgentIdentityConfigError,
    load_agent_identity_registry,
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
""")

    registry = load_agent_identity_registry(agents)

    identity = registry.get("implementation_partner")
    assert identity.display_name == "Implementation Partner"
    assert identity.agent_profile == "developer"
    assert identity.cli_provider == "codex"
    assert identity.workdir == "/repo"
    assert identity.session_name == "implementation-partner"


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

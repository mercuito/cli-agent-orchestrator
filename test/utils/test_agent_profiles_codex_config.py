from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_load_agent_profile_parses_codex_config(tmp_path: Path):
    from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile

    local_store = tmp_path / "agent-store"
    local_store.mkdir(parents=True)

    (local_store / "developer.md").write_text(
        """---
name: developer
description: Test profile
codexConfig:
  model_reasoning_effort: high
---

You are a test agent.
"""
    )

    with patch("cli_agent_orchestrator.utils.agent_profiles.LOCAL_AGENT_STORE_DIR", local_store):
        profile = load_agent_profile("developer")

    assert profile.codexConfig == {"model_reasoning_effort": "high"}

from __future__ import annotations

from pathlib import Path


def test_load_agent_parses_codex_config(tmp_path: Path):
    from cli_agent_orchestrator.agent import load_agent

    agent_dir = tmp_path / "developer"
    agent_dir.mkdir(parents=True)

    (agent_dir / "agent.toml").write_text(
        """
display_name = "Test profile"
id = "developer"
cli_provider = "codex"
workdir = "/repo"
session_name = "developer"

[codex_config]
model_reasoning_effort = "high"
"""
    )
    (agent_dir / "prompt.md").write_text("You are a test agent.\n")

    profile = load_agent("developer", agents_root=tmp_path)

    assert profile.codex_config == {"model_reasoning_effort": "high"}

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _profile(**overrides):
    data = {
        "name": "claude_developer",
        "description": "desc",
        "system_prompt": "Use your role skills.",
        "skills": None,
        "mcpServers": None,
        "model": None,
        "reasoning_effort": None,
    }
    data.update(overrides)
    return type("Profile", (), data)()


def _write_skill(skill_store: Path, name: str, body: str = "# Skill\n") -> None:
    skill_dir = skill_store / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n" f"name: {name}\n" "description: Test skill\n" "---\n\n" f"{body}"
    )


def test_prepare_agent_claude_runtime_materializes_profile_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from cli_agent_orchestrator.utils.claude_runtime import prepare_agent_claude_runtime

    skill_store = tmp_path / "skills"
    _write_skill(skill_store, "discovery-intake")
    monkeypatch.setattr("cli_agent_orchestrator.utils.skills.SKILLS_DIR", skill_store)

    with (
        patch(
            "cli_agent_orchestrator.utils.claude_runtime.shutil.which", return_value="/bin/claude"
        ),
        patch("cli_agent_orchestrator.utils.claude_runtime.claude_login_ok", return_value=True),
        patch(
            "cli_agent_orchestrator.utils.claude_runtime.load_agent",
            return_value=_profile(skills=("discovery-intake",)),
        ),
    ):
        provider_data_dir = prepare_agent_claude_runtime(
            tmp_path / "agent" / "claude_code",
            "terminal-1",
            "claude_developer",
            str(tmp_path / "work"),
        )

    settings = provider_data_dir / "settings.json"
    plugin = provider_data_dir / "plugins" / "cao-profile-skills"
    assert settings.read_text().find("skipDangerousModePermissionPrompt") >= 0
    assert (plugin / ".claude-plugin" / "plugin.json").exists()
    assert (plugin / "skills" / "discovery-intake" / "SKILL.md").exists()
    assert (provider_data_dir / "session-id").read_text().strip()
    assert (provider_data_dir / ".cao-terminal-id").read_text() == "terminal-1\n"


def test_claude_runtime_materialization_fingerprints_profile_scoped_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from cli_agent_orchestrator.utils.claude_runtime import build_claude_runtime_materialization

    skill_store = tmp_path / "skills"
    _write_skill(skill_store, "discovery-intake", "first version\n")
    monkeypatch.setattr("cli_agent_orchestrator.utils.skills.SKILLS_DIR", skill_store)

    with patch(
        "cli_agent_orchestrator.utils.claude_runtime.load_agent",
        return_value=_profile(skills=("discovery-intake",)),
    ):
        first = build_claude_runtime_materialization("claude_developer")
        (skill_store / "discovery-intake" / "SKILL.md").write_text(
            "---\nname: discovery-intake\ndescription: Test skill\n---\n\nsecond version\n"
        )
        second = build_claude_runtime_materialization("claude_developer")

    assert first.skill_fingerprints["discovery-intake"]["SKILL.md"] != (
        second.skill_fingerprints["discovery-intake"]["SKILL.md"]
    )


def test_prepare_agent_claude_runtime_requires_claude_login(tmp_path: Path):
    from cli_agent_orchestrator.utils.claude_runtime import prepare_agent_claude_runtime

    with (
        patch(
            "cli_agent_orchestrator.utils.claude_runtime.shutil.which", return_value="/bin/claude"
        ),
        patch("cli_agent_orchestrator.utils.claude_runtime.claude_login_ok", return_value=False),
    ):
        with pytest.raises(ValueError, match="Claude Code is not logged in"):
            prepare_agent_claude_runtime(
                tmp_path / "agent" / "claude_code",
                "terminal-1",
                "claude_developer",
                str(tmp_path / "work"),
            )


def test_ensure_claude_session_id_reuses_existing_uuid(tmp_path: Path):
    from cli_agent_orchestrator.utils.claude_runtime import ensure_claude_session_id

    first = ensure_claude_session_id(tmp_path)
    second = ensure_claude_session_id(tmp_path)

    assert first == second

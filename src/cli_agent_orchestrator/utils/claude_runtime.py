"""Claude Code runtime materialization for CAO-managed identities."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile
from cli_agent_orchestrator.utils.skills import (
    materialize_skill,
    skill_file_fingerprints,
    validate_skill_name,
)

CLAUDE_RUNTIME_MATERIALIZATION_SCHEMA_VERSION = "claude-runtime-materialization.v1"
CLAUDE_RUNTIME_STATE_SCHEMA_VERSION = "claude-runtime-state.v1"
CLAUDE_PLUGIN_NAME = "cao-profile-skills"
CLAUDE_PLUGIN_VERSION = "1.0.0"
CLAUDE_SESSION_ID_FILE = "session-id"
CLAUDE_SETTINGS_FILE = "settings.json"


@dataclass(frozen=True)
class ClaudeRuntimeMaterialization:
    """Claude-owned files that CAO materializes for one identity runtime."""

    settings: Dict[str, Any]
    plugin_manifest: Dict[str, Any]
    skill_fingerprints: Dict[str, Dict[str, str]]


def _profile_skill_names(profile: Any) -> tuple[str, ...]:
    raw_names = getattr(profile, "skills", None)
    if raw_names is None:
        return ()
    if not isinstance(raw_names, list) or not all(isinstance(item, str) for item in raw_names):
        raise ValueError("Agent profile skills must be a list of skill names")
    return tuple(validate_skill_name(item) for item in raw_names)


def _skill_fingerprints(skill_names: Iterable[str]) -> Dict[str, Dict[str, str]]:
    return {skill_name: skill_file_fingerprints(skill_name) for skill_name in skill_names}


def _plugin_manifest() -> Dict[str, Any]:
    return {
        "name": CLAUDE_PLUGIN_NAME,
        "version": CLAUDE_PLUGIN_VERSION,
        "description": "CAO materialized profile-scoped skills for this agent identity.",
        "author": {"name": "CLI Agent Orchestrator"},
    }


def build_claude_runtime_materialization(agent_profile: str) -> ClaudeRuntimeMaterialization:
    """Build Claude-owned identity runtime material without writing it."""
    profile = load_agent_profile(agent_profile)
    skill_names = _profile_skill_names(profile)
    return ClaudeRuntimeMaterialization(
        settings={
            # CAO launches Claude with --dangerously-skip-permissions intentionally.
            # Keep this in a CAO-owned settings file for identity launches instead
            # of mutating the user's global ~/.claude/settings.json.
            "skipDangerousModePermissionPrompt": True,
        },
        plugin_manifest=_plugin_manifest(),
        skill_fingerprints=_skill_fingerprints(skill_names),
    )


def _materialize_profile_skills(plugin_dir: Path, skill_names: Iterable[str]) -> None:
    skills_root = plugin_dir / "skills"
    shutil.rmtree(skills_root, ignore_errors=True)
    for skill_name in skill_names:
        materialize_skill(skill_name, skills_root / skill_name)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _read_session_id(provider_data_dir: Path) -> str | None:
    path = provider_data_dir / CLAUDE_SESSION_ID_FILE
    if not path.exists():
        return None
    value = path.read_text().strip()
    try:
        uuid.UUID(value)
    except ValueError:
        return None
    return value


def ensure_claude_session_id(provider_data_dir: Path) -> str:
    """Return this identity's Claude session id, creating it if needed."""
    existing = _read_session_id(provider_data_dir)
    if existing is not None:
        return existing
    value = str(uuid.uuid4())
    provider_data_dir.mkdir(parents=True, exist_ok=True)
    (provider_data_dir / CLAUDE_SESSION_ID_FILE).write_text(f"{value}\n")
    return value


def claude_login_ok() -> bool:
    """Best-effort check that Claude Code can use the current user's auth state."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return False
    try:
        proc = subprocess.run(
            [claude_bin, "auth", "status"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return False
    if proc.returncode != 0:
        return False
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return data.get("loggedIn") is True


def prepare_identity_claude_runtime(
    provider_data_dir: Path,
    terminal_id: str,
    agent_profile: str,
    working_directory: str,
) -> Path:
    """Prepare Claude-owned runtime material below the provider-owned data dir.

    Claude Code's first-party OAuth state is currently tied to the normal user
    home/keychain path. Copying ``~/.claude.json`` into an isolated HOME is not
    sufficient for login. CAO therefore keeps Claude auth on the real user path
    and preflights it, while putting CAO-generated settings/plugins/session ids
    under the identity provider directory.
    """
    if not shutil.which("claude"):
        raise ValueError("claude binary not found in PATH")
    if not claude_login_ok():
        raise ValueError(
            "Claude Code is not logged in (or requires user interaction). "
            "Run `claude auth login` first."
        )

    provider_data_dir.mkdir(parents=True, exist_ok=True)
    materialization = build_claude_runtime_materialization(agent_profile)

    _write_json(provider_data_dir / CLAUDE_SETTINGS_FILE, materialization.settings)

    plugin_dir = provider_data_dir / "plugins" / CLAUDE_PLUGIN_NAME
    _write_json(plugin_dir / ".claude-plugin" / "plugin.json", materialization.plugin_manifest)
    _materialize_profile_skills(plugin_dir, materialization.skill_fingerprints.keys())

    ensure_claude_session_id(provider_data_dir)
    (provider_data_dir / ".cao-terminal-id").write_text(f"{terminal_id}\n")
    (provider_data_dir / ".cao-working-directory").write_text(
        f"{os.path.realpath(working_directory or os.getcwd())}\n"
    )
    return provider_data_dir


def claude_runtime_paths(provider_data_dir: Path) -> dict[str, Path]:
    """Return the provider-owned Claude runtime paths used by the provider."""
    return {
        "settings": provider_data_dir / CLAUDE_SETTINGS_FILE,
        "plugin_dir": provider_data_dir / "plugins" / CLAUDE_PLUGIN_NAME,
        "session_id": provider_data_dir / CLAUDE_SESSION_ID_FILE,
    }

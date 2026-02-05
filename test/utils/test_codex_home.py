from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import tomli


def _read_toml(path: Path) -> dict:
    return tomli.loads(path.read_text())


class TestPrepareCodexHome:
    def test_prepare_codex_home_requires_codex_binary(self, tmp_path: Path):
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text('model = "gpt-5.2"\n')
        (global_codex_home / "auth.json").write_text('{"ok":true}\n')

        with (
            patch("cli_agent_orchestrator.utils.codex_home.shutil.which", return_value=None),
            patch(
                "cli_agent_orchestrator.utils.codex_home.load_agent_profile",
                return_value=type(
                    "Profile",
                    (),
                    {
                        "name": "codex_developer",
                        "description": "x",
                        "system_prompt": "Hello",
                        "mcpServers": None,
                        "model": None,
                        "codexConfig": None,
                    },
                )(),
            ),
        ):
            with pytest.raises(ValueError, match="codex"):
                prepare_codex_home(
                    terminal_id="abcd1234",
                    agent_profile="codex_developer",
                    working_directory=str(tmp_path / "work"),
                    cao_home_dir=tmp_path / "cao",
                    global_codex_home_dir=global_codex_home,
                )

    def test_prepare_codex_home_requires_auth_json(self, tmp_path: Path):
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text('model = "gpt-5.2"\n')
        # Intentionally omit auth.json

        with (
            patch(
                "cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"
            ),
            patch(
                "cli_agent_orchestrator.utils.codex_home.load_agent_profile",
                return_value=type(
                    "Profile",
                    (),
                    {
                        "name": "codex_developer",
                        "description": "x",
                        "system_prompt": "Hello",
                        "mcpServers": None,
                        "model": None,
                        "codexConfig": None,
                    },
                )(),
            ),
        ):
            with pytest.raises(ValueError, match="auth\\.json"):
                prepare_codex_home(
                    terminal_id="abcd1234",
                    agent_profile="codex_developer",
                    working_directory=str(tmp_path / "work"),
                    cao_home_dir=tmp_path / "cao",
                    global_codex_home_dir=global_codex_home,
                )

    def test_prepare_codex_home_writes_agents_md_from_profile(self, tmp_path: Path):
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text('model = "gpt-5.2"\n')
        (global_codex_home / "auth.json").write_text('{"ok":true}\n')

        profile = type(
            "Profile",
            (),
            {
                "name": "codex_developer",
                "description": "desc",
                "system_prompt": "You are codex dev.\nFollow rules.",
                "mcpServers": None,
                "model": None,
                "codexConfig": None,
            },
        )()

        with (
            patch(
                "cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"
            ),
            patch(
                "cli_agent_orchestrator.utils.codex_home._codex_login_ok",
                return_value=True,
            ),
            patch(
                "cli_agent_orchestrator.utils.codex_home.load_agent_profile", return_value=profile
            ),
        ):
            codex_home = prepare_codex_home(
                terminal_id="abcd1234",
                agent_profile="codex_developer",
                working_directory=str(tmp_path / "work"),
                cao_home_dir=tmp_path / "cao",
                global_codex_home_dir=global_codex_home,
            )

        agents_md = codex_home / "AGENTS.md"
        assert agents_md.exists()
        assert agents_md.read_text().strip() == profile.system_prompt

    def test_prepare_codex_home_merges_trust_and_mcp(self, tmp_path: Path):
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text('model = "gpt-5.2"\n')
        (global_codex_home / "auth.json").write_text('{"ok":true}\n')

        workdir = tmp_path / "work"
        workdir.mkdir()

        profile = type(
            "Profile",
            (),
            {
                "name": "codex_developer",
                "description": "desc",
                "system_prompt": "x",
                "mcpServers": {
                    "example": {
                        "command": "echo",
                        "args": ["hello"],
                        "enabled": True,
                    }
                },
                "model": "gpt-5.2",
                "codexConfig": {"model_reasoning_effort": "high"},
            },
        )()

        with (
            patch(
                "cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"
            ),
            patch(
                "cli_agent_orchestrator.utils.codex_home._codex_login_ok",
                return_value=True,
            ),
            patch(
                "cli_agent_orchestrator.utils.codex_home.load_agent_profile", return_value=profile
            ),
        ):
            codex_home = prepare_codex_home(
                terminal_id="abcd1234",
                agent_profile="codex_developer",
                working_directory=str(workdir),
                cao_home_dir=tmp_path / "cao",
                global_codex_home_dir=global_codex_home,
            )

        data = _read_toml(codex_home / "config.toml")
        assert data["model"] == "gpt-5.2"
        assert data["model_reasoning_effort"] == "high"
        assert data["projects"][str(workdir)]["trust_level"] == "trusted"

        assert "mcp_servers" in data
        assert data["mcp_servers"]["example"]["command"] == "echo"
        assert data["mcp_servers"]["example"]["args"] == ["hello"]

        # CAO MCP server is always present
        assert data["mcp_servers"]["cao-mcp-server"]["command"] == "cao-mcp-server"

    def test_prepare_codex_home_overrides_cao_mcp_server_to_local_binary(self, tmp_path: Path):
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text('model = "gpt-5.2"\n')
        (global_codex_home / "auth.json").write_text('{"ok":true}\n')

        profile = type(
            "Profile",
            (),
            {
                "name": "codex_developer",
                "description": "desc",
                "system_prompt": "x",
                "mcpServers": {
                    "cao-mcp-server": {
                        "command": "uvx",
                        "args": ["--from", "somewhere", "cao-mcp-server"],
                        "enabled": True,
                    }
                },
                "model": None,
                "codexConfig": None,
            },
        )()

        with (
            patch(
                "cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"
            ),
            patch(
                "cli_agent_orchestrator.utils.codex_home._codex_login_ok",
                return_value=True,
            ),
            patch(
                "cli_agent_orchestrator.utils.codex_home.load_agent_profile", return_value=profile
            ),
        ):
            codex_home = prepare_codex_home(
                terminal_id="abcd1234",
                agent_profile="codex_developer",
                working_directory=str(tmp_path / "work"),
                cao_home_dir=tmp_path / "cao",
                global_codex_home_dir=global_codex_home,
            )

        data = _read_toml(codex_home / "config.toml")
        assert data["mcp_servers"]["cao-mcp-server"]["command"] == "cao-mcp-server"

    def test_prepare_codex_home_fails_fast_if_not_logged_in(self, tmp_path: Path):
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text('model = "gpt-5.2"\n')
        (global_codex_home / "auth.json").write_text('{"ok":true}\n')

        profile = type(
            "Profile",
            (),
            {
                "name": "codex_developer",
                "description": "desc",
                "system_prompt": "x",
                "mcpServers": None,
                "model": None,
                "codexConfig": None,
            },
        )()

        with (
            patch(
                "cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"
            ),
            patch(
                "cli_agent_orchestrator.utils.codex_home._codex_login_ok",
                return_value=False,
            ),
            patch(
                "cli_agent_orchestrator.utils.codex_home.load_agent_profile", return_value=profile
            ),
        ):
            with pytest.raises(ValueError, match="login"):
                prepare_codex_home(
                    terminal_id="abcd1234",
                    agent_profile="codex_developer",
                    working_directory=str(tmp_path / "work"),
                    cao_home_dir=tmp_path / "cao",
                    global_codex_home_dir=global_codex_home,
                )

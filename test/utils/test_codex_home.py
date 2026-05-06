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

    def test_prepare_codex_home_copies_codex_auth_state(self, tmp_path: Path):
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text('model = "gpt-5.2"\n')
        auth_files = {
            "auth.json": '{"ok":true}\n',
            "installation_id": "install-1\n",
            "state_5.sqlite": "state-db",
            "state_5.sqlite-wal": "state-wal",
            "state_5.sqlite-shm": "state-shm",
        }
        for name, contents in auth_files.items():
            (global_codex_home / name).write_text(contents)
        (global_codex_home / "history.jsonl").write_text('{"not":"copied"}\n')
        (global_codex_home / "logs_2.sqlite").write_text("logs")

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
                "reasoning_effort": None,
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

        for name, contents in auth_files.items():
            assert (codex_home / name).read_text() == contents
        assert not (codex_home / "history.jsonl").exists()
        assert not (codex_home / "logs_2.sqlite").exists()

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
                "reasoning_effort": "low",
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

    def test_prepare_codex_home_applies_reasoning_effort_when_not_overridden(self, tmp_path: Path):
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
                "mcpServers": None,
                "model": None,
                "reasoning_effort": "high",
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
                working_directory=str(workdir),
                cao_home_dir=tmp_path / "cao",
                global_codex_home_dir=global_codex_home,
            )

        data = _read_toml(codex_home / "config.toml")
        assert data["model_reasoning_effort"] == "high"

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

    def test_global_config_is_filtered_not_cloned(self, tmp_path: Path):
        """Per-terminal config inherits ONLY the allowlisted global keys.

        Every other section — custom agents (with relative config_file paths
        that would break in CODEX_HOME), user-level MCP servers, user trust
        entries, feature flags — must be dropped. Regression for the
        "Ignoring malformed agent role definition" warnings that came from
        naive cloning of the global config.
        """
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text(
            'model = "gpt-5.4"\n'
            'model_reasoning_effort = "high"\n'
            "\n"
            "[notice]\n"
            "hide_full_access_warning = true\n"
            "\n"
            "[features]\n"
            "multi_agent = true\n"
            "\n"
            "[agents.implementer]\n"
            'description = "User custom agent"\n'
            'config_file = "agents/implementer.toml"\n'
            "\n"
            "[projects.'/some/other/dir']\n"
            'trust_level = "trusted"\n'
            "\n"
            "[mcp_servers.user-global-server]\n"
            'command = "user-tool"\n'
        )
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
                "reasoning_effort": None,
            },
        )()

        with (
            patch(
                "cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"
            ),
            patch("cli_agent_orchestrator.utils.codex_home._codex_login_ok", return_value=True),
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

        # Allowlisted: inherited from global.
        assert data["model"] == "gpt-5.4"
        assert data["model_reasoning_effort"] == "high"
        assert data["notice"]["hide_full_access_warning"] is True

        # Dropped: every non-allowlisted section.
        assert "agents" not in data
        assert "user-global-server" not in data.get("mcp_servers", {})
        # Only the CAO-managed workdir trust entry should be present —
        # user's other trusted projects are NOT inherited.
        assert list(data["projects"].keys()) == [str(tmp_path / "work")]

        # Overridden: CAO forces features.multi_agent off even if user has it on.
        assert data["features"]["multi_agent"] is False

    def test_global_plugins_section_is_dropped_from_per_terminal_config(self, tmp_path: Path):
        """User-level ``[plugins.*]`` entries must not leak into per-terminal config.

        Note: this is *not* a suppression mechanism — Codex rewrites
        ``[plugins.*].enabled`` on interactive startup regardless of what's
        in the per-terminal config. Actual plugin suppression happens via
        the ``--disable plugins --disable apps`` CLI flags in
        ``providers/codex.py``. This test only asserts config-level
        isolation: CAO doesn't carry user globals into its sessions.
        """
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text(
            "[plugins.'github@openai-curated']\n"
            "enabled = true\n"
            "\n"
            "[plugins.'another-plugin']\n"
            "enabled = true\n"
        )
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
                "reasoning_effort": None,
            },
        )()

        with (
            patch(
                "cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"
            ),
            patch("cli_agent_orchestrator.utils.codex_home._codex_login_ok", return_value=True),
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
        assert "plugins" not in data

    def test_profile_model_wins_over_inherited_global_model(self, tmp_path: Path):
        """Agent profile settings take precedence over inherited globals."""
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        (global_codex_home / "config.toml").write_text(
            'model = "gpt-5.4"\nmodel_reasoning_effort = "low"\n'
        )
        (global_codex_home / "auth.json").write_text('{"ok":true}\n')

        profile = type(
            "Profile",
            (),
            {
                "name": "codex_developer",
                "description": "desc",
                "system_prompt": "x",
                "mcpServers": None,
                "model": "gpt-5.5-profile-override",
                "codexConfig": None,
                "reasoning_effort": "high",
            },
        )()

        with (
            patch(
                "cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"
            ),
            patch("cli_agent_orchestrator.utils.codex_home._codex_login_ok", return_value=True),
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
        assert data["model"] == "gpt-5.5-profile-override"
        assert data["model_reasoning_effort"] == "high"

    def test_missing_global_config_still_produces_valid_per_terminal_config(self, tmp_path: Path):
        """No ~/.codex/config.toml — the minimum CAO overrides still apply."""
        from cli_agent_orchestrator.utils.codex_home import prepare_codex_home

        global_codex_home = tmp_path / "global" / ".codex"
        global_codex_home.mkdir(parents=True)
        # No config.toml in global; only auth.json.
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
                "reasoning_effort": None,
            },
        )()

        with (
            patch(
                "cli_agent_orchestrator.utils.codex_home.shutil.which", return_value="/bin/codex"
            ),
            patch("cli_agent_orchestrator.utils.codex_home._codex_login_ok", return_value=True),
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
        assert data["features"]["multi_agent"] is False
        assert data["projects"][str(tmp_path / "work")]["trust_level"] == "trusted"
        assert data["mcp_servers"]["cao-mcp-server"]["command"] == "cao-mcp-server"

"""Tests for the install CLI command."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import frontmatter
import pytest
from click.testing import CliRunner

from cli_agent_orchestrator.cli.commands.install import _read_agent_source, install
from test.support.agent_factory import Agent
from cli_agent_orchestrator.models.kiro_agent import KiroAgentConfig
from cli_agent_orchestrator.utils.skill_injection import refresh_agent_json_prompt


def _create_skill(folder: Path, name: str, description: str, body: str = "# Skill\n\nBody") -> None:
    """Create a skill folder with SKILL.md and optional content."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        "---\n" f"name: {name}\n" f"description: {description}\n" "---\n\n" f"{body}\n"
    )


class TestReadAgentSource:
    """Tests for the _read_agent_source helper function."""

    @patch("cli_agent_orchestrator.cli.commands.install.requests.get")
    def test_read_from_url_success(self, mock_get):
        """Test reading agent markdown from URL."""
        mock_response = MagicMock()
        mock_response.text = "# Test Agent\nname: test"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        name, content = _read_agent_source("https://example.com/test-agent.md")

        assert name == "test-agent"
        assert content == "# Test Agent\nname: test"
        mock_get.assert_called_once_with("https://example.com/test-agent.md")

    def test_read_from_url_invalid_extension(self):
        """Test reading agent from URL with invalid extension."""
        with patch("cli_agent_orchestrator.cli.commands.install.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = "content"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with pytest.raises(ValueError, match="URL must point to a .md file"):
                _read_agent_source("https://example.com/test-agent.txt")

    def test_read_from_file_success(self):
        """Test reading agent from local file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "source-agent.md"
            source_file.write_text("# Test Agent\nname: test")

            name, content = _read_agent_source(str(source_file))

            assert name == "source-agent"
            assert content == "# Test Agent\nname: test"

    def test_read_from_file_invalid_extension(self):
        """Test reading agent from file with invalid extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "source-agent.txt"
            source_file.write_text("content")

            with pytest.raises(ValueError, match="File must be a .md file"):
                _read_agent_source(str(source_file))

    def test_read_source_not_found(self):
        """Test reading agent from non-existent source."""
        with pytest.raises(FileNotFoundError, match="Source not found"):
            _read_agent_source("/nonexistent/path/agent.md")


class TestInstallCommand:
    """Tests for the install command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def install_paths(self, tmp_path, monkeypatch):
        """Patch install paths into a temp workspace."""
        example_dir = tmp_path / "examples"
        context_dir = tmp_path / "agent-context"
        kiro_dir = tmp_path / "kiro"
        q_dir = tmp_path / "q"
        copilot_dir = tmp_path / "copilot"
        for path in (example_dir, context_dir, kiro_dir, q_dir, copilot_dir):
            path.mkdir()
        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.EXAMPLE_AGENTS_DIR", example_dir)
        monkeypatch.setattr(
            "cli_agent_orchestrator.cli.commands.install.AGENT_CONTEXT_DIR",
            context_dir,
        )
        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.KIRO_AGENTS_DIR", kiro_dir)
        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.Q_AGENTS_DIR", q_dir)
        monkeypatch.setattr(
            "cli_agent_orchestrator.cli.commands.install.COPILOT_AGENTS_DIR",
            copilot_dir,
        )
        return {
            "example_dir": example_dir,
            "context_dir": context_dir,
            "kiro_dir": kiro_dir,
            "q_dir": q_dir,
            "copilot_dir": copilot_dir,
        }

    @staticmethod
    def _write_agent(path: Path, *, prompt: str = "Test system prompt", extra: str = "") -> None:
        path.write_text(
            "---\n"
            "name: test-agent\n"
            "display_name: Test Agent\n"
            "description: Test agent description\n"
            f"{extra}"
            "---\n"
            f"{prompt}\n",
            encoding="utf-8",
        )

    def test_install_builtin_agent_kiro_cli(self, runner, install_paths, tmp_path, monkeypatch):
        """Built-in agent markdown installs for kiro_cli provider."""
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        self._write_agent(builtin_dir / "test-agent.md")
        monkeypatch.setattr(
            "cli_agent_orchestrator.cli.commands.install.EXAMPLE_AGENTS_DIR",
            builtin_dir,
        )

        result = runner.invoke(install, ["test-agent", "--provider", "kiro_cli"])

        assert result.exit_code == 0
        assert "installed successfully" in result.output
        assert (install_paths["context_dir"] / "test-agent.md").exists()
        assert (install_paths["kiro_dir"] / "test-agent.json").exists()

    @patch("cli_agent_orchestrator.cli.commands.install.requests.get")
    def test_install_from_url(self, mock_get, runner, install_paths):
        """Installing from URL reads the remote markdown before parsing."""
        mock_response = MagicMock()
        mock_response.text = "---\nname: downloaded-agent\ndescription: Downloaded agent\n---\nPrompt\n"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = runner.invoke(install, ["https://example.com/downloaded-agent.md"])

        assert result.exit_code == 0
        assert "installed successfully" in result.output

    def test_install_from_file_path(self, runner, install_paths, tmp_path):
        """Installing from file path reads the local markdown before parsing."""
        source = tmp_path / "local-agent.md"
        self._write_agent(source)

        result = runner.invoke(install, [str(source)])

        assert result.exit_code == 0
        assert "installed successfully" in result.output

    def test_install_file_not_found(self, runner):
        """Test installing non-existent agent."""
        result = runner.invoke(install, ["nonexistent-agent"])

        assert "Error" in result.output

    @patch("cli_agent_orchestrator.cli.commands.install.requests.get")
    def test_install_url_request_error(self, mock_get, runner):
        """Test installing from URL with request error."""
        import requests

        mock_get.side_effect = requests.RequestException("Connection failed")

        result = runner.invoke(install, ["https://example.com/agent.md"])

        assert "Error" in result.output
        assert "Failed to download agent" in result.output

    def test_install_general_error(self, runner, install_paths):
        """Test installing agent with general error."""
        self._write_agent(install_paths["example_dir"] / "test-agent.md")

        with patch(
            "cli_agent_orchestrator.cli.commands.install._parse_agent_markdown",
            side_effect=Exception("Unexpected error"),
        ):
            result = runner.invoke(install, ["test-agent"])

        assert "Error" in result.output
        assert "Failed to install agent" in result.output

    def test_install_help_describes_env_workflow(self, runner):
        """Help text should describe env file storage, ${VAR} syntax, and an example."""
        result = runner.invoke(install, ["--help"])

        assert result.exit_code == 0
        assert "~/.aws/cli-agent-orchestrator/.env" in result.output
        assert "${VAR}" in result.output
        assert "API_TOKEN=my-secret-token" in result.output

    def test_install_q_cli_provider(self, runner, install_paths):
        """Test installing agent for q_cli provider."""
        self._write_agent(install_paths["example_dir"] / "test-agent.md")

        result = runner.invoke(install, ["test-agent", "--provider", "q_cli"])

        assert result.exit_code == 0
        assert (install_paths["q_dir"] / "test-agent.json").exists()

    def test_install_with_mcp_servers(self, runner, install_paths):
        """Test installing agent with MCP servers (covers lines 115-116)."""
        self._write_agent(
            install_paths["example_dir"] / "test-agent.md",
            extra=(
                "mcpServers:\n"
                "  server1:\n"
                "    command: test\n"
                "  server2:\n"
                "    command: test2\n"
            ),
        )

        result = runner.invoke(install, ["test-agent", "--provider", "kiro_cli"])
        kiro_config = json.loads((install_paths["kiro_dir"] / "test-agent.json").read_text())

        assert result.exit_code == 0
        assert set(kiro_config["mcpServers"]) == {"server1", "server2"}

    def test_install_without_provider_specific_config(self, runner, install_paths):
        """Test installing agent for claude_code provider (no agent file created)."""
        self._write_agent(install_paths["example_dir"] / "test-agent.md")

        result = runner.invoke(install, ["test-agent", "--provider", "claude_code"])

        assert result.exit_code == 0
        assert "installed successfully" in result.output
        assert not list(install_paths["q_dir"].iterdir())
        assert not list(install_paths["kiro_dir"].iterdir())
        assert not list(install_paths["copilot_dir"].iterdir())

    def test_install_copilot_cli_provider(self, runner, install_paths):
        """Test installing agent for copilot_cli provider."""
        self._write_agent(install_paths["example_dir"] / "test-agent.md")

        result = runner.invoke(install, ["test-agent", "--provider", "copilot_cli"])

        assert result.exit_code == 0
        assert "installed successfully" in result.output
        assert "copilot_cli agent:" in result.output
        agent_file = install_paths["copilot_dir"] / "test-agent.agent.md"
        assert agent_file.exists()
        post = frontmatter.loads(agent_file.read_text())
        assert post.metadata["name"] == "test-agent"
        assert post.metadata["description"] == "Test agent description"
        assert "Test system prompt" in post.content

    def test_install_copilot_cli_provider_requires_prompt(self, runner, install_paths):
        """Test copilot_cli install fails when profile has no prompt text."""
        self._write_agent(install_paths["example_dir"] / "test-agent.md", prompt="")

        result = runner.invoke(install, ["test-agent", "--provider", "copilot_cli"])

        assert "Failed to install agent" in result.output
        assert "has no usable prompt content for Copilot" in result.output


class TestInstallCommandEnvFlags:
    """Tests for install-time env var injection."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def install_paths(self, tmp_path, monkeypatch):
        """Patch install-related filesystem paths into a temp workspace."""
        example_dir = tmp_path / "examples"
        context_dir = tmp_path / "agent-context"
        kiro_dir = tmp_path / "kiro"
        q_dir = tmp_path / "q"
        env_file = tmp_path / ".env"

        example_dir.mkdir()
        context_dir.mkdir()
        kiro_dir.mkdir()
        q_dir.mkdir()

        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.EXAMPLE_AGENTS_DIR", example_dir)
        monkeypatch.setattr(
            "cli_agent_orchestrator.cli.commands.install.AGENT_CONTEXT_DIR", context_dir
        )
        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.KIRO_AGENTS_DIR", kiro_dir)
        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.Q_AGENTS_DIR", q_dir)
        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.CAO_ENV_FILE", env_file)
        monkeypatch.setattr("cli_agent_orchestrator.utils.env.CAO_ENV_FILE", env_file)
        monkeypatch.setattr(
            "cli_agent_orchestrator.services.settings_service.get_agent_dirs", lambda: {}, raising=False
        )
        monkeypatch.setattr(
            "cli_agent_orchestrator.services.settings_service.get_extra_agent_dirs", lambda: [], raising=False
        )

        return {
            "example_dir": example_dir,
            "context_dir": context_dir,
            "kiro_dir": kiro_dir,
            "q_dir": q_dir,
            "env_file": env_file,
        }

    @staticmethod
    def _write_profile(profile_path: Path, body: str) -> None:
        """Write a local profile with env placeholders."""
        profile_path.write_text(
            "---\n"
            "name: test-agent\n"
            "description: Test agent\n"
            "mcpServers:\n"
            "  service:\n"
            "    command: service-mcp\n"
            "    env:\n"
            "      API_TOKEN: ${API_TOKEN}\n"
            "      BASE_URL: ${BASE_URL}\n"
            "      URL: ${URL}\n"
            "---\n"
            f"{body}\n"
        )

    def test_install_with_env_writes_env_file_and_resolves_provider_config(
        self, runner, install_paths
    ):
        """--env should persist to .env, resolve in provider config, but NOT in context file."""
        profile_path = install_paths["example_dir"] / "test-agent.md"
        self._write_profile(profile_path, "Token: ${API_TOKEN}")

        result = runner.invoke(
            install,
            [
                "test-agent",
                "--provider",
                "kiro_cli",
                "--env",
                "API_TOKEN=secret-token",
            ],
        )

        assert result.exit_code == 0
        assert install_paths["env_file"].read_text() == "API_TOKEN='secret-token'\n"
        assert f"✓ Set 1 env var(s) in {install_paths['env_file']}" in result.output

        # Context file keeps placeholders (secrets stay in .env)
        context_text = (install_paths["context_dir"] / "test-agent.md").read_text()
        assert "${API_TOKEN}" in context_text
        assert "secret-token" not in context_text

        # Provider config has resolved values (Kiro can't read .env)
        kiro_agent_file = install_paths["kiro_dir"] / "test-agent.json"
        kiro_config = json.loads(kiro_agent_file.read_text())
        assert kiro_config["mcpServers"]["service"]["env"]["API_TOKEN"] == "secret-token"

    def test_install_with_multiple_env_flags_writes_all_values(self, runner, install_paths):
        """Multiple --env flags should all be written before profile resolution."""
        profile_path = install_paths["example_dir"] / "test-agent.md"
        self._write_profile(profile_path, "Token: ${API_TOKEN}\nBase URL: ${BASE_URL}")

        result = runner.invoke(
            install,
            [
                "test-agent",
                "--provider",
                "kiro_cli",
                "--env",
                "API_TOKEN=secret-token",
                "--env",
                "BASE_URL=http://localhost:27124",
            ],
        )

        context_text = (install_paths["context_dir"] / "test-agent.md").read_text()

        assert result.exit_code == 0
        assert "API_TOKEN='secret-token'" in install_paths["env_file"].read_text()
        assert "BASE_URL='http://localhost:27124'" in install_paths["env_file"].read_text()
        # Context file keeps placeholders
        assert "${API_TOKEN}" in context_text
        assert "${BASE_URL}" in context_text
        assert f"✓ Set 2 env var(s) in {install_paths['env_file']}" in result.output

    def test_install_with_env_value_containing_equals_preserves_full_value(
        self, runner, install_paths
    ):
        """The first equals sign splits the assignment and later ones remain in the value."""
        profile_path = install_paths["example_dir"] / "test-agent.md"
        self._write_profile(profile_path, "URL: ${URL}")

        result = runner.invoke(
            install,
            [
                "test-agent",
                "--provider",
                "q_cli",
                "--env",
                "URL=http://host?a=b",
            ],
        )

        context_text = (install_paths["context_dir"] / "test-agent.md").read_text()
        q_agent_file = install_paths["q_dir"] / "test-agent.json"
        q_config = json.loads(q_agent_file.read_text())

        assert result.exit_code == 0
        assert "URL='http://host?a=b'" in install_paths["env_file"].read_text()
        # Context file keeps placeholder
        assert "${URL}" in context_text
        # Provider config has resolved value
        assert q_config["mcpServers"]["service"]["env"]["URL"] == "http://host?a=b"

    def test_install_with_invalid_env_format_returns_click_error(self, runner, install_paths):
        """Assignments without '=' should fail validation with a user-friendly error."""
        profile_path = install_paths["example_dir"] / "test-agent.md"
        self._write_profile(profile_path, "Token: ${API_TOKEN}")

        result = runner.invoke(install, ["test-agent", "--env", "INVALID_FORMAT"])

        assert result.exit_code == 2
        assert "Invalid value for --env" in result.output
        assert "Expected format KEY=VALUE" in result.output
        assert not install_paths["env_file"].exists()

    def test_install_with_empty_env_key_returns_click_error(self, runner, install_paths):
        """Assignments with an empty key should fail validation."""
        profile_path = install_paths["example_dir"] / "test-agent.md"
        self._write_profile(profile_path, "Token: ${API_TOKEN}")

        result = runner.invoke(install, ["test-agent", "--env", "=value"])

        assert result.exit_code == 2
        assert "Invalid value for --env" in result.output
        assert "Key must not be empty" in result.output
        assert not install_paths["env_file"].exists()

    def test_install_without_env_does_not_modify_env_file(self, runner, install_paths):
        """Install should not create or update the env file when --env is omitted."""
        profile_path = install_paths["example_dir"] / "test-agent.md"
        profile_path.write_text(
            "---\nname: test-agent\ndescription: Test agent\n---\nPlain system prompt\n"
        )

        result = runner.invoke(install, ["test-agent", "--provider", "kiro_cli"])

        assert result.exit_code == 0
        assert not install_paths["env_file"].exists()
        assert "Set 1 env var" not in result.output

    def test_install_warns_about_unresolved_env_vars(self, runner, install_paths):
        """Unresolved ${VAR} placeholders should trigger a stderr warning."""
        profile_path = install_paths["example_dir"] / "test-agent.md"
        self._write_profile(profile_path, "Token: ${API_TOKEN}")

        result = runner.invoke(
            install,
            ["test-agent", "--provider", "kiro_cli", "--env", "API_TOKEN=secret"],
        )

        assert result.exit_code == 0
        # API_TOKEN is set, but BASE_URL and URL are not
        assert "Unresolved env var(s)" in result.output
        assert "BASE_URL" in result.output
        assert "URL" in result.output
        assert "API_TOKEN" not in result.output.split("Unresolved")[1]

    def test_install_no_warning_when_all_env_vars_resolved(self, runner, install_paths):
        """No warning when every placeholder has a value in .env."""
        profile_path = install_paths["example_dir"] / "test-agent.md"
        profile_path.write_text(
            "---\nname: test-agent\ndescription: Test agent\n"
            "mcpServers:\n  svc:\n    command: svc\n    env:\n"
            "      KEY: ${KEY}\n---\nPrompt\n"
        )

        result = runner.invoke(
            install,
            ["test-agent", "--provider", "kiro_cli", "--env", "KEY=value"],
        )

        assert result.exit_code == 0
        assert "Unresolved" not in result.output

    def test_install_no_warning_when_profile_has_no_placeholders(self, runner, install_paths):
        """Profiles without any ${VAR} syntax should not trigger a warning."""
        profile_path = install_paths["example_dir"] / "test-agent.md"
        profile_path.write_text(
            "---\nname: test-agent\ndescription: Test agent\n---\nPlain prompt\n"
        )

        result = runner.invoke(install, ["test-agent", "--provider", "kiro_cli"])

        assert result.exit_code == 0
        assert "Unresolved" not in result.output

    def test_install_end_to_end_keeps_placeholders_in_context_file(
        self, runner, install_paths, tmp_path
    ):
        """Context file should preserve ${VAR} placeholders; secrets stay in .env."""
        install_paths["env_file"].write_text(
            "API_TOKEN=integration-secret\nSERVICE_URL=http://127.0.0.1:27124\n"
        )
        source_profile = tmp_path / "service-agent.md"
        source_profile.write_text(
            "---\n"
            "name: service-agent\n"
            "description: Integration test profile\n"
            "mcpServers:\n"
            "  service:\n"
            "    command: service-mcp\n"
            "    env:\n"
            "      API_TOKEN: ${API_TOKEN}\n"
            "      SERVICE_URL: ${SERVICE_URL}\n"
            "---\n"
            "Use the service endpoint at ${SERVICE_URL}.\n"
        )

        result = runner.invoke(install, [str(source_profile), "--provider", "claude_code"])

        installed_profile = install_paths["context_dir"] / "service-agent.md"
        installed_text = installed_profile.read_text()

        assert result.exit_code == 0
        assert "${API_TOKEN}" in installed_text
        assert "${SERVICE_URL}" in installed_text
        assert "integration-secret" not in installed_text


class TestInstallNativeSkillConfiguration:
    """Tests for provider-native skill configuration during install."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def install_workspace(self, tmp_path, monkeypatch):
        """Patch install and skills paths into a temp workspace."""
        example_dir = tmp_path / "examples"
        context_dir = tmp_path / "agent-context"
        kiro_dir = tmp_path / "kiro"
        q_dir = tmp_path / "q"
        skills_dir = tmp_path / "skills"

        example_dir.mkdir()
        context_dir.mkdir()
        kiro_dir.mkdir()
        q_dir.mkdir()
        skills_dir.mkdir()

        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.EXAMPLE_AGENTS_DIR", example_dir)
        monkeypatch.setattr(
            "cli_agent_orchestrator.cli.commands.install.AGENT_CONTEXT_DIR", context_dir
        )
        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.KIRO_AGENTS_DIR", kiro_dir)
        monkeypatch.setattr("cli_agent_orchestrator.cli.commands.install.Q_AGENTS_DIR", q_dir)
        monkeypatch.setattr("cli_agent_orchestrator.utils.skills.SKILLS_DIR", skills_dir)
        monkeypatch.setattr(
            "cli_agent_orchestrator.services.settings_service.get_agent_dirs", lambda: {}, raising=False
        )
        monkeypatch.setattr(
            "cli_agent_orchestrator.services.settings_service.get_extra_agent_dirs", lambda: [], raising=False
        )

        return {
            "example_dir": example_dir,
            "context_dir": context_dir,
            "kiro_dir": kiro_dir,
            "q_dir": q_dir,
            "skills_dir": skills_dir,
        }

    @staticmethod
    def _write_profile(profile_path: Path, frontmatter_body: str, system_prompt: str) -> None:
        """Write a local markdown profile for install tests."""
        profile_path.write_text(f"---\n{frontmatter_body}---\n{system_prompt}\n", encoding="utf-8")

    def test_install_kiro_uses_skill_resources_not_baked_prompt(self, runner, install_workspace):
        """Kiro installs should use skill:// glob in resources instead of baking catalog into prompt."""
        _create_skill(
            install_workspace["skills_dir"] / "python-testing",
            "python-testing",
            "Pytest conventions",
        )
        self._write_profile(
            install_workspace["example_dir"] / "test-agent.md",
            "name: test-agent\ndescription: Test agent\nprompt: Build things\n",
            "System prompt",
        )

        result = runner.invoke(install, ["test-agent", "--provider", "kiro_cli"])

        assert result.exit_code == 0
        agent_json = json.loads((install_workspace["kiro_dir"] / "test-agent.json").read_text())
        # Prompt should be the raw markdown body without skill catalog
        assert agent_json["prompt"] == "System prompt"
        assert "Available Skills" not in agent_json["prompt"]
        # Resources should contain the skill:// glob
        skill_resources = [r for r in agent_json["resources"] if r.startswith("skill://")]
        assert len(skill_resources) == 1
        assert skill_resources[0].endswith("/**/SKILL.md")

    def test_install_q_keeps_prompt_free_of_cao_skill_catalog(self, runner, install_workspace):
        """Q installs should not bake the CAO skill catalog into the JSON prompt."""
        _create_skill(
            install_workspace["skills_dir"] / "python-testing",
            "python-testing",
            "Pytest conventions",
        )
        self._write_profile(
            install_workspace["example_dir"] / "test-agent.md",
            "name: test-agent\ndescription: Test agent\nprompt: Build things\n",
            "System prompt",
        )

        result = runner.invoke(install, ["test-agent", "--provider", "q_cli"])

        assert result.exit_code == 0
        agent_json = json.loads((install_workspace["q_dir"] / "test-agent.json").read_text())
        assert agent_json["prompt"] == "System prompt"
        assert "Available Skills" not in agent_json["prompt"]
        assert "python-testing" not in agent_json["prompt"]

    def test_install_kiro_omits_prompt_field_when_profile_prompt_is_empty(
        self, runner, install_workspace
    ):
        """Empty profile prompt should omit prompt field; skill:// glob still in resources."""
        self._write_profile(
            install_workspace["example_dir"] / "test-agent.md",
            "name: test-agent\ndescription: Test agent\n",
            "",
        )

        result = runner.invoke(install, ["test-agent", "--provider", "kiro_cli"])

        assert result.exit_code == 0
        agent_path = install_workspace["kiro_dir"] / "test-agent.json"
        agent_json = json.loads(agent_path.read_text())
        assert "prompt" not in agent_json
        # skill:// glob should still be present in resources
        skill_resources = [r for r in agent_json["resources"] if r.startswith("skill://")]
        assert len(skill_resources) == 1

    def test_install_non_ascii_prompt_round_trips_through_refresh_without_byte_drift(
        self, runner, install_workspace
    ):
        """Non-ASCII prompt content should survive install and refresh with byte-identical JSON."""
        _create_skill(
            install_workspace["skills_dir"] / "unicode-skill",
            "unicode-skill",
            "Unicode skill",
        )
        self._write_profile(
            install_workspace["example_dir"] / "unicode-agent.md",
            "name: unicode-agent\ndescription: Test agent\nprompt: こんにちは 🚀\n",
            "こんにちは 🚀",
        )

        result = runner.invoke(install, ["unicode-agent", "--provider", "q_cli"])

        assert result.exit_code == 0
        agent_path = install_workspace["q_dir"] / "unicode-agent.json"
        before_refresh = agent_path.read_bytes()

        refreshed = refresh_agent_json_prompt(
            agent_path,
            Agent(name="unicode-agent", description="Test agent", prompt="こんにちは 🚀"),
        )

        assert refreshed is True
        assert agent_path.read_bytes() == before_refresh

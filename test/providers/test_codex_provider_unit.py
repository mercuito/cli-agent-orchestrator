"""Unit tests for Codex provider."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.base import CatalogDiscoveryError, ModelDiscoveryCapability
from cli_agent_orchestrator.providers.codex import (
    CODEX_DEBUG_MODELS_SOURCE,
    CODEX_RUNTIME_STATE_SCHEMA_VERSION,
    CODEX_THREAD_ID_PROBE_PREFIX,
    CodexModelDiscoveryCapability,
    CodexProvider,
    ProviderError,
    _build_codex_provider_model,
    parse_codex_thread_id_probe_output,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str) -> str:
    with open(FIXTURES_DIR / filename, "r") as f:
        return f.read()


def load_json_fixture(filename: str) -> str:
    return load_fixture(filename)


class TestCodexProviderInitialization:
    @patch("cli_agent_orchestrator.providers.codex.CodexProvider.run_update_preflight")
    @patch("cli_agent_orchestrator.providers.codex.wait_until_status")
    @patch("cli_agent_orchestrator.providers.codex.wait_for_shell")
    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_initialize_success(
        self, mock_tmux, mock_wait_shell, mock_wait_status, mock_update_preflight
    ):
        mock_wait_shell.return_value = True
        mock_wait_status.return_value = True
        mock_tmux.get_history.return_value = "OpenAI Codex (v0.98.0)"

        provider = CodexProvider("test1234", "test-session", "window-0", None)
        result = provider.initialize()

        assert result is True
        mock_update_preflight.assert_called_once()
        mock_wait_shell.assert_called_once()
        # Two send_keys calls: warm-up echo + codex with tmux-compatible flags
        assert mock_tmux.send_keys.call_count == 2
        mock_tmux.send_keys.assert_any_call("test-session", "window-0", "echo ready")
        mock_tmux.send_keys.assert_any_call(
            "test-session",
            "window-0",
            "codex --yolo --no-alt-screen --disable shell_snapshot --disable plugins --disable apps",
        )
        mock_wait_status.assert_called_once()

    @patch("cli_agent_orchestrator.providers.codex.wait_for_shell")
    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_initialize_shell_timeout(self, mock_tmux, mock_wait_shell):
        mock_wait_shell.return_value = False

        provider = CodexProvider("test1234", "test-session", "window-0", None)

        with pytest.raises(TimeoutError, match="Shell initialization timed out"):
            provider.initialize()

    @patch("cli_agent_orchestrator.providers.codex.CodexProvider.run_update_preflight")
    @patch("cli_agent_orchestrator.providers.codex.wait_until_status")
    @patch("cli_agent_orchestrator.providers.codex.wait_for_shell")
    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_initialize_codex_timeout(
        self, mock_tmux, mock_wait_shell, mock_wait_status, mock_update_preflight
    ):
        mock_wait_shell.return_value = True
        mock_wait_status.return_value = False
        mock_tmux.get_history.return_value = "OpenAI Codex (v0.98.0)"

        provider = CodexProvider("test1234", "test-session", "window-0", None)

        with pytest.raises(
            ProviderError,
            match="Codex initialization did not reach an idle state",
        ):
            provider.initialize()
        mock_update_preflight.assert_called_once()

    @patch("cli_agent_orchestrator.providers.codex.CodexProvider.run_update_preflight")
    @patch("cli_agent_orchestrator.providers.codex.wait_until_status")
    @patch("cli_agent_orchestrator.providers.codex.wait_for_shell")
    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_initialize_update_prompt_fails_before_waiting_for_idle(
        self, mock_tmux, mock_wait_shell, mock_wait_status, mock_update_preflight
    ):
        mock_wait_shell.return_value = True
        mock_tmux.get_history.return_value = (
            "A new Codex update is available.\n" "Run codex update, then please restart Codex.\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0", None)

        with pytest.raises(ProviderError, match="update/restart prompt"):
            provider.initialize()

        mock_update_preflight.assert_called_once()
        mock_wait_status.assert_not_called()

    @patch("cli_agent_orchestrator.providers.codex.CodexProvider.run_update_preflight")
    @patch("cli_agent_orchestrator.providers.codex.wait_until_status")
    @patch("cli_agent_orchestrator.providers.codex.wait_for_shell")
    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_initialize_unknown_startup_prompt_fails_with_diagnostics(
        self, mock_tmux, mock_wait_shell, mock_wait_status, mock_update_preflight
    ):
        mock_wait_shell.return_value = True
        mock_tmux.get_history.return_value = (
            "Codex needs one more startup decision.\n" "Press Enter to continue.\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0", None)

        with pytest.raises(ProviderError) as exc_info:
            provider.initialize()

        assert "unsupported interactive prompt" in str(exc_info.value)
        assert "Press Enter to continue" in str(exc_info.value)
        mock_update_preflight.assert_called_once()
        mock_wait_status.assert_not_called()


class TestCodexUpdatePreflight:
    @patch("cli_agent_orchestrator.providers.codex.subprocess.run")
    @patch("cli_agent_orchestrator.providers.codex.shutil.which", return_value="/bin/codex")
    def test_update_preflight_runs_codex_update_outside_managed_home(
        self, mock_which, mock_run, monkeypatch
    ):
        monkeypatch.setenv("CODEX_HOME", "/tmp/managed-codex-home")
        mock_run.return_value = MagicMock(returncode=0, stdout="already up to date")

        CodexProvider.run_update_preflight(timeout=3.0)

        mock_which.assert_called_once_with("codex")
        args, kwargs = mock_run.call_args
        assert args[0] == ["/bin/codex", "update"]
        assert kwargs["timeout"] == 3.0
        assert "CODEX_HOME" not in kwargs["env"]

    @patch("cli_agent_orchestrator.providers.codex.subprocess.run")
    @patch("cli_agent_orchestrator.providers.codex.shutil.which", return_value="/bin/codex")
    def test_update_preflight_failure_is_provider_error(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=7, stdout="network unavailable")

        with pytest.raises(ProviderError) as exc_info:
            CodexProvider.run_update_preflight(timeout=3.0)

        assert "Codex update preflight failed" in str(exc_info.value)
        assert "network unavailable" in str(exc_info.value)

    @patch("cli_agent_orchestrator.providers.codex.shutil.which", return_value=None)
    def test_update_preflight_missing_binary_is_provider_error(self, mock_which):
        with pytest.raises(ProviderError, match="codex binary not found"):
            CodexProvider.run_update_preflight(timeout=3.0)


class TestCodexModelDiscovery:
    def test_build_provider_model_filters_hidden_catalog_entries(self):
        # Given
        raw = {
            "slug": "test-hidden",
            "display_name": "Test Hidden",
            "visibility": "hide",
            "supported_reasoning_levels": [{"effort": "medium"}],
        }

        # When
        result = _build_codex_provider_model(raw)

        # Then
        assert result is None

    def test_build_provider_model_extracts_visible_model_metadata(self):
        # Given
        raw = {
            "slug": "test-visible",
            "display_name": "Test Visible",
            "visibility": "list",
            "supported_in_api": False,
            "context_window": 258400,
            "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}],
        }

        # When
        result = _build_codex_provider_model(raw)

        # Then
        assert result is not None
        assert result.id == "test-visible"
        assert result.display_name == "Test Visible"
        assert result.reasoning_efforts == ("low", "high")
        assert result.thinking_supported is True
        assert result.max_input_tokens == 258400
        assert result.max_output_tokens is None

    def test_codex_provider_exposes_model_discovery_capability(self):
        # When
        capability = CodexProvider.model_discovery_capability()

        # Then
        typed: ModelDiscoveryCapability = capability
        assert isinstance(capability, CodexModelDiscoveryCapability)
        assert typed is capability

    @patch("cli_agent_orchestrator.providers.codex.subprocess.run")
    @patch("cli_agent_orchestrator.providers.codex.shutil.which", return_value="/bin/codex")
    def test_discover_catalog_runs_codex_debug_models(self, mock_which, mock_run):
        # Given
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=load_json_fixture("codex_debug_models_response.json"),
            stderr="",
        )
        capability = CodexModelDiscoveryCapability()

        # When
        catalog = capability.discover_catalog()

        # Then
        mock_which.assert_called_once_with("codex")
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ["/bin/codex", "debug", "models"]
        assert kwargs["timeout"] == 10.0
        assert catalog.provider_type == "codex"
        assert catalog.source == CODEX_DEBUG_MODELS_SOURCE
        assert [model.id for model in catalog.models] == ["test-frontier", "test-cli-only"]
        assert catalog.models[1].reasoning_efforts == ("high",)
        assert catalog.models[1].max_input_tokens == 128000

    @patch("cli_agent_orchestrator.providers.codex.shutil.which", return_value=None)
    def test_discover_catalog_missing_binary_raises_catalog_discovery_error(self, mock_which):
        # Given
        capability = CodexModelDiscoveryCapability()

        # When / Then
        with pytest.raises(CatalogDiscoveryError, match="not installed"):
            capability.discover_catalog()
        mock_which.assert_called_once_with("codex")

    @patch("cli_agent_orchestrator.providers.codex.subprocess.run")
    @patch("cli_agent_orchestrator.providers.codex.shutil.which", return_value="/bin/codex")
    def test_discover_catalog_nonzero_exit_raises_catalog_discovery_error(
        self, mock_which, mock_run
    ):
        # Given
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="nope")
        capability = CodexModelDiscoveryCapability()

        # When / Then
        with pytest.raises(CatalogDiscoveryError) as exc_info:
            capability.discover_catalog()
        assert "exit 2" in str(exc_info.value)
        assert "nope" in str(exc_info.value)

    @patch("cli_agent_orchestrator.providers.codex.subprocess.run")
    @patch("cli_agent_orchestrator.providers.codex.shutil.which", return_value="/bin/codex")
    def test_discover_catalog_non_json_raises_catalog_discovery_error(self, mock_which, mock_run):
        # Given
        mock_run.return_value = MagicMock(returncode=0, stdout="not-json", stderr="")
        capability = CodexModelDiscoveryCapability()

        # When / Then
        with pytest.raises(CatalogDiscoveryError, match="non-JSON"):
            capability.discover_catalog()


class TestCodexBuildCommand:
    def test_build_command_no_profile(self):
        provider = CodexProvider("test1234", "test-session", "window-0", None)
        command = provider._build_codex_command()
        assert (
            command
            == "codex --yolo --no-alt-screen --disable shell_snapshot --disable plugins --disable apps"
        )

    def test_build_command_always_disables_plugins_and_apps(self):
        """Every CAO-spawned Codex session must suppress user-level plugins/apps.

        Codex auto-loads plugins from ~/.codex/plugins/ regardless of
        CODEX_HOME, and plugin state is account-authoritative — Codex
        overwrites local ``[plugins.*].enabled = false`` entries in
        config.toml on interactive startup. The ``--disable plugins`` and
        ``--disable apps`` CLI flags are the only reliable suppression.
        """
        provider = CodexProvider("test1234", "test-session", "window-0", "nonexistent-profile")
        with patch("cli_agent_orchestrator.providers.codex.load_agent") as m:
            m.side_effect = FileNotFoundError
            try:
                command = provider._build_codex_command()
            except Exception:
                # If command building aborts, we still want to know the base
                # command includes the flags before it got to profile loading.
                # Access the constant portion directly.
                command = "codex --yolo --no-alt-screen --disable shell_snapshot --disable plugins --disable apps"
        assert "--disable plugins" in command
        assert "--disable apps" in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_with_agent_id(self, mock_load_profile):
        mock_agent = MagicMock()
        mock_agent.prompt = "You are a code supervisor agent."
        mock_agent.mcp_servers = None
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "code_supervisor")
        command = provider._build_codex_command()

        mock_load_profile.assert_called_once_with("code_supervisor")
        assert (
            "codex --yolo --no-alt-screen --disable shell_snapshot --disable plugins --disable apps"
            in command
        )
        assert "-c" in command
        assert "developer_instructions=" in command
        assert "You are a code supervisor agent." in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_escapes_quotes(self, mock_load_profile):
        mock_agent = MagicMock()
        mock_agent.prompt = 'Use "double quotes" carefully.'
        mock_agent.mcp_servers = None
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "test_agent")
        command = provider._build_codex_command()

        assert '\\"double quotes\\"' in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_escapes_newlines(self, mock_load_profile):
        mock_agent = MagicMock()
        mock_agent.prompt = "Line one.\nLine two.\n\n## Section\n- Item"
        mock_agent.mcp_servers = None
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "test_agent")
        command = provider._build_codex_command()

        # Literal newlines must be escaped to \n for TOML and tmux compatibility
        assert "\n" not in command
        assert "\\n" in command
        assert "Line one.\\nLine two.\\n\\n## Section\\n- Item" in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_with_mcp_servers(self, mock_load_profile):
        mock_agent = MagicMock()
        mock_agent.prompt = "You are a supervisor."
        mock_agent.mcp_servers = {
            "cao-mcp-server": {
                "type": "stdio",
                "command": "uvx",
                "args": ["--from", "git+https://example.com/repo.git@main", "cao-mcp-server"],
            }
        }
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "code_supervisor")
        command = provider._build_codex_command()

        assert "mcp_servers.cao-mcp-server.command=" in command
        assert '"cao-mcp-server"' in command
        assert "uvx" not in command
        assert "mcp_servers.cao-mcp-server.args=" not in command
        assert "cao-mcp-server" in command
        # CAO_AGENT_ID must be forwarded for handoff to work
        assert "mcp_servers.cao-mcp-server.env_vars=" in command
        assert "CAO_AGENT_ID" in command
        # Tool timeout must be a TOML float (600.0) for Codex's f64 deserializer
        assert "mcp_servers.cao-mcp-server.tool_timeout_sec=600.0" in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_with_mcp_servers_env(self, mock_load_profile):
        mock_agent = MagicMock()
        mock_agent.prompt = ""
        mock_agent.mcp_servers = {
            "test-server": {
                "command": "npx",
                "args": ["-y", "test-server"],
                "env": {"API_KEY": "secret123"},
            }
        }
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "test_agent")
        command = provider._build_codex_command()

        assert "mcp_servers.test-server.command=" in command
        assert "mcp_servers.test-server.env.API_KEY=" in command
        assert "secret123" in command
        # CAO_AGENT_ID always forwarded even without explicit env_vars
        assert "mcp_servers.test-server.env_vars=" in command
        assert "CAO_AGENT_ID" in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_mcp_preserves_existing_env_vars(self, mock_load_profile):
        mock_agent = MagicMock()
        mock_agent.prompt = ""
        mock_agent.mcp_servers = {
            "my-server": {
                "command": "node",
                "args": ["server.js"],
                "env_vars": ["HOME", "PATH"],
            }
        }
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "test_agent")
        command = provider._build_codex_command()

        # Existing env_vars preserved and CAO_AGENT_ID appended
        assert "HOME" in command
        assert "PATH" in command
        assert "CAO_AGENT_ID" in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_mcp_overrides_existing_cao_agent_id_env(self, mock_load_profile):
        mock_agent = MagicMock()
        mock_agent.prompt = ""
        mock_agent.mcp_servers = {
            "my-server": {
                "command": "node",
                "env": {"CAO_AGENT_ID": "spoofed-agent"},
            }
        }
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "test_agent")
        command = provider._build_codex_command()

        assert 'mcp_servers.my-server.env.CAO_AGENT_ID="test_agent"' in command
        assert "spoofed-agent" not in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_empty_system_prompt(self, mock_load_profile):
        mock_agent = MagicMock()
        mock_agent.prompt = ""
        mock_agent.mcp_servers = None
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "empty_agent")
        command = provider._build_codex_command()

        assert "developer_instructions" not in command
        assert "mcp_servers.cao-mcp-server.command=" in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_none_system_prompt(self, mock_load_profile):
        mock_agent = MagicMock()
        mock_agent.prompt = None
        mock_agent.mcp_servers = None
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "none_agent")
        command = provider._build_codex_command()

        assert "developer_instructions" not in command
        assert "mcp_servers.cao-mcp-server.command=" in command

    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    def test_build_command_profile_load_failure(self, mock_load_profile):
        mock_load_profile.side_effect = RuntimeError("Agent not found")

        provider = CodexProvider("test1234", "test-session", "window-0", "bad_agent")

        with pytest.raises(ProviderError, match="Failed to load agent"):
            provider._build_codex_command()

    @patch("cli_agent_orchestrator.providers.codex.CodexProvider.run_update_preflight")
    @patch("cli_agent_orchestrator.providers.codex.wait_until_status")
    @patch("cli_agent_orchestrator.providers.codex.wait_for_shell")
    @patch("cli_agent_orchestrator.providers.codex.load_agent")
    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_initialize_with_agent_id(
        self,
        mock_tmux,
        mock_load_profile,
        mock_wait_shell,
        mock_wait_status,
        mock_update_preflight,
    ):
        mock_wait_shell.return_value = True
        mock_wait_status.return_value = True
        mock_tmux.get_history.return_value = "OpenAI Codex (v0.98.0)"
        mock_agent = MagicMock()
        mock_agent.prompt = "You are a supervisor."
        mock_agent.mcp_servers = None
        mock_load_profile.return_value = mock_agent

        provider = CodexProvider("test1234", "test-session", "window-0", "code_supervisor")
        result = provider.initialize()

        assert result is True
        mock_update_preflight.assert_called_once()
        # The second send_keys call should contain developer_instructions
        codex_call = mock_tmux.send_keys.call_args_list[1]
        assert "developer_instructions=" in codex_call.args[2]
        assert "You are a supervisor." in codex_call.args[2]


class TestCodexProviderStatusDetection:
    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_idle(self, mock_tmux):
        mock_tmux.get_history.return_value = load_fixture("codex_idle_output.txt")

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.IDLE

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_completed(self, mock_tmux):
        mock_tmux.get_history.return_value = load_fixture("codex_completed_output.txt")

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_processing(self, mock_tmux):
        mock_tmux.get_history.return_value = load_fixture("codex_processing_output.txt")

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.PROCESSING

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_waiting_user_answer(self, mock_tmux):
        mock_tmux.get_history.return_value = load_fixture("codex_permission_output.txt")

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.WAITING_USER_ANSWER

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_error(self, mock_tmux):
        mock_tmux.get_history.return_value = load_fixture("codex_error_output.txt")

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.ERROR

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_empty_output(self, mock_tmux):
        mock_tmux.get_history.return_value = ""

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.ERROR

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_with_tail_lines(self, mock_tmux):
        mock_tmux.get_history.return_value = load_fixture("codex_idle_output.txt")

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status(tail_lines=50)

        assert status == TerminalStatus.IDLE
        mock_tmux.get_history.assert_called_once_with("test-session", "window-0", tail_lines=50)

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_processing_when_old_prompt_present(self, mock_tmux):
        # If the captured history contains an earlier prompt but the *latest* output is processing,
        # we should report PROCESSING. The old prompt should be far enough from the bottom
        # (more than IDLE_PROMPT_TAIL_LINES) to avoid false idle detection.
        mock_tmux.get_history.return_value = (
            "Welcome to Codex\n"
            "❯ \n"
            "You Fix the failing tests\n"
            "assistant: Working on it...\n"
            "Reading file src/main.py...\n"
            "Analyzing code structure...\n"
            "Checking dependencies...\n"
            "Codex is thinking…\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.PROCESSING

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_not_error_on_failed_in_message(self, mock_tmux):
        # "failed" is commonly used in normal assistant output; it should not automatically
        # force ERROR.
        mock_tmux.get_history.return_value = (
            "You Explain why the test failed\n"
            "assistant: The test failed because the assertion is incorrect.\n"
            "\n"
            "❯ \n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_idle_if_no_assistant_after_last_user(self, mock_tmux):
        # If there is a user message but no assistant response after it, we should not
        # treat the session as COMPLETED.
        mock_tmux.get_history.return_value = "assistant: Welcome\n" "You Do the thing\n" "\n" "❯ \n"

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.IDLE

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_processing_when_no_prompt_and_no_keywords(self, mock_tmux):
        # Codex output may not always include explicit "thinking/processing" keywords.
        # Without an idle prompt at the end, we should assume it's still processing.
        mock_tmux.get_history.return_value = "You Run the command\nWorking...\n"

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.PROCESSING

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_not_error_when_assistant_mentions_error_text(self, mock_tmux):
        mock_tmux.get_history.return_value = (
            "You Explain the failure\n"
            "assistant: Here's an example error:\n"
            "Error: example only\n"
            "\n"
            "❯ \n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_not_waiting_when_assistant_mentions_approval_text(self, mock_tmux):
        mock_tmux.get_history.return_value = (
            "You Explain approvals\n"
            "assistant: You might see this prompt:\n"
            "Approve this command? [y/n]\n"
            "\n"
            "❯ \n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_error_when_error_after_user_and_prompt(self, mock_tmux):
        mock_tmux.get_history.return_value = "You Run thing\nError: failed\n\n❯ \n"

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.ERROR

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_waiting_user_answer_when_no_user_prefix(self, mock_tmux):
        mock_tmux.get_history.return_value = "Approve this command? [y/n]\n"

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.WAITING_USER_ANSWER

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_error_when_no_user_prefix(self, mock_tmux):
        mock_tmux.get_history.return_value = "Error: something failed\n"

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.ERROR

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_idle_tui_with_status_bar(self, mock_tmux):
        """Test IDLE detection with realistic TUI output (status bar after prompt)."""
        mock_tmux.get_history.return_value = (
            "╭───────────────────────────────────────────╮\n"
            "│ >_ OpenAI Codex (v0.98.0)                 │\n"
            "│ model: gpt-5.3-codex high                 │\n"
            "│ directory: ~/project                      │\n"
            "╰───────────────────────────────────────────╯\n"
            "  Tip: Try the Codex App\n"
            "› Use /skills to list available skills\n"
            "  ? for shortcuts                     100% context left\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.IDLE

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_completed_tui_with_status_bar(self, mock_tmux):
        """Test COMPLETED detection with TUI output (status bar after prompt)."""
        mock_tmux.get_history.return_value = (
            "You Fix the bug\n"
            "assistant: I've fixed the issue in main.py.\n"
            "\n"
            "› \n"
            "  ? for shortcuts                     100% context left\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED


class TestCodexBulletFormatStatusDetection:
    """Tests for Codex's real interactive output format using › prompt and • bullets."""

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_completed_bullet_format(self, mock_tmux):
        """COMPLETED when › user message followed by • response and idle prompt."""
        mock_tmux.get_history.return_value = (
            "› what is your role?\n"
            "• I am the Coding Supervisor Agent.\n"
            "• I coordinate tasks between developer and reviewer agents.\n"
            "\n"
            "› \n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_processing_bullet_format(self, mock_tmux):
        """PROCESSING when • response started but no idle prompt at bottom."""
        mock_tmux.get_history.return_value = (
            "› fix the failing tests\n"
            "• Let me look at the test files.\n"
            "Reading src/test_main.py...\n"
            "Analyzing code structure...\n"
            "Checking dependencies...\n"
            "Running unit tests...\n"
            "Codex is thinking…\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.PROCESSING

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_idle_bullet_format_no_response(self, mock_tmux):
        """IDLE when › user message but no • response yet and idle prompt at bottom."""
        mock_tmux.get_history.return_value = "› hello\n\n› \n"

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.IDLE

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_completed_bullet_with_code_block(self, mock_tmux):
        """COMPLETED with • response containing code blocks."""
        mock_tmux.get_history.return_value = (
            "› show me a function\n"
            "• Here's the function:\n"
            "\n"
            "  ```python\n"
            "  def hello():\n"
            "      print('hello')\n"
            "  ```\n"
            "\n"
            "• Let me know if you need changes.\n"
            "\n"
            "› \n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_error_not_masked_by_bullet_pattern(self, mock_tmux):
        """ERROR still detected when no • response and error after › user message."""
        mock_tmux.get_history.return_value = "› do something\nError: connection refused\n"

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.ERROR

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_completed_multi_turn_bullet(self, mock_tmux):
        """COMPLETED uses last user message in multi-turn bullet format."""
        mock_tmux.get_history.return_value = (
            "› first question\n"
            "• First answer.\n"
            "\n"
            "› second question\n"
            "• Second answer with details.\n"
            "\n"
            "› \n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_completed_bullet_with_tui_status_bar(self, mock_tmux):
        """COMPLETED with bullet format and TUI status bar after prompt."""
        mock_tmux.get_history.return_value = (
            "› fix the bug\n"
            "• I've fixed the issue in main.py by correcting the import.\n"
            "\n"
            "› \n"
            "  ? for shortcuts                     98% context left\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_processing_tui_spinner(self, mock_tmux):
        """PROCESSING when TUI shows • Working spinner, not false COMPLETED."""
        mock_tmux.get_history.return_value = (
            "› [CAO Handoff] Supervisor agent ID: sup-123. Do the task.\n"
            "\n"
            "• Working (0s • esc to interrupt)\n"
            "\n"
            "› Use /skills to list available skills\n"
            "\n"
            "  ? for shortcuts                     100% context left\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.PROCESSING

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_processing_tui_thinking_spinner(self, mock_tmux):
        """PROCESSING when TUI shows • Thinking spinner."""
        mock_tmux.get_history.return_value = (
            "› Implement feature X\n"
            "\n"
            "• Thinking (3s • esc to interrupt)\n"
            "\n"
            "› Run /review on my current changes\n"
            "\n"
            "  ? for shortcuts                     95% context left\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.PROCESSING

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_processing_dynamic_spinner_text(self, mock_tmux):
        """PROCESSING when TUI shows spinner with dynamic prefix text."""
        mock_tmux.get_history.return_value = (
            "› [CAO Handoff] Do the task.\n"
            "\n"
            "• Creating /tmp/file.py\n"
            "\n"
            "• Starting script creation (10s • esc to interrupt)\n"
            "\n"
            "› Use /skills to list available skills\n"
            "\n"
            "  ? for shortcuts                     100% context left\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.PROCESSING


class TestCodexV0111FooterFormat:
    """Tests for Codex v0.111.0+ TUI footer format.

    v0.111.0 (PR #13202 'tui: restore draft footer hints') changed the footer:
    - Old: "› Use /skills to list available skills\\n  ? for shortcuts  100% context left"
    - New: "› Find and fix a bug in @filename\\n  gpt-5.3-codex high · 100% left · ~/path"
    The new format uses "N% left" instead of "N% context left" and removes "? for shortcuts".
    """

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_idle_v0111_footer(self, mock_tmux):
        """IDLE with v0.111.0 footer format (no '? for shortcuts')."""
        mock_tmux.get_history.return_value = (
            "╭───────────────────────────────────────────╮\n"
            "│ >_ OpenAI Codex (v0.111.0)                │\n"
            "│ model: gpt-5.3-codex high                 │\n"
            "│ directory: ~/project                      │\n"
            "╰───────────────────────────────────────────╯\n"
            "  Tip: You can run any shell command from Codex using ! (e.g. !ls)\n"
            "\n"
            "› Find and fix a bug in @filename\n"
            "\n"
            "  gpt-5.3-codex high · 100% left · ~/project\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.IDLE

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_completed_v0111_footer(self, mock_tmux):
        """COMPLETED with v0.111.0 footer (suggestion hint must not be treated as user input)."""
        mock_tmux.get_history.return_value = (
            "› fix the bug\n"
            "• I've fixed the issue in main.py by correcting the import.\n"
            "\n"
            "› Find and fix a bug in @filename\n"
            "\n"
            "  gpt-5.3-codex high · 98% left · ~/project\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_completed_v0111_multi_turn(self, mock_tmux):
        """COMPLETED in multi-turn with v0.111.0 footer."""
        mock_tmux.get_history.return_value = (
            "› first question\n"
            "• First answer.\n"
            "\n"
            "› second question\n"
            "• Second answer with details.\n"
            "\n"
            "› Write tests for @main.py\n"
            "\n"
            "  gpt-5.3-codex high · 95% left · ~/project\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.COMPLETED

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_processing_v0111_spinner(self, mock_tmux):
        """PROCESSING when TUI shows spinner with v0.111.0 footer."""
        mock_tmux.get_history.return_value = (
            "› [CAO Handoff] Do the task.\n"
            "\n"
            "• Working (0s • esc to interrupt)\n"
            "\n"
            "› Find and fix a bug in @filename\n"
            "\n"
            "  gpt-5.3-codex high · 100% left · ~/project\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        assert status == TerminalStatus.PROCESSING


class TestCodexProviderMessageExtraction:
    def test_extract_last_message_success(self):
        output = load_fixture("codex_completed_output.txt")

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        assert "Here's the fix" in message
        assert "All tests now pass." in message

    def test_extract_complex_message(self):
        output = load_fixture("codex_complex_response.txt")

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        assert "def add(a, b):" in message
        assert "Let me know" in message

    def test_extract_message_no_marker(self):
        output = "No assistant prefix here"

        provider = CodexProvider("test1234", "test-session", "window-0")

        with pytest.raises(ValueError, match="No Codex response found"):
            provider.extract_last_message_from_script(output)

    def test_extract_message_empty_response(self):
        output = "assistant:   \n\n❯ "

        provider = CodexProvider("test1234", "test-session", "window-0")

        with pytest.raises(ValueError, match="Empty Codex response"):
            provider.extract_last_message_from_script(output)


class TestCodexBulletFormatExtraction:
    """Tests for message extraction from Codex's real • bullet format."""

    def test_extract_bullet_format_single_line(self):
        """Extract single-line • response."""
        output = "› what is your role?\n• I am the Coding Supervisor Agent.\n\n› \n"

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        assert "I am the Coding Supervisor Agent." in message

    def test_extract_bullet_format_multi_line(self):
        """Extract multi-line • response with all bullets preserved."""
        output = (
            "› describe your capabilities\n"
            "• I can coordinate development tasks.\n"
            "• I assign work to developer agents.\n"
            "• I review results from workers.\n"
            "\n"
            "› \n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        assert "coordinate development tasks" in message
        assert "assign work" in message
        assert "review results" in message

    def test_extract_bullet_format_with_code_block(self):
        """Extract • response containing code blocks."""
        output = (
            "› show me the fix\n"
            "• Here's the corrected code:\n"
            "\n"
            "  ```python\n"
            "  def add(a, b):\n"
            "      return a + b\n"
            "  ```\n"
            "\n"
            "• All tests pass now.\n"
            "\n"
            "› \n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        assert "def add(a, b):" in message
        assert "All tests pass now." in message

    def test_extract_bullet_format_multi_turn(self):
        """Extract only the last response from multi-turn • format."""
        output = (
            "› first question\n"
            "• First answer.\n"
            "\n"
            "› second question\n"
            "• Second answer with more detail.\n"
            "• Additional context here.\n"
            "\n"
            "› \n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        # Should only contain the second response
        assert "First answer" not in message
        assert "Second answer with more detail." in message
        assert "Additional context here." in message

    def test_extract_bullet_format_without_trailing_prompt(self):
        """Extract • response when no trailing idle prompt (output still streaming)."""
        output = "› fix the bug\n• I've fixed the import issue in main.py.\n"

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        assert "I've fixed the import issue" in message


class TestCodexV0111Extraction:
    """Extraction tests for Codex v0.111.0+ footer format."""

    def test_extract_bullet_with_v0111_footer(self):
        """Extract response when v0.111.0 footer (suggestion hint) is present."""
        output = (
            "› fix the bug\n"
            "• I've fixed the issue in main.py by correcting the import.\n"
            "\n"
            "› Find and fix a bug in @filename\n"
            "\n"
            "  gpt-5.3-codex high · 98% left · ~/project\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        assert "I've fixed the issue" in message
        # Suggestion hint should not leak into extracted output
        assert "Find and fix a bug" not in message
        assert "gpt-5.3-codex" not in message

    def test_extract_multi_turn_with_v0111_footer(self):
        """Extract last response from multi-turn with v0.111.0 footer."""
        output = (
            "› first question\n"
            "• First answer.\n"
            "\n"
            "› second question\n"
            "• Second answer with details.\n"
            "\n"
            "› Write tests for @main.py\n"
            "\n"
            "  gpt-5.3-codex high · 95% left · ~/project\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        assert "First answer" not in message
        assert "Second answer with details." in message
        assert "Write tests" not in message

    def test_extract_double_blank_between_hint_and_status(self):
        """Suggestion hint must not leak when 2 blank lines separate it from status bar."""
        output = (
            "› fix the bug\n"
            "• I've fixed the issue in main.py by correcting the import.\n"
            "\n"
            "› Find and fix a bug in @filename\n"
            "\n"
            "\n"
            "  gpt-5.3-codex high · 98% left · ~/project\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)

        assert "I've fixed the issue" in message
        assert "Find and fix a bug" not in message


class TestCodexProviderMisc:
    @patch("cli_agent_orchestrator.providers.base.tmux_client")
    def test_interrupt_sends_escape_while_processing(self, mock_tmux):
        provider = CodexProvider("test1234", "test-session", "window-0")
        provider.get_status = MagicMock(return_value=TerminalStatus.PROCESSING)

        assert provider.interrupt() is True
        provider.get_status.assert_called_once_with()
        mock_tmux.send_special_key.assert_called_once_with(
            "test-session",
            "window-0",
            "Escape",
        )

    def test_paste_enter_count_uses_provider_runtime_config(self):
        provider = CodexProvider("test1234", "test-session", "window-0")

        assert provider.paste_enter_count == 3

    def test_get_idle_pattern_for_log(self):
        provider = CodexProvider("test1234", "test-session", "window-0")
        pattern = provider.get_idle_pattern_for_log()
        # Codex TUI renders ❯ via cursor positioning (capture-pane only).
        # The pipe-pane log contains "? for shortcuts" from the TUI footer.
        assert pattern == r"\? for shortcuts"
        import re

        assert re.search(pattern, "? for shortcuts")

    def test_exit_cli(self):
        provider = CodexProvider("test1234", "test-session", "window-0")
        assert provider.exit_cli() == "/exit"

    def test_cleanup(self):
        provider = CodexProvider("test1234", "test-session", "window-0")
        provider._initialized = True
        provider.cleanup()
        assert provider._initialized is False

    def test_extract_last_message_without_trailing_prompt(self):
        output = "You do thing\nassistant: Hello\nSecond line\n"
        provider = CodexProvider("test1234", "test-session", "window-0")
        message = provider.extract_last_message_from_script(output)
        assert message == "Hello\nSecond line"


class TestCodexRuntimeStateCapability:
    def test_payload_serializes_to_minimal_schema_and_thread_id_only(self, tmp_path):
        capability = CodexProvider.runtime_state_capability()
        state = capability.deserialize_runtime_state(
            {
                "schema_version": CODEX_RUNTIME_STATE_SCHEMA_VERSION,
                "thread_id": "019e0707-afb4-72e3-ad1e-468306ca90f8",
            },
            provider_data_dir=tmp_path,
        )

        payload = capability.serialize_runtime_state(state)

        assert payload == {
            "schema_version": CODEX_RUNTIME_STATE_SCHEMA_VERSION,
            "thread_id": "019e0707-afb4-72e3-ad1e-468306ca90f8",
        }
        assert state.provider_data_dir == tmp_path

    @pytest.mark.parametrize(
        "payload",
        [
            {"schema_version": "unknown", "thread_id": "thread-1"},
            {"schema_version": CODEX_RUNTIME_STATE_SCHEMA_VERSION},
            {"schema_version": CODEX_RUNTIME_STATE_SCHEMA_VERSION, "thread_id": ""},
        ],
    )
    def test_deserialize_rejects_invalid_payloads(self, payload, tmp_path):
        capability = CodexProvider.runtime_state_capability()

        with pytest.raises(ValueError):
            capability.deserialize_runtime_state(payload, provider_data_dir=tmp_path)

    def test_launch_resume_args_use_validated_thread_id(self, tmp_path):
        capability = CodexProvider.runtime_state_capability()
        state = capability.deserialize_runtime_state(
            {
                "schema_version": CODEX_RUNTIME_STATE_SCHEMA_VERSION,
                "thread_id": "thread-123",
            },
            provider_data_dir=tmp_path,
        )

        assert capability.launch_resume_args(state, provider_data_dir=tmp_path) == [
            "resume",
            "thread-123",
        ]

    def test_runtime_resume_args_are_appended_to_codex_command(self):
        provider = CodexProvider(
            "test1234",
            "test-session",
            "window-0",
            runtime_resume_args=["resume", "thread-123"],
        )

        assert provider._build_codex_command().endswith("resume thread-123")

    def test_probe_parser_uses_nonce_and_ignores_unrelated_output(self):
        output = (
            "unrelated CODEX_THREAD_ID=wrong\n"
            f"{CODEX_THREAD_ID_PROBE_PREFIX}other=other-thread\n"
            f"{CODEX_THREAD_ID_PROBE_PREFIX}abc123=thread-123\n"
        )

        assert parse_codex_thread_id_probe_output(output, nonce="abc123") == "thread-123"
        assert parse_codex_thread_id_probe_output(output, nonce="missing") is None

    def test_probe_parser_tolerates_codex_wrapped_thread_id_output(self):
        output = (
            f"{CODEX_THREAD_ID_PROBE_PREFIX}abc123=019e0b8\n" "    c-0138-7130-885e-9fbf56f88782\n"
        )

        assert (
            parse_codex_thread_id_probe_output(output, nonce="abc123")
            == "019e0b8c-0138-7130-885e-9fbf56f88782"
        )

    @patch("cli_agent_orchestrator.providers.codex.uuid.uuid4")
    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    @patch("cli_agent_orchestrator.providers.codex.get_terminal_metadata")
    def test_discover_current_runtime_state_uses_no_llm_probe(
        self,
        mock_get_metadata,
        mock_tmux,
        mock_uuid4,
        tmp_path,
    ):
        mock_uuid4.return_value.hex = "abc123"
        mock_get_metadata.return_value = {
            "tmux_session": "cao-session",
            "tmux_window": "window-1",
        }
        mock_tmux.get_history.return_value = f"{CODEX_THREAD_ID_PROBE_PREFIX}abc123=thread-123"

        state = CodexProvider.runtime_state_capability().discover_current_runtime_state(
            terminal_id="terminal-1",
            provider_data_dir=tmp_path,
        )

        assert state is not None
        assert state.payload == {
            "schema_version": CODEX_RUNTIME_STATE_SCHEMA_VERSION,
            "thread_id": "thread-123",
        }
        mock_tmux.send_keys.assert_called_once_with(
            "cao-session",
            "window-1",
            f'!printf "%s\\n" "{CODEX_THREAD_ID_PROBE_PREFIX}abc123=$CODEX_THREAD_ID"',
        )


class TestCodexProviderTrustPrompt:
    """Tests for Codex workspace trust prompt handling."""

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_handle_trust_prompt_detected_and_accepted(self, mock_tmux):
        """Test that trust prompt is detected and auto-accepted."""
        mock_tmux.get_history.return_value = (
            "> You are running Codex in /Users/test/project\n"
            "\n"
            "  Since this folder is version controlled, you may wish to "
            "allow Codex to work in this folder without asking for approval.\n"
            "\n"
            "› 1. Yes, allow Codex to work in this folder without asking for approval\n"
            "  2. No, ask me to approve edits and commands\n"
        )
        mock_session = MagicMock()
        mock_window = MagicMock()
        mock_pane = MagicMock()
        mock_tmux.server.sessions.get.return_value = mock_session
        mock_session.windows.get.return_value = mock_window
        mock_window.active_pane = mock_pane

        provider = CodexProvider("test1234", "test-session", "window-0")
        provider._handle_trust_prompt(timeout=2.0)

        mock_pane.send_keys.assert_called_once_with("", enter=True)

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_handle_trust_prompt_not_needed(self, mock_tmux):
        """Test early return when Codex starts without trust prompt."""
        mock_tmux.get_history.return_value = "OpenAI Codex (v0.98.0)\n› "

        provider = CodexProvider("test1234", "test-session", "window-0")
        provider._handle_trust_prompt(timeout=2.0)

        mock_tmux.server.sessions.get.assert_not_called()

    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_get_status_trust_prompt_is_waiting_user_answer(self, mock_tmux):
        """Test that trust prompt reports WAITING_USER_ANSWER, not PROCESSING."""
        mock_tmux.get_history.return_value = (
            "> You are running Codex in /Users/test/project\n"
            "allow Codex to work in this folder without asking for approval.\n"
            "› 1. Yes\n"
        )

        provider = CodexProvider("test1234", "test-session", "window-0")
        status = provider.get_status()

        # Should be WAITING_USER_ANSWER (not PROCESSING despite "running" in text)
        assert status == TerminalStatus.WAITING_USER_ANSWER

    @patch("cli_agent_orchestrator.providers.codex.CodexProvider.run_update_preflight")
    @patch("cli_agent_orchestrator.providers.codex.wait_until_status")
    @patch("cli_agent_orchestrator.providers.codex.wait_for_shell")
    @patch("cli_agent_orchestrator.providers.codex.tmux_client")
    def test_initialize_with_trust_prompt(
        self, mock_tmux, mock_wait_shell, mock_wait_status, mock_update_preflight
    ):
        """Test that initialize handles trust prompt during startup."""
        mock_wait_shell.return_value = True
        mock_wait_status.return_value = True
        mock_tmux.get_history.return_value = (
            "allow Codex to work in this folder without asking for approval.\n"
        )
        mock_session = MagicMock()
        mock_window = MagicMock()
        mock_pane = MagicMock()
        mock_tmux.server.sessions.get.return_value = mock_session
        mock_session.windows.get.return_value = mock_window
        mock_window.active_pane = mock_pane

        provider = CodexProvider("test1234", "test-session", "window-0")
        result = provider.initialize()

        assert result is True
        mock_update_preflight.assert_called_once()
        mock_pane.send_keys.assert_called_with("", enter=True)

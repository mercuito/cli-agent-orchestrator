"""Claude Code provider implementation."""

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, cast

import requests  # type: ignore[import-untyped]

from cli_agent_orchestrator.agent import load_agent
from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.constants import CAO_AGENT_ID_ENV
from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.base import (
    AgentRuntimeLaunchContext,
    BaseProvider,
    CatalogDiscoveryError,
    ModelDiscoveryCapability,
    ProviderCatalog,
    ProviderModel,
    ProviderRuntimeDescriptor,
    ProviderRuntimePreparation,
    ProviderRuntimeState,
    ProviderRuntimeStateCapability,
)
from cli_agent_orchestrator.providers.runtime_config import get_provider_runtime_config
from cli_agent_orchestrator.services.tool_service import tool_service_for_loaded_agent
from cli_agent_orchestrator.utils.claude_runtime import (
    CLAUDE_RUNTIME_MATERIALIZATION_SCHEMA_VERSION,
    CLAUDE_RUNTIME_STATE_SCHEMA_VERSION,
    build_claude_runtime_materialization,
    claude_login_ok,
    claude_runtime_paths,
    ensure_claude_session_id,
    prepare_agent_claude_runtime,
)
from cli_agent_orchestrator.utils.terminal import wait_for_shell, wait_until_status

logger = logging.getLogger(__name__)
PROVIDER_RUNTIME_STATE_FILENAME = "runtime_state.json"


# Custom exception for provider errors
class ProviderError(Exception):
    """Exception raised for provider-specific errors."""

    pass


# Regex patterns for Claude Code output analysis
ANSI_CODE_PATTERN = r"\x1b\[[0-9;]*m"
RESPONSE_PATTERN = r"⏺(?:\x1b\[[0-9;]*m)*\s+"  # Handle any ANSI codes between marker and text
# Match Claude Code processing spinners:
# - Old format: "✽ Cooking… (esc to interrupt)" / "✶ Thinking… (esc to interrupt)"
# - New format: "✽ Cooking… (6s · ↓ 174 tokens · thinking)"
# - Minimal format: "✻ Orbiting…" (no parenthesized status)
# Common: spinner char + text + ellipsis, optionally followed by parenthesized status
PROCESSING_PATTERN = r"[✶✢✽✻✳·].*\u2026"
# Structural PROCESSING indicator: a spinner line (spinner char + … ) immediately
# before the ──────── separator line that Claude Code draws before the input prompt.
# Requires a known spinner character on the same line as … to avoid false-positives
# from response text or tool outputs that happen to contain … .
# Allows 0–2 blank lines between the spinner and the separator.
# The separator line starts with an ANSI colour code (\x1b[38;5;244m) before the
# box-drawing characters (U+2500), so the pattern skips that prefix explicitly.
#
# Processing: "✻ Skedaddling…\n\n────────\n❯ " → spinner+… before separator → PROCESSING
# Idle/done: "⏺ response text\n────────\n❯ " → no spinner before separator → not PROCESSING
# Stale spinner: "✢ Thinking…" far back in scrollback, current separator has
# no spinner immediately before it → not PROCESSING
THINKING_BEFORE_SEPARATOR_PATTERN = re.compile(
    r"[^\n]*[✶✢✽✻✳·][^\n]*\u2026[^\n]*\n(?:[^\n]*\n){0,2}(?:\x1b\[[0-9;]*m)*\u2500{20,}",
    re.MULTILINE,
)
IDLE_PROMPT_PATTERN = r"[>❯][\s\xa0]"  # Handle both old ">" and new "❯" prompt styles
WAITING_USER_ANSWER_PATTERN = (
    r"↑/↓ to navigate"  # Ink TUI footer shown only while a selection widget is active
)
TRUST_PROMPT_PATTERN = r"Yes, I trust this folder"  # Workspace trust dialog
BYPASS_PROMPT_PATTERN = r"Yes, I accept"  # Bypass permissions confirmation dialog
IDLE_PROMPT_PATTERN_LOG = r"[>❯][\s\xa0]"  # Same pattern for log files
CLAUDE_UPDATE_TIMEOUT_SECONDS = 120.0
CLAUDE_STARTUP_DIAGNOSTIC_MAX_CHARS = 800


def _bounded_startup_diagnostics(output: str) -> str:
    """Return short terminal diagnostics suitable for logs and API errors."""
    clean_output = re.sub(ANSI_CODE_PATTERN, "", output or "").strip()
    if not clean_output:
        return "<no terminal output captured>"
    lines = [line.rstrip() for line in clean_output.splitlines() if line.strip()]
    diagnostic = "\n".join(lines[-20:]).strip()
    if len(diagnostic) > CLAUDE_STARTUP_DIAGNOSTIC_MAX_CHARS:
        diagnostic = "..." + diagnostic[-CLAUDE_STARTUP_DIAGNOSTIC_MAX_CHARS:]
    return diagnostic


class ClaudeRuntimeStateCapability(ProviderRuntimeStateCapability):
    """Claude-owned runtime/session restoration capability."""

    provider_type = ProviderType.CLAUDE_CODE.value

    def discover_current_runtime_state(
        self,
        *,
        terminal_id: str,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState | None:
        """Return the provider-owned Claude session id for this agent.

        CAO launches agent-managed Claude sessions with a provider-owned
        UUID via ``--session-id``. Claude then persists the conversation under
        its normal authenticated user state, and relaunch can use
        ``--resume <session-id>``. This intentionally avoids scraping Claude's
        TUI output. If Claude changes the ``--session-id``/``--resume``
        contract, update this capability and its tests together.
        """
        session_id = ensure_claude_session_id(provider_data_dir)
        return ProviderRuntimeState(
            provider_type=self.provider_type,
            provider_data_dir=provider_data_dir,
            payload={
                "schema_version": CLAUDE_RUNTIME_STATE_SCHEMA_VERSION,
                "session_id": session_id,
            },
        )

    def deserialize_runtime_state(
        self,
        payload: Mapping[str, object],
        *,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState:
        """Validate a durable Claude runtime payload."""
        schema_version = payload.get("schema_version")
        session_id = payload.get("session_id")
        if schema_version != CLAUDE_RUNTIME_STATE_SCHEMA_VERSION:
            raise ValueError("Claude runtime state has unsupported schema_version")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("Claude runtime state requires a non-empty session_id")
        return ProviderRuntimeState(
            provider_type=self.provider_type,
            provider_data_dir=provider_data_dir,
            payload={
                "schema_version": CLAUDE_RUNTIME_STATE_SCHEMA_VERSION,
                "session_id": session_id.strip(),
            },
        )

    def serialize_runtime_state(
        self,
        state: ProviderRuntimeState,
    ) -> Mapping[str, object]:
        """Serialize Claude runtime state as the minimal durable payload."""
        if state.provider_type != self.provider_type:
            raise ValueError("Claude cannot serialize runtime state for another provider")
        return self.deserialize_runtime_state(
            state.payload,
            provider_data_dir=state.provider_data_dir,
        ).payload

    def launch_resume_args(
        self,
        state: ProviderRuntimeState,
        *,
        provider_data_dir: Path,
    ) -> list[str]:
        """Return Claude CLI args that resume the captured session."""
        validated = self.deserialize_runtime_state(
            state.payload, provider_data_dir=provider_data_dir
        )
        return ["--resume", str(validated.payload["session_id"])]

    def load_runtime_state(
        self,
        *,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState | None:
        """Load Claude-owned runtime state from the provider data directory."""
        path = provider_data_dir / PROVIDER_RUNTIME_STATE_FILENAME
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except Exception:
            return None
        if not isinstance(payload, Mapping):
            return None
        return self.deserialize_runtime_state(payload, provider_data_dir=provider_data_dir)

    def save_runtime_state(self, state: ProviderRuntimeState) -> None:
        """Persist Claude-owned runtime state in the provider data directory."""
        payload = self.serialize_runtime_state(state)
        state.provider_data_dir.mkdir(parents=True, exist_ok=True)
        (state.provider_data_dir / PROVIDER_RUNTIME_STATE_FILENAME).write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        )

    def clear_runtime_state(
        self,
        *,
        provider_data_dir: Path,
    ) -> None:
        """Clear Claude-owned runtime state in the provider data directory."""
        try:
            (provider_data_dir / PROVIDER_RUNTIME_STATE_FILENAME).unlink()
        except FileNotFoundError:
            pass


ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_MODELS_TIMEOUT_SECONDS = 10.0
ANTHROPIC_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
CLAUDE_KEYCHAIN_SERVICE = "Claude Code-credentials"
CLAUDE_ROUTED_AUTH_ENV_VARS = (
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)


def _routed_auth_var(environ: Mapping[str, str]) -> str | None:
    """Return the routed-auth env var that is enabled, if any."""
    for name in CLAUDE_ROUTED_AUTH_ENV_VARS:
        value = environ.get(name, "").strip().lower()
        if value and value not in {"0", "false", "no", "off"}:
            return name
    return None


def _read_claude_oauth_token() -> Optional[str]:
    """Return the Claude Code OAuth access token from the macOS keychain.

    Phase 1 supports macOS only. Other platforms get None and the caller
    raises a "not logged in" error.
    """
    import sys

    user = os.environ.get("USER", "").strip()
    return _read_claude_oauth_token_for_user(platform=sys.platform, user=user)


def _read_claude_oauth_token_for_user(*, platform: str, user: str) -> Optional[str]:
    """Return the Claude Code OAuth access token for one OS user."""
    if platform != "darwin":
        return None
    if not user:
        return None
    try:
        proc = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                CLAUDE_KEYCHAIN_SERVICE,
                "-a",
                user,
                "-w",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        blob = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    oauth = blob.get("claudeAiOauth") if isinstance(blob, dict) else None
    if not isinstance(oauth, dict):
        return None
    token = oauth.get("accessToken")
    return token if isinstance(token, str) and token else None


def _build_provider_model(raw: Mapping[str, Any]) -> Optional[ProviderModel]:
    """Map one raw ``/v1/models`` entry to a ``ProviderModel``, or filter it out.

    Filter rule: keep models whose ``id`` is a ``claude-*`` string AND whose
    ``capabilities.thinking.supported`` is ``True``. Everything else (legacy
    Claude 2 family, embedding models, models that don't support extended
    thinking) is dropped — Claude Code cannot drive them.
    """
    model_id = raw.get("id")
    if not isinstance(model_id, str) or not model_id.startswith("claude-"):
        return None
    capabilities = raw.get("capabilities") or {}
    if not isinstance(capabilities, Mapping):
        return None
    thinking = capabilities.get("thinking") or {}
    if not (isinstance(thinking, Mapping) and thinking.get("supported") is True):
        return None
    effort = capabilities.get("effort") or {}
    if not isinstance(effort, Mapping):
        effort = {}
    reasoning_efforts = tuple(
        level
        for level in ANTHROPIC_EFFORT_LEVELS
        if isinstance(effort.get(level), Mapping) and effort[level].get("supported") is True
    )
    display_name = raw.get("display_name")
    max_input_tokens = raw.get("max_input_tokens")
    max_output_tokens = raw.get("max_tokens")
    return ProviderModel(
        id=model_id,
        display_name=str(display_name) if isinstance(display_name, str) else model_id,
        reasoning_efforts=reasoning_efforts,
        thinking_supported=True,
        max_input_tokens=max_input_tokens if isinstance(max_input_tokens, int) else None,
        max_output_tokens=max_output_tokens if isinstance(max_output_tokens, int) else None,
    )


class ClaudeModelDiscoveryCapability(ModelDiscoveryCapability):
    """Discover Claude Code's currently-available models via Anthropic's API.

    Reads the OAuth access token from the macOS keychain (Claude Code's
    auth store) and calls ``GET /v1/models``, keeping only ``claude-*``
    models with extended-thinking support.
    """

    def discover_catalog(self) -> ProviderCatalog:
        routed_auth_var = _routed_auth_var(os.environ)
        if routed_auth_var is not None:
            raise CatalogDiscoveryError(
                f"Claude Code routed auth via {routed_auth_var} is not supported "
                "for model discovery yet."
            )
        token = _read_claude_oauth_token()
        if token is None:
            raise CatalogDiscoveryError(
                "Claude Code credentials not found. Run `claude` and complete the login flow."
            )
        try:
            response = requests.get(
                ANTHROPIC_MODELS_URL,
                headers={
                    "anthropic-version": ANTHROPIC_API_VERSION,
                    "Authorization": f"Bearer {token}",
                },
                timeout=ANTHROPIC_MODELS_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise CatalogDiscoveryError(f"Anthropic /v1/models call failed: {exc}") from exc
        if response.status_code != 200:
            raise CatalogDiscoveryError(
                f"Anthropic /v1/models returned HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CatalogDiscoveryError(f"Anthropic /v1/models returned non-JSON: {exc}") from exc
        data = payload.get("data")
        if not isinstance(data, list):
            raise CatalogDiscoveryError("Anthropic /v1/models response is missing 'data' list")
        models = tuple(
            model
            for model in (_build_provider_model(raw) for raw in data if isinstance(raw, dict))
            if model is not None
        )
        return ProviderCatalog(
            provider_type=ProviderType.CLAUDE_CODE.value,
            models=models,
            discovered_at=datetime.now(tz=timezone.utc),
            source="anthropic-api",
        )


class ClaudeCodeProvider(BaseProvider):
    """Provider for Claude Code CLI tool integration."""

    provider_type = ProviderType.CLAUDE_CODE.value
    interrupt_key = "Escape"
    binary = "claude"

    @classmethod
    def runtime_state_capability(cls) -> ClaudeRuntimeStateCapability:
        """Expose Claude's runtime/session restoration capability."""
        return ClaudeRuntimeStateCapability()

    @classmethod
    def model_discovery_capability(cls) -> ClaudeModelDiscoveryCapability:
        """Expose Claude's runtime model catalog discovery capability."""
        return ClaudeModelDiscoveryCapability()

    @staticmethod
    def prepare_terminal_runtime(
        *,
        terminal_id: str,
        agent_id: str,
        working_directory: str,
        launch_context: Optional[AgentRuntimeLaunchContext] = None,
    ) -> ProviderRuntimePreparation:
        """Prepare Claude-owned agent runtime material."""
        if launch_context is None:
            return ProviderRuntimePreparation()

        provider_data_dir = prepare_agent_claude_runtime(
            launch_context.provider_data_dir,
            terminal_id,
            agent_id,
            working_directory,
        )
        return ProviderRuntimePreparation(
            environment={
                "CAO_CLAUDE_PROVIDER_DATA_DIR": str(provider_data_dir),
            },
            agent_scoped=True,
        )

    @classmethod
    def runtime_fingerprint_contribution(
        cls,
        *,
        launch_context: AgentRuntimeLaunchContext,
    ) -> ProviderRuntimeDescriptor:
        """Describe Claude-owned runtime inputs that require terminal replacement."""
        materialization = build_claude_runtime_materialization(launch_context.agent_id)
        startup_command = cls(
            terminal_id="<fingerprint>",
            session_name=launch_context.session_name,
            window_name=launch_context.window_name,
            agent_id=launch_context.agent_id,
            allowed_tools=launch_context.allowed_tools,
            provider_data_dir=launch_context.provider_data_dir,
            include_runtime_session=False,
        )._build_claude_command()
        return ProviderRuntimeDescriptor(
            schema_version="claude-runtime-descriptor.v1",
            material={
                "claude_runtime_schema_version": CLAUDE_RUNTIME_MATERIALIZATION_SCHEMA_VERSION,
                "claude_runtime_settings": materialization.settings,
                "claude_runtime_plugin_manifest": materialization.plugin_manifest,
                "claude_runtime_skills": materialization.skill_fingerprints,
                "startup_command": startup_command,
                "provider_runtime_config": get_provider_runtime_config(cls.provider_type),
            },
        )

    @classmethod
    def run_update_preflight(cls, *, timeout: float = CLAUDE_UPDATE_TIMEOUT_SECONDS) -> None:
        """Run Claude's updater before launching an agent-managed runtime."""
        # Resolve from the provider's declared binary so the install check and
        # ``/providers`` endpoint share the same authoritative source per
        # ``authoritative-sources-are-referenced-not-copied``.
        claude_bin = shutil.which(cls.binary)
        if not claude_bin:
            raise ProviderError("Claude update preflight failed: claude binary not found in PATH")
        try:
            proc = subprocess.run(
                [claude_bin, "update"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            raise ProviderError(
                "Claude update preflight timed out. "
                f"Output:\n{_bounded_startup_diagnostics(str(output))}"
            ) from exc
        except OSError as exc:
            raise ProviderError(f"Claude update preflight failed to start: {exc}") from exc
        if proc.returncode != 0:
            raise ProviderError(
                "Claude update preflight failed "
                f"(exit {proc.returncode}). Output:\n"
                f"{_bounded_startup_diagnostics(proc.stdout or '')}"
            )

    @staticmethod
    def run_auth_preflight() -> None:
        """Fail fast when Claude cannot use the current user's login state."""
        if not claude_login_ok():
            raise ProviderError(
                "Claude auth preflight failed: Claude Code is not logged in. "
                "Run `claude auth login` first."
            )

    def __init__(
        self,
        terminal_id: str,
        session_name: str,
        window_name: str,
        agent_id: Optional[str] = None,
        allowed_tools: Optional[list] = None,
        *,
        provider_data_dir: Optional[Path | str] = None,
        runtime_resume_args: Optional[list[str]] = None,
        include_runtime_session: bool = True,
    ):
        """Initialize provider state."""
        super().__init__(terminal_id, session_name, window_name, allowed_tools)
        self._initialized = False
        self._agent_id = agent_id
        self._provider_data_dir = None if provider_data_dir is None else Path(provider_data_dir)
        self._runtime_resume_args = list(runtime_resume_args or [])
        self._include_runtime_session = include_runtime_session

    def _build_claude_command(self) -> str:
        """Build Claude Code command with agent if provided.

        Returns properly escaped shell command string that can be safely sent via tmux.
        Uses shlex.join() to handle multiline strings and special characters correctly.
        """
        # --dangerously-skip-permissions: bypass the workspace trust dialog and
        # tool permission prompts. CAO already confirms workspace access during
        # `cao agent start`, so re-prompting each spawned agent
        # (supervisor and worker) is redundant and blocks handoff/assign flows.
        command_parts = ["claude", "--dangerously-skip-permissions"]

        if self._provider_data_dir is not None:
            paths = claude_runtime_paths(self._provider_data_dir)
            command_parts.extend(["--settings", str(paths["settings"])])
            command_parts.extend(["--plugin-dir", str(paths["plugin_dir"])])
            command_parts.append("--strict-mcp-config")

        if self._agent_id is not None:
            try:
                agent = load_agent(self._agent_id)

                if agent.reasoning_effort is not None:
                    command_parts.extend(["--effort", str(agent.reasoning_effort)])

                # Add system prompt - escape newlines to prevent tmux chunking issues
                system_prompt = agent.prompt or ""
                if system_prompt:
                    # Replace actual newlines with \n escape sequences
                    # This prevents tmux send_keys chunking from breaking the command
                    escaped_prompt = system_prompt.replace("\\", "\\\\").replace("\n", "\\n")
                    command_parts.extend(["--append-system-prompt", escaped_prompt])

                # Add MCP config if present.
                # Forward CAO_AGENT_ID so MCP servers (e.g. cao-mcp-server)
                # can identify the current agent for handoff/assign operations.
                # Claude Code does not automatically forward parent shell env vars
                # to MCP subprocesses, so we inject it explicitly via the env field.
                mcp_servers = tool_service_for_loaded_agent(
                    agent,
                    fallback_agent_id=self._agent_id,
                    cli_provider="claude_code",
                ).materialized_mcp_servers_for_agent(self._agent_id)
                if mcp_servers:
                    mcp_config = {}
                    for server_name, server_config in mcp_servers.items():
                        if isinstance(server_config, dict):
                            mcp_config[server_name] = dict(server_config)
                        else:
                            mcp_config[server_name] = cast(Any, server_config).model_dump(
                                exclude_none=True
                            )

                        env = mcp_config[server_name].get("env", {})
                        env[CAO_AGENT_ID_ENV] = self._agent_id
                        mcp_config[server_name]["env"] = env

                    mcp_json = json.dumps({"mcpServers": mcp_config})
                    command_parts.extend(["--mcp-config", mcp_json])

            except Exception as e:
                raise ProviderError(f"Failed to load agent '{self._agent_id}': {e}")

        # Apply tool restrictions via --disallowedTools flags.
        # --dangerously-skip-permissions bypasses prompts but --disallowedTools
        # still prevents the agent from using the blocked tools entirely.
        if self._allowed_tools and "*" not in self._allowed_tools:
            from cli_agent_orchestrator.utils.tool_mapping import get_disallowed_tools

            disallowed = get_disallowed_tools("claude_code", self._allowed_tools)
            for tool in disallowed:
                command_parts.extend(["--disallowedTools", tool])

        if self._runtime_resume_args:
            command_parts.extend(self._runtime_resume_args)
        elif self._provider_data_dir is not None and self._include_runtime_session:
            command_parts.extend(
                ["--session-id", ensure_claude_session_id(self._provider_data_dir)]
            )

        # Use shlex.join() for proper shell escaping of all arguments
        # This correctly handles multiline strings, quotes, and special characters
        claude_cmd = shlex.join(command_parts)

        # When cao-server runs inside a Claude Code session, CLAUDE* env vars
        # leak into spawned tmux panes (via the tmux server's global env).
        # Claude Code detects these and refuses to start ("nested session").
        # Unset all matching vars except CLAUDE_CODE_USE_* and
        # CLAUDE_CODE_SKIP_*_AUTH (needed for provider authentication:
        # Bedrock, Vertex AI, Foundry).
        unset_cmd = (
            "unset $(env | sed -n 's/^\\(CLAUDE[A-Z_]*\\)=.*/\\1/p'"
            " | grep -v -E 'CLAUDE_CODE_USE_(BEDROCK|VERTEX|FOUNDRY)"
            "|CLAUDE_CODE_SKIP_(BEDROCK|VERTEX|FOUNDRY)_AUTH'"
            ") 2>/dev/null"
        )
        return f"{unset_cmd}; {claude_cmd}"

    @staticmethod
    def _ensure_skip_bypass_prompt_setting() -> None:
        """Ensure ``skipDangerousModePermissionPrompt`` is set in settings.

        Claude Code (v2.1.41+) shows a bypass permissions confirmation dialog
        on every launch with ``--dangerously-skip-permissions`` unless
        ``skipDangerousModePermissionPrompt: true`` is persisted in
        ``~/.claude/settings.json``.  CAO already uses the flag intentionally,
        so the confirmation is redundant and blocks initialization.
        """
        settings_path = Path.home() / ".claude" / "settings.json"
        settings: dict = {}
        if settings_path.exists():
            try:
                with open(settings_path) as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        if settings.get("skipDangerousModePermissionPrompt") is True:
            return

        settings["skipDangerousModePermissionPrompt"] = True
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
        logger.info("Set skipDangerousModePermissionPrompt in ~/.claude/settings.json")

    def _handle_startup_prompts(self, timeout: float = 20.0) -> None:
        """Auto-accept startup prompts that may appear before the REPL is ready.

        Claude Code may show up to two prompts during startup:

        1. **Bypass permissions confirmation** (``--dangerously-skip-permissions``)
           – shows "Yes, I accept" as option 2; requires ``Down`` + ``Enter``.
           The settings-based fix (``_ensure_skip_bypass_prompt_setting``) prevents
           this in most cases; this handler is a defensive fallback.
        2. **Workspace trust dialog** – shows "Yes, I trust this folder";
           requires ``Enter``.
        """
        start_time = time.time()
        bypass_accepted = False
        while time.time() - start_time < timeout:
            output = tmux_client.get_history(self.session_name, self.window_name)
            if not output:
                time.sleep(1.0)
                continue

            clean_output = re.sub(ANSI_CODE_PATTERN, "", output)

            # 1) Handle bypass permissions prompt (appears before trust prompt).
            #    Only act once — the text stays in the buffer after dismissal.
            if not bypass_accepted and re.search(BYPASS_PROMPT_PATTERN, clean_output):
                logger.info("Bypass permissions prompt detected, auto-accepting")
                target = f"{self.session_name}:{self.window_name}"
                # Send raw Down arrow escape sequence (-l for literal) to move
                # cursor to "Yes, I accept", then Enter to confirm.
                # tmux send-keys "Down" doesn't work with Claude's Ink TUI.
                subprocess.run(["tmux", "send-keys", "-t", target, "-l", "\x1b[B"], check=False)
                time.sleep(0.5)
                subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], check=False)
                bypass_accepted = True
                time.sleep(1.0)
                continue  # Trust prompt may follow

            # 2) Handle workspace trust prompt
            if re.search(TRUST_PROMPT_PATTERN, clean_output):
                logger.info("Workspace trust prompt detected, auto-accepting")
                session = tmux_client.server.sessions.get(session_name=self.session_name)
                window = (
                    None if session is None else session.windows.get(window_name=self.window_name)
                )
                pane = None if window is None else window.active_pane
                if pane is not None:
                    pane.send_keys("", enter=True)
                return

            # 3) Claude Code fully started — no prompts needed
            if re.search(r"Welcome to|Claude Code v\d+", clean_output):
                logger.info("Claude Code started without prompts")
                return
            if re.search(IDLE_PROMPT_PATTERN, clean_output):
                logger.info("Claude Code idle prompt detected, no prompts needed")
                return

            time.sleep(1.0)
        logger.warning("Startup prompt handler timed out")

    def initialize(self) -> bool:
        """Initialize Claude Code provider by starting claude command."""
        # Wait for shell prompt to appear in the tmux window
        if not wait_for_shell(tmux_client, self.session_name, self.window_name, timeout=10.0):
            raise TimeoutError("Shell initialization timed out after 10 seconds")

        if self._provider_data_dir is None:
            # Prevent bypass permissions dialog from appearing (settings-based fix).
            self._ensure_skip_bypass_prompt_setting()
        else:
            self.run_update_preflight()
            self.run_auth_preflight()

        # Build properly escaped command string
        command = self._build_claude_command()

        # Send Claude Code command using tmux client
        tmux_client.send_keys(self.session_name, self.window_name, command)

        # Handle startup prompts (bypass permissions + workspace trust)
        self._handle_startup_prompts(timeout=20.0)

        # Wait for Claude Code prompt to be ready.
        # Accept both IDLE and COMPLETED — some CLI versions show a startup
        # message that get_status() interprets as a completed response.
        if not wait_until_status(
            self,
            {TerminalStatus.IDLE, TerminalStatus.COMPLETED},
            timeout=30.0,
            polling_interval=1.0,
        ):
            output = tmux_client.get_history(self.session_name, self.window_name)
            raise ProviderError(
                "Claude Code initialization did not reach an idle state. "
                f"Output:\n{_bounded_startup_diagnostics(output)}"
            )

        self._initialized = True
        return True

    def get_status(self, tail_lines: Optional[int] = None) -> TerminalStatus:
        """Get Claude Code status by analyzing terminal output.

        Uses a structural "thinking-before-separator" check as the primary
        PROCESSING indicator, plus position-based fallbacks for edge cases.

        Bug history:
        1. Stale-spinner bug (#104): Old spinner lines persist in the tmux
           scrollback after the agent returns to idle (Claude Code renders
           inline, not alt-screen, inside a tmux pane). Position comparison
           of last spinner vs last idle prompt catches this.

        2. Mid-tool-execution race (this issue): The ❯ input prompt is ALWAYS
           rendered at the bottom of the tmux pane (last position in the
           scrollback buffer). Position-based comparisons against ❯ are
           therefore unreliable — last_idle.start() is always greater than
           any other marker when anything has been typed/executed.

        V3 fix (structural): Check whether any line containing … (U+2026,
        the ellipsis used in all Claude Code thinking/spinner text) appears
        immediately before the ──────── separator line. Claude Code draws
        this separator between the active-execution area and the input prompt.
        When the agent is thinking/processing:
        "· Swirling… (thinking)\n\n──────────────────────\n❯ "
        When idle or completed:
        "some response text\n──────────────────────\n❯ "
        A stale old spinner line far back in scrollback will NOT be
        immediately before the separator, so the structural check is immune
        to the stale-spinner false-positive.

        See: https://github.com/awslabs/cli-agent-orchestrator/issues/104
        """

        output = tmux_client.get_history(self.session_name, self.window_name, tail_lines=tail_lines)

        if not output:
            return TerminalStatus.ERROR

        # PRIMARY PROCESSING check: structural — thinking line immediately
        # before the ──────── separator. Catches ALL spinner variants (including
        # newer "· Swirling…" format) and is immune to the ❯ position problem.
        if THINKING_BEFORE_SEPARATOR_PATTERN.search(output):
            return TerminalStatus.PROCESSING

        # Find the LAST occurrence of each marker for fallback position checks.
        last_processing = None
        for m in re.finditer(PROCESSING_PATTERN, output):
            last_processing = m

        last_idle = None
        for m in re.finditer(IDLE_PROMPT_PATTERN, output):
            last_idle = m

        last_response = None
        for m in re.finditer(RESPONSE_PATTERN, output):
            last_response = m

        # FALLBACK PROCESSING: spinner visible AND no separator follows it yet
        # (early in execution before the separator appears). Position comparison
        # is used here only when no separator is present (safe case).
        if last_processing and not re.search(r"\u2500{20,}", output):
            if last_idle is None or last_processing.start() > last_idle.start():
                return TerminalStatus.PROCESSING

        # Check for waiting user answer via the active Ink selection footer.
        # Exclude startup prompts (trust + bypass), which also render the footer.
        if (
            re.search(WAITING_USER_ANSWER_PATTERN, output)
            and not re.search(TRUST_PROMPT_PATTERN, output)
            and not re.search(BYPASS_PROMPT_PATTERN, output)
        ):
            return TerminalStatus.WAITING_USER_ANSWER

        # COMPLETED: ⏺ response exists AND ❯ prompt is visible (agent finished).
        if last_response and last_idle:
            return TerminalStatus.COMPLETED

        # IDLE: shell prompt visible but no response yet (e.g. just initialized).
        if last_idle:
            return TerminalStatus.IDLE

        return TerminalStatus.ERROR

    def get_idle_pattern_for_log(self) -> str:
        """Return Claude Code IDLE prompt pattern for log files."""
        return IDLE_PROMPT_PATTERN_LOG

    def extract_last_message_from_script(self, script_output: str) -> str:
        """Extract Claude's final response message using ⏺ indicator."""
        # Find all matches of response pattern
        matches = list(re.finditer(RESPONSE_PATTERN, script_output))

        if not matches:
            raise ValueError("No Claude Code response found - no ⏺ pattern detected")

        # Get the last match (final answer)
        last_match = matches[-1]
        start_pos = last_match.end()

        # Extract everything after the last ⏺ until next prompt or separator
        remaining_text = script_output[start_pos:]

        # Split by lines and extract response
        lines = remaining_text.split("\n")
        response_lines = []

        for line in lines:
            # Stop at next > prompt or separator line
            if re.match(r">\s", line) or "────────" in line:
                break

            # Clean the line
            clean_line = line.strip()
            response_lines.append(clean_line)

        if not response_lines or not any(line.strip() for line in response_lines):
            raise ValueError("Empty Claude Code response - no content found after ⏺")

        # Join lines and clean up
        final_answer = "\n".join(response_lines).strip()
        # Remove ANSI codes from the final message
        final_answer = re.sub(ANSI_CODE_PATTERN, "", final_answer)
        return final_answer.strip()

    def exit_cli(self) -> str:
        """Get the command to exit Claude Code."""
        return "/exit"

    def cleanup(self) -> None:
        """Clean up Claude Code provider."""
        self._initialized = False

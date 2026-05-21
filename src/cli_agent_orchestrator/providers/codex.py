"""Codex CLI provider implementation."""

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, cast

from cli_agent_orchestrator.agent import load_agent
from cli_agent_orchestrator.clients.database import get_terminal_metadata
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
from cli_agent_orchestrator.utils.codex_home import (
    CODEX_HOME_MATERIALIZATION_SCHEMA_VERSION,
    build_codex_home_materialization,
    cleanup_codex_home,
    prepare_agent_codex_home,
    prepare_codex_home,
)
from cli_agent_orchestrator.utils.terminal import wait_for_shell, wait_until_status

logger = logging.getLogger(__name__)

# Regex patterns for Codex output analysis
ANSI_CODE_PATTERN = r"\x1b\[[0-9;]*m"
PROVIDER_RUNTIME_STATE_FILENAME = "runtime_state.json"
IDLE_PROMPT_PATTERN = r"(?:❯|›|codex>)"
# Number of lines from the bottom of capture to check for the idle prompt.
# With --no-alt-screen, codex output is inline (scrollback contains history),
# so we can't anchor to \Z. Instead, check the last few lines where the prompt
# and status bar appear.
IDLE_PROMPT_TAIL_LINES = 5
# The idle prompt character ❯ (U+276F) is rendered on-screen by capture-pane
# but is NOT written to the raw output stream captured by pipe-pane.  Instead,
# the TUI footer text "? for shortcuts" is reliably present whenever the TUI
# is active.  This is intentionally permissive — _has_idle_pattern() is a
# lightweight pre-check; the real status decision is made by get_status()
# which uses capture-pane (rendered screen).
IDLE_PROMPT_PATTERN_LOG = r"\? for shortcuts"
# Match assistant response start: "assistant:/codex:/agent:" (label style from synthetic
# test fixtures) or "•" bullet point (real Codex interactive output format).
ASSISTANT_PREFIX_PATTERN = r"^(?:(?:assistant|codex|agent)\s*:|\s*•)"
# Match user input: "You ..." (label style) or "› text" (Codex interactive prompt).
# The "›[^\S\n]*\S" alternative requires a non-whitespace character on the same line
# to distinguish user input ("› what is your role?") from the empty idle prompt ("› ").
# [^\S\n] matches horizontal whitespace only (spaces/tabs), preventing the pattern
# from crossing newline boundaries into subsequent lines.
USER_PREFIX_PATTERN = r"^(?:You\b|›[^\S\n]*\S)"
# Strict idle prompt pattern for extraction: matches empty prompt lines only.
# Distinguishes "› " (idle) from "› user message" (user input with text).
IDLE_PROMPT_STRICT_PATTERN = r"^\s*(?:❯|›|codex>)\s*$"

PROCESSING_PATTERN = r"\b(thinking|working|running|executing|processing|analyzing)\b"
WAITING_PROMPT_PATTERN = r"^(?:Approve|Allow)\b.*\b(?:y/n|yes/no|yes|no)\b"
ERROR_PATTERN = r"^(?:Error:|ERROR:|Traceback \(most recent call last\):|panic:)"

# Codex TUI footer indicators (status bar below the idle prompt).
# Used to detect when the bottom lines contain TUI chrome rather than user input.
# v0.110 and earlier: "? for shortcuts" and "N% context left"
# v0.111+: "model · N% left · path" (PR #13202 restored draft footer hints)
TUI_FOOTER_PATTERN = r"(?:\?\s+for shortcuts|context left|\d+%\s+left)"
# Codex TUI progress spinner: "• Working (0s • esc to interrupt)",
# "• Thinking (2s ...)", "• Starting script creation (10s • esc to interrupt)".
# The prefix text varies but the "(Ns • esc to interrupt)" format is consistent.
# Appears inline with --no-alt-screen when the agent is actively processing.
# Must be checked before COMPLETED to avoid false positives (the • matches
# ASSISTANT_PREFIX_PATTERN and the TUI footer › matches idle prompt).
TUI_PROGRESS_PATTERN = r"•.*\(\d+s\s*•\s*esc to interrupt\)"

# Workspace trust/approval prompt shown when Codex opens a new directory
TRUST_PROMPT_PATTERN = r"allow Codex to work in this folder"
# Codex welcome banner indicating normal startup (no trust prompt)
CODEX_WELCOME_PATTERN = r"OpenAI Codex"
CODEX_UPDATE_TIMEOUT_SECONDS = 120.0
CODEX_STARTUP_DIAGNOSTIC_MAX_CHARS = 800
CODEX_UPDATE_STARTUP_PROMPT_PATTERN = (
    r"(?:codex\s+update|update\s+codex|update\s+available|self[- ]?update|"
    r"please\s+restart\s+codex|restart\s+codex)"
)
CODEX_UNKNOWN_STARTUP_PROMPT_PATTERN = (
    r"(?:press\s+(?:enter|return)\b|would\s+you\s+like|select\s+an\s+option|"
    r"choose\s+an\s+option|continue\?)"
)

# Fatal startup errors that never recover — short-circuit to ERROR before
# the normal status-detection logic runs.
SHELL_COMMAND_NOT_FOUND_PATTERN = (
    r"(?:command not found: codex|codex: command not found|not found: codex)"
)
CODEX_TERM_DUMB_PATTERN = r'TERM is set to "dumb"\. Refusing to start'
CODEX_RUNTIME_STATE_SCHEMA_VERSION = "codex-runtime-state.v1"
CODEX_THREAD_ID_PROBE_PREFIX = "CAOCT_"
CODEX_DEBUG_MODELS_TIMEOUT_SECONDS = 10.0
CODEX_DEBUG_MODELS_SOURCE = "codex-debug-models"


def _compute_tui_footer_cutoff(all_lines: list) -> int:
    """Compute the character position where the TUI footer area starts.

    Scans backward from the last line to find the TUI footer status bar
    (matches TUI_FOOTER_PATTERN), then continues upward to include any
    blank lines and the suggestion hint line (› with text) that appear
    above the status bar as part of the footer area.

    Returns the character position in the joined text (``'\\n'.join(all_lines)``)
    where the footer starts. Returns ``len('\\n'.join(all_lines))`` if no
    footer is found.
    """
    n = len(all_lines)
    footer_start_idx = n

    # Find the status bar line (last TUI_FOOTER_PATTERN match in the bottom area)
    for i in range(n - 1, max(n - IDLE_PROMPT_TAIL_LINES - 1, -1), -1):
        if re.search(TUI_FOOTER_PATTERN, all_lines[i]):
            footer_start_idx = i
            break

    if footer_start_idx == n:
        return len("\n".join(all_lines))

    # Scan upward from the status bar to include blank lines and the
    # suggestion hint (› with text) that are part of the TUI footer chrome.
    for j in range(footer_start_idx - 1, max(footer_start_idx - 4, -1), -1):
        line = all_lines[j]
        if not line.strip():
            footer_start_idx = j
        elif re.match(rf"\s*{IDLE_PROMPT_PATTERN}", line):
            footer_start_idx = j
            break
        else:
            break

    return len("\n".join(all_lines[:footer_start_idx]))


class ProviderError(Exception):
    """Exception raised for provider-specific errors."""

    pass


def _bounded_startup_diagnostics(output: str) -> str:
    """Return short terminal diagnostics suitable for logs and API errors."""
    clean_output = re.sub(ANSI_CODE_PATTERN, "", output or "").strip()
    if not clean_output:
        return "<no terminal output captured>"
    lines = [line.rstrip() for line in clean_output.splitlines() if line.strip()]
    diagnostic = "\n".join(lines[-20:]).strip()
    if len(diagnostic) > CODEX_STARTUP_DIAGNOSTIC_MAX_CHARS:
        diagnostic = "..." + diagnostic[-CODEX_STARTUP_DIAGNOSTIC_MAX_CHARS:]
    return diagnostic


def _detect_codex_update_prompt(output: str) -> bool:
    """Return whether startup output indicates Codex wants an update/restart flow."""
    clean_output = re.sub(ANSI_CODE_PATTERN, "", output or "")
    return bool(re.search(CODEX_UPDATE_STARTUP_PROMPT_PATTERN, clean_output, re.IGNORECASE))


def parse_codex_thread_id_probe_output(output: str, *, nonce: str) -> str | None:
    """Return the nonce-tagged Codex thread id from tmux output, if present."""
    normalized = re.sub(r"(?<=[A-Za-z0-9_.:-])\n[ \t]+(?=[A-Za-z0-9_.:-])", "", output)
    pattern = re.compile(
        rf"{re.escape(CODEX_THREAD_ID_PROBE_PREFIX + nonce)}=" r"([A-Za-z0-9_.:-]{8,})"
    )
    matches = pattern.findall(normalized)
    if not matches:
        return None
    thread_id = matches[-1].strip()
    return thread_id or None


def _build_codex_provider_model(raw: Mapping[str, Any]) -> ProviderModel | None:
    """Map one ``codex debug models`` entry to a picker-visible model."""
    model_id = raw.get("slug")
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    model_id = model_id.strip()
    if raw.get("visibility") != "list":
        return None

    raw_efforts = raw.get("supported_reasoning_levels")
    reasoning_efforts: list[str] = []
    if isinstance(raw_efforts, list):
        for item in raw_efforts:
            if not isinstance(item, Mapping):
                continue
            effort = item.get("effort")
            if isinstance(effort, str) and effort:
                reasoning_efforts.append(effort)

    display_name = raw.get("display_name")
    context_window = raw.get("context_window")
    max_context_window = raw.get("max_context_window")
    max_input_tokens = (
        context_window
        if isinstance(context_window, int)
        else max_context_window if isinstance(max_context_window, int) else None
    )

    return ProviderModel(
        id=model_id,
        display_name=display_name if isinstance(display_name, str) else model_id,
        reasoning_efforts=tuple(reasoning_efforts),
        thinking_supported=bool(reasoning_efforts),
        max_input_tokens=max_input_tokens,
        max_output_tokens=None,
    )


class CodexRuntimeStateCapability(ProviderRuntimeStateCapability):
    """Codex-owned runtime/session restoration capability."""

    provider_type = ProviderType.CODEX.value

    def discover_current_runtime_state(
        self,
        *,
        terminal_id: str,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState | None:
        """Discover the active Codex thread id without sending a model prompt.

        WARNING: this intentionally relies on brittle Codex CLI behavior observed
        in Codex CLI 0.128.0:
        - Codex hooks did not fire for startup, `!` shell commands, or `/clear`
          without a real model prompt.
        - Codex `!` shell commands currently receive `CODEX_THREAD_ID`.
        - The observed `CODEX_THREAD_ID` matches transcript
          `session_meta.payload.id`.
        - Replace this probe when Codex exposes a stable session-discovery API.
        """
        metadata = get_terminal_metadata(terminal_id)
        if metadata is None:
            raise ValueError(f"Terminal '{terminal_id}' not found")

        nonce = uuid.uuid4().hex[:8]
        # Keep the probe line short enough to avoid Codex TUI wrapping the
        # thread id across visual lines; the parser still tolerates wrapping
        # because this discovery path depends on brittle CLI output behavior.
        probe = f'!printf "%s\\n" "{CODEX_THREAD_ID_PROBE_PREFIX}{nonce}=$CODEX_THREAD_ID"'
        tmux_client.send_keys(metadata["tmux_session"], metadata["tmux_window"], probe)

        deadline = time.time() + 5.0
        while time.time() < deadline:
            output = tmux_client.get_history(metadata["tmux_session"], metadata["tmux_window"])
            thread_id = parse_codex_thread_id_probe_output(output, nonce=nonce)
            if thread_id is not None:
                return ProviderRuntimeState(
                    provider_type=self.provider_type,
                    provider_data_dir=provider_data_dir,
                    payload={
                        "schema_version": CODEX_RUNTIME_STATE_SCHEMA_VERSION,
                        "thread_id": thread_id,
                    },
                )
            time.sleep(0.2)
        return None

    def deserialize_runtime_state(
        self,
        payload: Mapping[str, object],
        *,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState:
        """Validate a durable Codex runtime payload."""
        schema_version = payload.get("schema_version")
        thread_id = payload.get("thread_id")
        if schema_version != CODEX_RUNTIME_STATE_SCHEMA_VERSION:
            raise ValueError("Codex runtime state has unsupported schema_version")
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("Codex runtime state requires a non-empty thread_id")
        return ProviderRuntimeState(
            provider_type=self.provider_type,
            provider_data_dir=provider_data_dir,
            payload={
                "schema_version": CODEX_RUNTIME_STATE_SCHEMA_VERSION,
                "thread_id": thread_id.strip(),
            },
        )

    def serialize_runtime_state(
        self,
        state: ProviderRuntimeState,
    ) -> Mapping[str, object]:
        """Serialize Codex runtime state as the minimal durable payload."""
        if state.provider_type != self.provider_type:
            raise ValueError("Codex cannot serialize runtime state for another provider")
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
        """Return Codex CLI args that resume the captured thread."""
        validated = self.deserialize_runtime_state(
            state.payload, provider_data_dir=provider_data_dir
        )
        return ["resume", str(validated.payload["thread_id"])]

    def load_runtime_state(
        self,
        *,
        provider_data_dir: Path,
    ) -> ProviderRuntimeState | None:
        """Load Codex-owned runtime state from the provider data directory."""
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
        """Persist Codex-owned runtime state in the provider data directory."""
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
        """Clear Codex-owned runtime state in the provider data directory."""
        try:
            (provider_data_dir / PROVIDER_RUNTIME_STATE_FILENAME).unlink()
        except FileNotFoundError:
            pass


class CodexModelDiscoveryCapability(ModelDiscoveryCapability):
    """Discover Codex's currently-available models through the Codex CLI."""

    def discover_catalog(self) -> ProviderCatalog:
        codex_bin = shutil.which(CodexProvider.binary)
        if not codex_bin:
            raise CatalogDiscoveryError(
                "Codex CLI is not installed or not on PATH, so its model catalog "
                "cannot be discovered."
            )

        try:
            proc = subprocess.run(
                [codex_bin, "debug", "models"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=CODEX_DEBUG_MODELS_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CatalogDiscoveryError("Codex `debug models` timed out") from exc
        except OSError as exc:
            raise CatalogDiscoveryError(f"Codex `debug models` failed to start: {exc}") from exc

        if proc.returncode != 0:
            output = (proc.stderr or proc.stdout or "").strip()
            raise CatalogDiscoveryError(
                "Codex `debug models` failed "
                f"(exit {proc.returncode}): {output[:200] or '<no output>'}"
            )

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise CatalogDiscoveryError(f"Codex `debug models` returned non-JSON: {exc}") from exc

        if not isinstance(payload, Mapping):
            raise CatalogDiscoveryError("Codex `debug models` response is not an object")
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise CatalogDiscoveryError("Codex `debug models` response is missing 'models' list")

        models = tuple(
            model
            for model in (
                _build_codex_provider_model(raw) for raw in raw_models if isinstance(raw, Mapping)
            )
            if model is not None
        )
        if not models:
            raise CatalogDiscoveryError(
                "Codex `debug models` did not return any picker-visible models"
            )

        return ProviderCatalog(
            provider_type=ProviderType.CODEX.value,
            models=models,
            discovered_at=datetime.now(tz=timezone.utc),
            source=CODEX_DEBUG_MODELS_SOURCE,
        )


class CodexProvider(BaseProvider):
    """Provider for Codex CLI tool integration."""

    provider_type = ProviderType.CODEX.value
    interrupt_key = "Escape"
    binary = "codex"

    @classmethod
    def runtime_state_capability(cls) -> CodexRuntimeStateCapability:
        """Expose Codex's optional runtime/session restoration capability."""
        return CodexRuntimeStateCapability()

    @classmethod
    def model_discovery_capability(cls) -> CodexModelDiscoveryCapability:
        """Expose Codex's runtime model catalog discovery capability."""
        return CodexModelDiscoveryCapability()

    @staticmethod
    def prepare_terminal_runtime(
        *,
        terminal_id: str,
        agent_id: str,
        working_directory: str,
        launch_context: Optional[AgentRuntimeLaunchContext] = None,
    ) -> ProviderRuntimePreparation:
        """Prepare Codex-owned runtime storage and return the tmux environment."""
        workdir = os.path.realpath(working_directory or os.getcwd())
        if launch_context is not None:
            codex_home = prepare_agent_codex_home(
                launch_context.provider_data_dir,
                terminal_id,
                agent_id,
                workdir,
            )
            return ProviderRuntimePreparation(
                environment={"CODEX_HOME": str(codex_home)},
                agent_scoped=True,
            )

        codex_home = prepare_codex_home(terminal_id, agent_id, workdir)
        return ProviderRuntimePreparation(
            environment={"CODEX_HOME": str(codex_home)},
            agent_scoped=False,
        )

    @classmethod
    def runtime_fingerprint_contribution(
        cls,
        *,
        launch_context: AgentRuntimeLaunchContext,
    ) -> ProviderRuntimeDescriptor:
        """Describe Codex-owned runtime inputs that require terminal replacement."""
        workdir = os.path.realpath(launch_context.working_directory or os.getcwd())
        materialization = build_codex_home_materialization(
            launch_context.agent_id,
            workdir,
        )
        startup_command = cls(
            terminal_id="<fingerprint>",
            session_name=launch_context.session_name,
            window_name=launch_context.window_name,
            agent_id=launch_context.agent_id,
            allowed_tools=launch_context.allowed_tools,
        )._build_codex_command()
        return ProviderRuntimeDescriptor(
            schema_version="codex-runtime-descriptor.v1",
            material={
                "codex_home_schema_version": CODEX_HOME_MATERIALIZATION_SCHEMA_VERSION,
                "codex_home_config": materialization.config,
                "codex_home_agents_md": materialization.agents_md,
                "codex_home_skills": materialization.skill_fingerprints,
                "startup_command": startup_command,
                "provider_runtime_config": get_provider_runtime_config(cls.provider_type),
            },
        )

    @classmethod
    def run_update_preflight(cls, *, timeout: float = CODEX_UPDATE_TIMEOUT_SECONDS) -> None:
        """Run Codex's own updater before launching the interactive runtime.

        CAO launches Codex inside managed tmux windows where interactive update
        prompts can block inbox delivery. Running `codex update` outside
        the managed terminal makes routine update prompts happen before the agent
        runtime starts. This depends on the Codex CLI's documented `update`
        subcommand; if that contract changes, fail before creating a misleading
        hanging runtime.
        """
        # Resolve from the provider's declared binary so the install check and
        # ``/providers`` endpoint share the same authoritative source per
        # ``authoritative-sources-are-referenced-not-copied``.
        codex_bin = shutil.which(cls.binary)
        if not codex_bin:
            raise ProviderError("Codex update preflight failed: codex binary not found in PATH")

        env = os.environ.copy()
        # The update is for the installed CLI, not a per-terminal CODEX_HOME.
        env.pop("CODEX_HOME", None)
        try:
            proc = subprocess.run(
                [codex_bin, "update"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            raise ProviderError(
                "Codex update preflight timed out. "
                f"Output:\n{_bounded_startup_diagnostics(str(output))}"
            ) from exc
        except OSError as exc:
            raise ProviderError(f"Codex update preflight failed to start: {exc}") from exc

        if proc.returncode != 0:
            raise ProviderError(
                "Codex update preflight failed "
                f"(exit {proc.returncode}). Output:\n"
                f"{_bounded_startup_diagnostics(proc.stdout or '')}"
            )

    @staticmethod
    def cleanup_terminal_runtime(terminal_id: str) -> None:
        """Clean up volatile raw-terminal Codex runtime storage."""
        cleanup_codex_home(terminal_id)

    def __init__(
        self,
        terminal_id: str,
        session_name: str,
        window_name: str,
        agent_id: Optional[str] = None,
        allowed_tools: Optional[list] = None,
        runtime_resume_args: Optional[list[str]] = None,
    ):
        """Initialize provider state."""
        super().__init__(terminal_id, session_name, window_name, allowed_tools)
        self._initialized = False
        self._agent_id = agent_id
        self._runtime_resume_args = list(runtime_resume_args or [])

    def _build_codex_command(self) -> str:
        """Build Codex command with agent if provided.

        Returns properly escaped shell command string that can be safely sent via tmux.
        Uses codex's -c developer_instructions flag to inject agent system prompts.
        """
        # --yolo (alias for --dangerously-bypass-approvals-and-sandbox):
        # bypass approval prompts and sandboxing. CAO agents run in
        # non-interactive tmux sessions where interactive approval prompts
        # block handoff/assign flows. This mirrors Claude Code's
        # --dangerously-skip-permissions and Gemini CLI's --yolo flags.
        #
        # --disable plugins / apps: Codex's plugin and apps systems load
        # user-level tools (e.g. github@openai-curated registers ~86 tools,
        # ~70K tokens of schema) from ~/.codex/plugins/ regardless of
        # CODEX_HOME. Suppressing these at the feature-flag level is the
        # only reliable off switch; a local `[plugins.*].enabled = false`
        # in config.toml is overwritten by Codex on interactive startup
        # (plugin state is account-authoritative). CAO agents get their
        # tools via MCP servers declared in the agent instead.
        command_parts = [
            "codex",
            "--yolo",
            "--no-alt-screen",
            "--disable",
            "shell_snapshot",
            "--disable",
            "plugins",
            "--disable",
            "apps",
        ]

        if self._agent_id is not None:
            try:
                agent = load_agent(self._agent_id)

                system_prompt = agent.prompt or ""

                # Prepend security constraints for soft enforcement (Codex has no
                # native tool restriction mechanism). Only applied when tool
                # restrictions are active (not unrestricted "*").
                if self._allowed_tools and "*" not in self._allowed_tools:
                    from cli_agent_orchestrator.constants import SECURITY_PROMPT

                    tools_list = ", ".join(self._allowed_tools)
                    tool_constraint = f"\nYou only have access to these tools: {tools_list}\n"
                    system_prompt = SECURITY_PROMPT + tool_constraint + system_prompt

                if system_prompt:
                    # Codex accepts developer_instructions via -c config override.
                    # This is injected as a developer role message before AGENTS.md content.
                    # Escape backslashes, double quotes, and newlines for TOML basic string.
                    # Newlines must become literal \n to prevent tmux send_keys from
                    # splitting the command across multiple lines.
                    escaped_prompt = (
                        system_prompt.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                    )
                    command_parts.extend(["-c", f'developer_instructions="{escaped_prompt}"'])

                # Add MCP servers via -c config overrides (per-session, no global config changes).
                # Each server field is set via dotted path: mcp_servers.<name>.<field>=<value>
                mcp_servers = tool_service_for_loaded_agent(
                    agent,
                    fallback_agent_id=self._agent_id,
                    cli_provider="codex",
                ).materialized_mcp_servers_for_agent(self._agent_id)
                if mcp_servers:
                    for server_name, server_config in mcp_servers.items():
                        prefix = f"mcp_servers.{server_name}"
                        if isinstance(server_config, dict):
                            cfg = server_config
                        else:
                            cfg = cast(Any, server_config).model_dump(exclude_none=True)
                        if "command" in cfg:
                            command_parts.extend(["-c", f'{prefix}.command="{cfg["command"]}"'])
                        if "args" in cfg:
                            args_toml = "[" + ", ".join(f'"{a}"' for a in cfg["args"]) + "]"
                            command_parts.extend(["-c", f"{prefix}.args={args_toml}"])
                        if "env" in cfg and cfg["env"]:
                            for env_key, env_val in cfg["env"].items():
                                if env_key == CAO_AGENT_ID_ENV:
                                    env_val = self._agent_id
                                command_parts.extend(["-c", f'{prefix}.env.{env_key}="{env_val}"'])
                        # Forward CAO_AGENT_ID so MCP servers (e.g. cao-mcp-server)
                        # can identify the current agent for handoff/assign operations.
                        # Codex does not forward env vars to MCP subprocesses by default;
                        # env_vars lists names to inherit from the parent shell environment.
                        env_vars = cfg.get("env_vars", [])
                        if CAO_AGENT_ID_ENV not in env_vars:
                            env_vars = list(env_vars) + [CAO_AGENT_ID_ENV]
                        env_vars_toml = "[" + ", ".join(f'"{v}"' for v in env_vars) + "]"
                        command_parts.extend(["-c", f"{prefix}.env_vars={env_vars_toml}"])
                        # Set a generous tool timeout for MCP calls like handoff, which
                        # create a new terminal, initialize the provider, send a message,
                        # wait for the agent to complete, and extract the output.
                        # Codex defaults to 60s which is too short for multi-step operations.
                        # Value MUST be a TOML float (600.0, not 600) because Codex
                        # deserializes tool_timeout_sec via Option<f64>; a TOML integer
                        # is silently rejected and falls back to the 60s default.
                        if "tool_timeout_sec" not in cfg:
                            command_parts.extend(["-c", f"{prefix}.tool_timeout_sec=600.0"])

            except Exception as e:
                raise ProviderError(f"Failed to load agent '{self._agent_id}': {e}")

        command_parts.extend(self._runtime_resume_args)
        return shlex.join(command_parts)

    def _handle_trust_prompt(self, timeout: float = 20.0) -> None:
        """Auto-accept the workspace trust prompt if it appears.

        Codex shows a folder approval dialog when opening a new directory.
        This sends Enter to accept the default option (allow Codex to work).
        CAO assumes the user trusts the working directory since they confirmed
        workspace access during the launch command.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            output = tmux_client.get_history(self.session_name, self.window_name)
            if not output:
                time.sleep(1.0)
                continue

            # Clean ANSI codes for reliable text matching
            clean_output = re.sub(ANSI_CODE_PATTERN, "", output)

            if _detect_codex_update_prompt(clean_output):
                raise ProviderError(
                    "Codex startup stopped on an update/restart prompt after update preflight. "
                    f"Output:\n{_bounded_startup_diagnostics(clean_output)}"
                )

            if re.search(TRUST_PROMPT_PATTERN, clean_output):
                logger.info("Codex workspace trust prompt detected, auto-accepting")
                session = tmux_client.server.sessions.get(session_name=self.session_name)
                if session is None:
                    logger.warning("Codex trust prompt detected but tmux session was not found")
                    return
                window = session.windows.get(window_name=self.window_name)
                if window is None:
                    logger.warning("Codex trust prompt detected but tmux window was not found")
                    return
                pane = window.active_pane
                if pane:
                    pane.send_keys("", enter=True)
                return

            # Check if Codex has fully started (welcome banner visible)
            if re.search(CODEX_WELCOME_PATTERN, clean_output):
                logger.info("Codex started without trust prompt")
                return

            if re.search(CODEX_UNKNOWN_STARTUP_PROMPT_PATTERN, clean_output, re.IGNORECASE):
                raise ProviderError(
                    "Codex startup stopped on an unsupported interactive prompt. "
                    f"Output:\n{_bounded_startup_diagnostics(clean_output)}"
                )

            time.sleep(1.0)
        logger.warning("Codex trust prompt handler timed out")

    def initialize(self) -> bool:
        """Initialize Codex provider by starting codex command."""
        if not wait_for_shell(tmux_client, self.session_name, self.window_name, timeout=10.0):
            raise TimeoutError("Shell initialization timed out after 10 seconds")

        # Send a warm-up command before launching codex.
        # Codex exits immediately in freshly-created tmux sessions where the shell
        # has not yet processed a full interactive command cycle.
        tmux_client.send_keys(self.session_name, self.window_name, "echo ready")
        time.sleep(2.0)

        self.run_update_preflight()

        # Build command with flags and agent (developer_instructions).
        # --no-alt-screen: run in inline mode so output stays in normal scrollback,
        #   making tmux capture-pane reliable.
        # --disable shell_snapshot: avoid TTY input conflicts (SIGTTIN) in tmux
        #   caused by the shell_snapshot subprocess inheriting stdin.
        command = self._build_codex_command()
        tmux_client.send_keys(self.session_name, self.window_name, command)

        # Handle workspace trust prompt if it appears (new/untrusted directories)
        self._handle_trust_prompt(timeout=20.0)

        if not wait_until_status(
            self,
            {TerminalStatus.IDLE, TerminalStatus.COMPLETED},
            timeout=60.0,
            polling_interval=1.0,
        ):
            output = tmux_client.get_history(self.session_name, self.window_name)
            if _detect_codex_update_prompt(output):
                raise ProviderError(
                    "Codex startup stopped on an update/restart prompt after update preflight. "
                    f"Output:\n{_bounded_startup_diagnostics(output)}"
                )
            raise ProviderError(
                "Codex initialization did not reach an idle state. "
                f"Output:\n{_bounded_startup_diagnostics(output)}"
            )

        self._initialized = True
        return True

    def get_status(self, tail_lines: Optional[int] = None) -> TerminalStatus:
        """Get Codex status by analyzing terminal output."""
        output = tmux_client.get_history(self.session_name, self.window_name, tail_lines=tail_lines)

        if not output:
            return TerminalStatus.ERROR

        clean_output = re.sub(ANSI_CODE_PATTERN, "", output)
        tail_output = "\n".join(clean_output.splitlines()[-25:])

        # Fatal startup errors: codex binary missing, or a non-interactive
        # TERM (e.g. dumb) that codex refuses to start under.
        if re.search(SHELL_COMMAND_NOT_FOUND_PATTERN, clean_output, re.IGNORECASE):
            return TerminalStatus.ERROR
        if re.search(CODEX_TERM_DUMB_PATTERN, clean_output, re.IGNORECASE):
            return TerminalStatus.ERROR

        # Search for user messages, excluding the Codex TUI footer when present.
        # The TUI footer (idle prompt hint like "› Summarize recent commits" +
        # status bar "? for shortcuts / context left") can contain › followed by
        # suggestion text, which USER_PREFIX_PATTERN would incorrectly match as
        # user input, preventing COMPLETED detection.
        # Only apply the cutoff when TUI footer indicators are actually present
        # to avoid over-excluding in short outputs or test fixtures.
        all_lines = clean_output.splitlines()
        tui_footer_detected = any(
            re.search(TUI_FOOTER_PATTERN, line) for line in all_lines[-IDLE_PROMPT_TAIL_LINES:]
        )
        if tui_footer_detected:
            cutoff_pos = _compute_tui_footer_cutoff(all_lines)
        else:
            cutoff_pos = len(clean_output)

        last_user = None
        for match in re.finditer(USER_PREFIX_PATTERN, clean_output, re.IGNORECASE | re.MULTILINE):
            if match.start() < cutoff_pos:
                last_user = match

        output_after_last_user = clean_output[last_user.start() :] if last_user else clean_output
        assistant_after_last_user = bool(
            last_user
            and re.search(
                ASSISTANT_PREFIX_PATTERN,
                output_after_last_user,
                re.IGNORECASE | re.MULTILINE,
            )
        )

        # Check trust prompt early — the trust menu uses › which matches the idle prompt
        # pattern, and PROCESSING_PATTERN matches "running" in "You are running Codex in..."
        if re.search(TRUST_PROMPT_PATTERN, clean_output):
            return TerminalStatus.WAITING_USER_ANSWER

        # Check bottom of captured output for idle prompt.
        # With --no-alt-screen, scrollback contains history so we can't anchor
        # to end-of-string. Instead, check only the last few lines.
        bottom_lines = clean_output.strip().splitlines()[-IDLE_PROMPT_TAIL_LINES:]
        has_idle_prompt_at_end = any(
            re.match(rf"\s*{IDLE_PROMPT_PATTERN}", line, re.IGNORECASE) for line in bottom_lines
        )

        # Only treat ERROR/WAITING prompts as actionable if they appear after the last user message
        # and are not part of an assistant response.
        if last_user is not None:
            if not assistant_after_last_user:
                if re.search(
                    WAITING_PROMPT_PATTERN,
                    output_after_last_user,
                    re.IGNORECASE | re.MULTILINE,
                ):
                    return TerminalStatus.WAITING_USER_ANSWER
                if re.search(
                    ERROR_PATTERN,
                    output_after_last_user,
                    re.IGNORECASE | re.MULTILINE,
                ):
                    return TerminalStatus.ERROR
        else:
            if re.search(WAITING_PROMPT_PATTERN, tail_output, re.IGNORECASE | re.MULTILINE):
                return TerminalStatus.WAITING_USER_ANSWER
            if re.search(ERROR_PATTERN, tail_output, re.IGNORECASE | re.MULTILINE):
                return TerminalStatus.ERROR
        if has_idle_prompt_at_end:
            # Check for TUI progress indicator ("• Working (0s • esc to interrupt)").
            # With --no-alt-screen, the TUI footer (› hint + status bar) is always
            # rendered at the bottom, even during processing. The • in the progress
            # spinner matches ASSISTANT_PREFIX_PATTERN, causing a false COMPLETED.
            # Detect the spinner and return PROCESSING before checking for COMPLETED.
            if re.search(TUI_PROGRESS_PATTERN, tail_output, re.MULTILINE):
                return TerminalStatus.PROCESSING

            # Consider COMPLETED only if we see an assistant marker after the last user message.
            if last_user is not None:
                if re.search(
                    ASSISTANT_PREFIX_PATTERN,
                    clean_output[last_user.start() :],
                    re.IGNORECASE | re.MULTILINE,
                ):
                    return TerminalStatus.COMPLETED

                return TerminalStatus.IDLE

            return TerminalStatus.IDLE

        # If we're not at an idle prompt and we don't see explicit errors/permission prompts,
        # assume the CLI is still producing output.
        return TerminalStatus.PROCESSING

    def get_idle_pattern_for_log(self) -> str:
        """Return Codex IDLE prompt pattern for log files."""
        return IDLE_PROMPT_PATTERN_LOG

    def extract_last_message_from_script(self, script_output: str) -> str:
        """Extract Codex's final response from terminal output.

        Supports two output formats:
        - Label style: "You ...\\nassistant: response\\n❯" (synthetic/test format)
        - Bullet style: "› user message\\n• response\\n›" (real Codex interactive mode)

        Primary approach: find the last user message and extract everything between
        the end of that line and the next empty idle prompt.
        Fallback: use assistant marker based extraction when no user message is found.
        """
        clean_output = re.sub(ANSI_CODE_PATTERN, "", script_output)

        # Primary: find last user message, extract response between it and idle prompt.
        # Exclude the Codex TUI footer from user-message matching when detected.
        all_lines = clean_output.splitlines()
        tui_footer_detected = any(
            re.search(TUI_FOOTER_PATTERN, line) for line in all_lines[-IDLE_PROMPT_TAIL_LINES:]
        )
        if tui_footer_detected:
            cutoff_pos = _compute_tui_footer_cutoff(all_lines)
        else:
            cutoff_pos = len(clean_output)

        user_matches = [
            m
            for m in re.finditer(USER_PREFIX_PATTERN, clean_output, re.IGNORECASE | re.MULTILINE)
            if m.start() < cutoff_pos
        ]

        if user_matches:
            last_user = user_matches[-1]

            # Find the first assistant response marker (• or assistant:) after
            # the user message. This correctly skips multi-line user messages
            # that wrap across several lines in the Codex TUI.
            asst_after_user = re.search(
                ASSISTANT_PREFIX_PATTERN,
                clean_output[last_user.start() :],
                re.IGNORECASE | re.MULTILINE,
            )
            if asst_after_user:
                response_start = last_user.start() + asst_after_user.start()
            else:
                # No assistant marker found; fall back to skipping one line
                user_line_end = clean_output.find("\n", last_user.start())
                if user_line_end == -1:
                    user_line_end = len(clean_output)
                response_start = user_line_end + 1

            # Find extraction boundary: empty idle prompt or TUI footer area.
            # With --no-alt-screen, the TUI footer (› hint + status bar) has no
            # empty idle prompt. Use cutoff_pos as the boundary when TUI is present.
            idle_after = re.search(
                IDLE_PROMPT_STRICT_PATTERN,
                clean_output[response_start:],
                re.MULTILINE,
            )
            if idle_after:
                end_pos = response_start + idle_after.start()
            elif tui_footer_detected:
                end_pos = cutoff_pos
            else:
                end_pos = len(clean_output)

            response_text = clean_output[response_start:end_pos].strip()

            if response_text:
                # Strip "assistant:" prefix if present (label format)
                response_text = re.sub(
                    r"^(?:assistant|codex|agent)\s*:\s*",
                    "",
                    response_text,
                    count=1,
                    flags=re.IGNORECASE,
                )
                return response_text.strip()

        # Fallback: assistant marker based extraction (no user message found).
        matches = list(
            re.finditer(ASSISTANT_PREFIX_PATTERN, clean_output, re.IGNORECASE | re.MULTILINE)
        )

        if not matches:
            raise ValueError("No Codex response found - no assistant marker detected")

        last_match = matches[-1]
        start_pos = last_match.end()

        idle_after = re.search(
            IDLE_PROMPT_STRICT_PATTERN,
            clean_output[start_pos:],
            re.MULTILINE,
        )
        end_pos = start_pos + idle_after.start() if idle_after else len(clean_output)

        final_answer = clean_output[start_pos:end_pos].strip()

        if not final_answer:
            raise ValueError("Empty Codex response - no content found")

        return final_answer

    def exit_cli(self) -> str:
        """Get the command to exit Codex CLI."""
        return "/exit"

    def cleanup(self) -> None:
        """Clean up Codex CLI provider."""
        self._initialized = False

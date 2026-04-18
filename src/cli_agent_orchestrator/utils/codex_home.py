"""Per-terminal Codex home management.

Codex CLI supports selecting its home directory via the `CODEX_HOME` environment variable. By
creating a separate home per CAO terminal we can isolate agent configs, MCP server registrations,
and per-agent instructions (`AGENTS.md`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from cli_agent_orchestrator.constants import CAO_HOME_DIR
from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile


def _format_toml_key(key: str) -> str:
    if key.replace("_", "").isalnum() and key[0].isalpha():
        return key
    return json.dumps(key)


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(v) for v in value) + "]"
    raise TypeError(f"Unsupported TOML value type: {type(value).__name__}")


def _iter_dict_items_stable(d: Dict[str, Any]) -> Iterable[tuple[str, Any]]:
    # Sort for deterministic output (helps tests and diffs).
    for key in sorted(d.keys()):
        yield key, d[key]


def _dump_toml(data: Dict[str, Any]) -> str:
    """Very small TOML writer for the subset we need."""

    lines: list[str] = []

    def emit_table(prefix: list[str], table: Dict[str, Any]) -> None:
        scalar_items: list[tuple[str, Any]] = []
        dict_items: list[tuple[str, Dict[str, Any]]] = []

        for key, value in _iter_dict_items_stable(table):
            if isinstance(value, dict):
                dict_items.append((key, value))
            else:
                scalar_items.append((key, value))

        if prefix:
            header = "[" + ".".join(_format_toml_key(k) for k in prefix) + "]"
            lines.append(header)

        for key, value in scalar_items:
            lines.append(f"{_format_toml_key(key)} = {_format_toml_value(value)}")

        if scalar_items and dict_items:
            lines.append("")

        for idx, (key, child) in enumerate(dict_items):
            emit_table(prefix + [key], child)
            if idx != len(dict_items) - 1:
                lines.append("")

    emit_table([], data)
    return "\n".join(lines).rstrip() + "\n"


def _merge_into(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge updates into base (mutates base)."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_into(base[key], value)  # type: ignore[index]
        else:
            base[key] = value
    return base


def _codex_login_ok(codex_home_dir: Path) -> bool:
    """Best-effort check that Codex CLI is authenticated.

    CAO cannot currently handle interactive authentication flows inside a managed terminal,
    so we fail fast when Codex appears to require login.
    """

    codex_bin = shutil.which("codex")
    if not codex_bin:
        return False

    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home_dir)

    def run_status(args: list[str]) -> Optional[tuple[int, str]]:
        try:
            proc = subprocess.run(
                args,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception:
            return None
        return proc.returncode, (proc.stdout or "")

    def output_indicates_logged_out(output: str) -> bool:
        lowered = output.lower()
        return "not logged" in lowered or "logged out" in lowered or "please log" in lowered

    def output_indicates_command_missing(output: str, command: str) -> bool:
        lowered = output.lower()
        # Various CLIs use different phrasing for unknown subcommands.
        return (
            "unrecognized subcommand" in lowered
            or "unknown command" in lowered
            or "unknown subcommand" in lowered
        ) and command in lowered

    # Codex CLI has changed subcommand naming across versions:
    # - Newer: `codex login status`
    # - Older docs: `codex auth status`
    status_checks = [
        (["login", "status"], "login"),
        (["auth", "status"], "auth"),
    ]

    for subcommand, command_name in status_checks:
        result = run_status([codex_bin, *subcommand])
        if result is None:
            continue
        returncode, output = result
        if returncode == 0 and not output_indicates_logged_out(output):
            return True
        # If this specific command isn't supported, try the next candidate.
        if output_indicates_command_missing(output, command_name):
            continue
        return False

    return False


def prepare_codex_home(
    terminal_id: str,
    agent_profile: str,
    working_directory: str,
    *,
    cao_home_dir: Optional[Path] = None,
    global_codex_home_dir: Optional[Path] = None,
) -> Path:
    """Create a per-terminal Codex home directory and return the CODEX_HOME path."""
    cao_home_dir = CAO_HOME_DIR if cao_home_dir is None else cao_home_dir
    global_codex_home_dir = (
        (Path.home() / ".codex") if global_codex_home_dir is None else global_codex_home_dir
    )

    if not shutil.which("codex"):
        raise ValueError("codex binary not found in PATH")

    terminal_codex_home = cao_home_dir / "codex-homes" / terminal_id / ".codex"
    terminal_codex_home.mkdir(parents=True, exist_ok=True)

    auth_src = global_codex_home_dir / "auth.json"
    if not auth_src.exists():
        raise ValueError(f"Codex auth.json not found at {auth_src}")

    # Copy auth + (optional) config
    shutil.copy2(auth_src, terminal_codex_home / "auth.json")

    if not _codex_login_ok(terminal_codex_home):
        # Best-effort cleanup so we don't accumulate per-terminal homes on failures.
        try:
            shutil.rmtree(terminal_codex_home.parent, ignore_errors=True)
        finally:
            raise ValueError(
                "Codex CLI is not logged in (or requires user interaction). Run `codex auth login` first."
            )

    profile = load_agent_profile(agent_profile)

    # Build a minimal config from scratch — intentionally NOT inheriting from
    # ~/.codex/config.toml. The global config may reference files by relative
    # path (e.g. [agents.*].config_file, profiles.*.instructions_file,
    # mcp_servers.*.cwd) which resolve against CODEX_HOME. Copying the config
    # into a per-terminal CODEX_HOME silently breaks those references. Ship a
    # clean, CAO-controlled config instead; user's custom Codex agents in
    # ~/.codex/ remain untouched and keep working for standalone codex usage.
    base_config: Dict[str, Any] = {
        "projects": {str(Path(working_directory)): {"trust_level": "trusted"}},
    }

    if getattr(profile, "model", None):
        base_config["model"] = profile.model  # type: ignore[attr-defined]

    codex_config = getattr(profile, "codexConfig", None)
    if isinstance(codex_config, dict):
        _merge_into(base_config, codex_config)

    reasoning_effort = getattr(profile, "reasoning_effort", None)
    if reasoning_effort and not (
        isinstance(codex_config, dict) and "model_reasoning_effort" in codex_config
    ):
        base_config["model_reasoning_effort"] = str(reasoning_effort)

    # MCP servers from the agent profile + the mandatory CAO MCP server.
    mcp_servers: Dict[str, Any] = {}
    if isinstance(base_config.get("mcp_servers"), dict):
        mcp_servers = base_config["mcp_servers"]  # type: ignore[assignment]

    profile_mcp = getattr(profile, "mcpServers", None)
    if isinstance(profile_mcp, dict):
        for name, server in profile_mcp.items():
            if isinstance(server, dict):
                entry: Dict[str, Any] = {}
                if "command" in server:
                    entry["command"] = server["command"]
                if "args" in server:
                    entry["args"] = server["args"]
                if "env" in server:
                    entry["env"] = server["env"]
                if "cwd" in server:
                    entry["cwd"] = server["cwd"]
                entry["enabled"] = bool(server.get("enabled", True))
                mcp_servers[name] = entry

    cao_existing = mcp_servers.get("cao-mcp-server")
    cao_entry: Dict[str, Any] = {"command": "cao-mcp-server", "enabled": True}
    if isinstance(cao_existing, dict):
        for key in ("env", "cwd"):
            if key in cao_existing:
                cao_entry[key] = cao_existing[key]
    mcp_servers["cao-mcp-server"] = cao_entry
    base_config["mcp_servers"] = mcp_servers

    (terminal_codex_home / "config.toml").write_text(_dump_toml(base_config))

    # Write AGENTS.md from the profile markdown body
    agents_md = terminal_codex_home / "AGENTS.md"
    agents_md.write_text((profile.system_prompt or "").rstrip() + "\n")  # type: ignore[attr-defined]

    # Also write a tiny marker for debugging/cleanup tooling.
    (terminal_codex_home / ".cao-terminal-id").write_text(f"{terminal_id}\n")

    return terminal_codex_home


def cleanup_codex_home(terminal_id: str, *, cao_home_dir: Optional[Path] = None) -> None:
    """Remove the per-terminal Codex home directory (best-effort)."""
    cao_home_dir = CAO_HOME_DIR if cao_home_dir is None else cao_home_dir
    terminal_dir = cao_home_dir / "codex-homes" / terminal_id
    shutil.rmtree(terminal_dir, ignore_errors=True)

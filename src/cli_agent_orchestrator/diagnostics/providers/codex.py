"""Codex provider diagnostics.

Design goals:
- Usable at runtime (CLI command), producing structured results.
- Usable from opt-in E2E tests.
- Offline mode should avoid billable model calls.
- Online mode requires explicit allow_billing=True.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from cli_agent_orchestrator.clients.database import init_db
from cli_agent_orchestrator.constants import CAO_HOME_DIR
from cli_agent_orchestrator.diagnostics.models import DiagnosticResult, DiagnosticStepResult
from cli_agent_orchestrator.diagnostics.runner import _PROVIDER_RUNNERS
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.manager import provider_manager
from cli_agent_orchestrator.services import session_service, terminal_service
from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile
from cli_agent_orchestrator.utils.codex_home import cleanup_codex_home, prepare_codex_home


def _step(name: str, *, billable: bool = False) -> DiagnosticStepResult:
    return DiagnosticStepResult(name=name, ok=False, billable=billable, duration_ms=0)


def _run_command(
    args: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    timeout_s: float = 15.0,
) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, proc.stdout or ""


def _codex_mcp_list_json(*, codex_home: Path) -> Dict[str, Any]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)

    rc, out = _run_command(["codex", "mcp", "list", "--json"], env=env, timeout_s=20.0)
    if rc != 0:
        raise RuntimeError(out.strip() or f"codex mcp list failed (exit {rc})")
    try:
        return json.loads(out)
    except Exception as e:
        raise RuntimeError(f"Failed to parse codex mcp list JSON: {e}\n{out}")


def _poll_status(
    terminal_id: str,
    *,
    timeout_s: float,
    interval_s: float = 0.5,
) -> List[TerminalStatus]:
    deadline = time.monotonic() + timeout_s
    seen: List[TerminalStatus] = []
    while time.monotonic() < deadline:
        provider = provider_manager.get_provider(terminal_id)
        if provider is None:
            break
        status = provider.get_status()
        if not seen or status != seen[-1]:
            seen.append(status)
        time.sleep(interval_s)
    return seen


def run_codex_diagnostics(
    *,
    provider: str,
    agent_profile: str,
    mode: str,
    allow_billing: bool,
    working_directory: str,
) -> DiagnosticResult:
    result = DiagnosticResult(
        provider=provider,
        agent_profile=agent_profile,
        mode=mode,
        allow_billing=allow_billing,
        ok=False,
        steps=[],
    )

    run_id = uuid.uuid4().hex[:8]
    created_session: Optional[str] = None
    created_terminal_id: Optional[str] = None
    prepared_terminal_id: Optional[str] = None

    try:
        # Step: tmux exists
        step = _step("tmux available")
        start = time.monotonic()
        try:
            if not shutil.which("tmux"):
                raise RuntimeError("tmux not found in PATH")
            step.ok = True
        except Exception as e:
            step.details = str(e)
        finally:
            step.duration_ms = int((time.monotonic() - start) * 1000)
            result.steps.append(step)
        if not step.ok:
            return result.finalize()

        # Step: codex exists
        step = _step("codex available")
        start = time.monotonic()
        try:
            if not shutil.which("codex"):
                raise RuntimeError("codex not found in PATH")
            step.ok = True
        except Exception as e:
            step.details = str(e)
        finally:
            step.duration_ms = int((time.monotonic() - start) * 1000)
            result.steps.append(step)
        if not step.ok:
            return result.finalize()

        # Step: load agent profile
        step = _step("agent profile loads")
        start = time.monotonic()
        profile = None
        try:
            profile = load_agent_profile(agent_profile)
            step.ok = True
            step.data = {"name": profile.name, "description": profile.description}
        except Exception as e:
            step.details = str(e)
        finally:
            step.duration_ms = int((time.monotonic() - start) * 1000)
            result.steps.append(step)
        if not step.ok:
            return result.finalize()

        # Step: prepare per-terminal CODEX_HOME (preflight)
        step = _step("prepare CODEX_HOME (preflight)")
        start = time.monotonic()
        prepared_home: Optional[Path] = None
        prepared_terminal_id = f"diag-{run_id}"
        try:
            workdir = os.path.realpath(working_directory)
            prepared_home = prepare_codex_home(prepared_terminal_id, agent_profile, workdir)

            expected = ["auth.json", "config.toml", "AGENTS.md"]
            missing = [name for name in expected if not (prepared_home / name).exists()]
            if missing:
                raise RuntimeError(f"Missing files in CODEX_HOME: {', '.join(missing)}")

            step.ok = True
            step.data = {"CODEX_HOME": str(prepared_home)}
        except Exception as e:
            step.details = str(e)
        finally:
            step.duration_ms = int((time.monotonic() - start) * 1000)
            result.steps.append(step)
        if not step.ok:
            return result.finalize()

        # Step: codex login status (prepared home)
        step = _step("codex login status (preflight)")
        start = time.monotonic()
        try:
            assert prepared_home is not None
            env = os.environ.copy()
            env["CODEX_HOME"] = str(prepared_home)
            rc, out = _run_command(["codex", "login", "status"], env=env, timeout_s=15.0)
            if rc != 0:
                raise RuntimeError(out.strip() or f"codex login status failed (exit {rc})")
            step.ok = True
        except Exception as e:
            step.details = str(e)
        finally:
            step.duration_ms = int((time.monotonic() - start) * 1000)
            result.steps.append(step)
        if not step.ok:
            return result.finalize()

        # Step: MCP servers visible from prepared home
        step = _step("codex mcp list includes cao-mcp-server (preflight)")
        start = time.monotonic()
        try:
            assert prepared_home is not None
            payload = _codex_mcp_list_json(codex_home=prepared_home)

            # Be permissive about JSON shape; just find the server names.
            server_names: List[str] = []
            if isinstance(payload, dict):
                if "mcp_servers" in payload and isinstance(payload["mcp_servers"], dict):
                    server_names = list(payload["mcp_servers"].keys())
                elif "servers" in payload and isinstance(payload["servers"], list):
                    server_names = [
                        s.get("name", "") for s in payload["servers"] if isinstance(s, dict)
                    ]
            if "cao-mcp-server" not in server_names:
                raise RuntimeError(f"cao-mcp-server not found in codex mcp list: {server_names}")

            step.ok = True
            step.data = {"servers": sorted([n for n in server_names if n])}
        except Exception as e:
            step.details = str(e)
        finally:
            step.duration_ms = int((time.monotonic() - start) * 1000)
            result.steps.append(step)
        if not step.ok:
            return result.finalize()

        # Step: spawn a real CAO codex terminal and ensure wrapper can reach IDLE
        step = _step("spawn codex terminal (idle)")
        start = time.monotonic()
        try:
            init_db()
            session_hint = f"diag-{run_id}"
            terminal = terminal_service.create_terminal(
                provider="codex",
                agent_profile=agent_profile,
                session_name=session_hint,
                new_session=True,
                working_directory=os.path.realpath(working_directory),
            )
            created_session = terminal.session_name
            created_terminal_id = terminal.id

            provider_inst = provider_manager.get_provider(terminal.id)
            if provider_inst is None:
                raise RuntimeError("Provider instance not found after terminal creation")
            status = provider_inst.get_status()
            if status != TerminalStatus.IDLE:
                raise RuntimeError(f"Expected IDLE after initialize, got {status.value}")

            # Verify the provisioned CODEX_HOME is usable for codex subcommands.
            terminal_home = CAO_HOME_DIR / "codex-homes" / terminal.id / ".codex"
            env = os.environ.copy()
            env["CODEX_HOME"] = str(terminal_home)

            rc, out = _run_command(["codex", "login", "status"], env=env, timeout_s=15.0)
            if rc != 0:
                raise RuntimeError(
                    out.strip() or f"codex login status failed for terminal CODEX_HOME (exit {rc})"
                )
            payload = _codex_mcp_list_json(codex_home=terminal_home)
            step.ok = True
            step.data = {"terminal_id": terminal.id, "session": terminal.session_name}
            if isinstance(payload, dict) and "mcp_servers" in payload:
                step.data["mcp_servers"] = sorted(list(payload["mcp_servers"].keys()))  # type: ignore[assignment]
        except Exception as e:
            step.details = str(e)
        finally:
            step.duration_ms = int((time.monotonic() - start) * 1000)
            result.steps.append(step)
        if not step.ok:
            return result.finalize()

        if mode == "online":
            # Step: billable round-trip prompt (observe processing and completion)
            step = _step("billable prompt round-trip", billable=True)
            start = time.monotonic()
            try:
                if not allow_billing:
                    raise RuntimeError("allow_billing is required for online diagnostics")
                assert created_terminal_id is not None
                token = f"CAO_DIAG_OK_{uuid.uuid4().hex[:8]}"

                terminal_service.send_input(
                    created_terminal_id,
                    f'Respond with exactly this token and nothing else: "{token}"',
                )

                statuses = _poll_status(created_terminal_id, timeout_s=45.0, interval_s=0.5)
                saw_processing = any(s == TerminalStatus.PROCESSING for s in statuses)
                if not saw_processing:
                    raise RuntimeError(
                        f"Never observed PROCESSING status. Seen: {[s.value for s in statuses]}"
                    )

                # Wait for completion-ish state
                provider_inst = provider_manager.get_provider(created_terminal_id)
                if provider_inst is None:
                    raise RuntimeError("Provider instance missing during online poll")

                # Try to extract the last message
                output = terminal_service.get_output(
                    created_terminal_id, mode=terminal_service.OutputMode.LAST
                )
                if token not in output:
                    raise RuntimeError(
                        f"Expected token not found in output. Output was: {output!r}"
                    )

                step.ok = True
                step.data = {"token": token, "statuses": [s.value for s in statuses]}
            except Exception as e:
                step.details = str(e)
            finally:
                step.duration_ms = int((time.monotonic() - start) * 1000)
                result.steps.append(step)

        return result.finalize()

    finally:
        # Cleanup: per-terminal preflight home.
        if prepared_terminal_id:
            try:
                cleanup_codex_home(prepared_terminal_id)
            except Exception:
                pass

        # Cleanup: codex terminal (session cleanup also cleans per-terminal CODEX_HOME).
        if created_session:
            try:
                session_service.delete_session(created_session)
            except Exception:
                # Best-effort: attempt terminal cleanup and directory cleanup.
                if created_terminal_id:
                    try:
                        terminal_service.delete_terminal(created_terminal_id)
                    except Exception:
                        pass
                if created_terminal_id:
                    try:
                        cleanup_codex_home(created_terminal_id)
                    except Exception:
                        pass


_PROVIDER_RUNNERS["codex"] = run_codex_diagnostics

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cli_agent_orchestrator.agent import AGENTS_ROOT, Agent, write_agent
from cli_agent_orchestrator.diagnostics.runner import run_provider_diagnostics


@pytest.mark.e2e
def test_codex_diagnostics_offline_smoke(tmp_path: Path):
    """Opt-in: runs real Codex + tmux and verifies CODEX_HOME wiring.

    Skipped by default because it depends on real user auth and local provider binaries.
    """

    if os.environ.get("CAO_E2E") != "1":
        pytest.skip("Set CAO_E2E=1 to run provider E2E diagnostics")

    if shutil.which("tmux") is None:
        pytest.skip("tmux not available")
    if shutil.which("codex") is None:
        pytest.skip("codex not available")

    # Require user to already be logged in.
    rc = subprocess.run(
        ["codex", "login", "status"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode
    if rc != 0:
        pytest.skip("codex not logged in (run `codex login` first)")

    agent_name = f"e2e_codex_diag_{os.getpid()}"
    write_agent(
        Agent(
            id=agent_name,
            display_name=agent_name,
            description="Codex diagnostics E2E agent",
            cli_provider="codex",
            workdir=os.path.realpath(str(tmp_path)),
            session_name=agent_name,
            prompt=f"E2E agent marker: {agent_name}\n",
            mcp_servers={"e2e-echo": {"command": "echo", "args": ["hello"]}},
        )
    )

    try:
        result = run_provider_diagnostics(
            provider="codex",
            agent_id=agent_name,
            mode="offline",
            allow_billing=False,
            working_directory=os.path.realpath(str(tmp_path)),
        )
        assert result.ok, result.model_dump()
    finally:
        shutil.rmtree(AGENTS_ROOT / agent_name, ignore_errors=True)

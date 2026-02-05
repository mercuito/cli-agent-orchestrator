from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest


def test_run_provider_diagnostics_requires_allow_billing_for_online():
    from cli_agent_orchestrator.diagnostics.runner import run_provider_diagnostics

    with pytest.raises(ValueError, match="allow_billing"):
        run_provider_diagnostics(
            provider="codex",
            agent_profile="codex_developer",
            mode="online",
            allow_billing=False,
            working_directory=".",
        )


def test_run_provider_diagnostics_rejects_unknown_provider():
    from cli_agent_orchestrator.diagnostics.runner import run_provider_diagnostics

    with pytest.raises(ValueError, match="provider"):
        run_provider_diagnostics(
            provider="unknown",
            agent_profile="x",
            mode="offline",
            allow_billing=False,
            working_directory=".",
        )


def test_run_provider_diagnostics_dispatches_to_provider_runner():
    from cli_agent_orchestrator.diagnostics.models import DiagnosticResult, DiagnosticStepResult
    from cli_agent_orchestrator.diagnostics.runner import run_provider_diagnostics

    fake = DiagnosticResult(
        provider="codex",
        agent_profile="codex_developer",
        mode="offline",
        allow_billing=False,
        ok=True,
        steps=[DiagnosticStepResult(name="x", ok=True, billable=False)],
    )

    with patch(
        "cli_agent_orchestrator.diagnostics.runner._PROVIDER_RUNNERS",
        {"codex": lambda **kwargs: fake},
    ):
        result = run_provider_diagnostics(
            provider="codex",
            agent_profile="codex_developer",
            mode="offline",
            allow_billing=False,
            working_directory=".",
        )

    assert result is fake


def test_run_provider_diagnostics_passes_through_common_args():
    from cli_agent_orchestrator.diagnostics.models import DiagnosticResult
    from cli_agent_orchestrator.diagnostics.runner import run_provider_diagnostics

    captured = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return DiagnosticResult(
            provider=kwargs["provider"],
            agent_profile=kwargs["agent_profile"],
            mode=kwargs["mode"],
            allow_billing=kwargs["allow_billing"],
            ok=True,
            steps=[],
        )

    with patch(
        "cli_agent_orchestrator.diagnostics.runner._PROVIDER_RUNNERS",
        {"codex": fake_runner},
    ):
        run_provider_diagnostics(
            provider="codex",
            agent_profile="codex_developer",
            mode="offline",
            allow_billing=False,
            working_directory="/tmp",
        )

    assert captured["provider"] == "codex"
    assert captured["agent_profile"] == "codex_developer"
    assert captured["mode"] == "offline"
    assert captured["allow_billing"] is False
    assert captured["working_directory"] == "/tmp"

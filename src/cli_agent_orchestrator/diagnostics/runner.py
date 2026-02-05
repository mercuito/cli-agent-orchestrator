"""Diagnostics runner and provider dispatch."""

from __future__ import annotations

from typing import Callable, Dict

from cli_agent_orchestrator.diagnostics.models import DiagnosticResult


def _not_implemented(**kwargs) -> DiagnosticResult:
    provider = kwargs.get("provider", "unknown")
    agent_profile = kwargs.get("agent_profile", "unknown")
    mode = kwargs.get("mode", "offline")
    allow_billing = bool(kwargs.get("allow_billing", False))
    return DiagnosticResult(
        provider=provider,
        agent_profile=agent_profile,
        mode=mode,
        allow_billing=allow_billing,
        ok=False,
        steps=[],
    ).finalize()


# Provider runners are registered here so both CLI and tests can dispatch consistently.
_PROVIDER_RUNNERS: Dict[str, Callable[..., DiagnosticResult]] = {
    "codex": _not_implemented,  # replaced in providers/codex.py import side-effect
}


def run_provider_diagnostics(
    *,
    provider: str,
    agent_profile: str,
    mode: str = "offline",
    allow_billing: bool = False,
    working_directory: str = ".",
) -> DiagnosticResult:
    if mode not in {"offline", "online"}:
        raise ValueError("mode must be 'offline' or 'online'")
    if mode == "online" and not allow_billing:
        raise ValueError("mode='online' requires allow_billing=True")

    runner = _PROVIDER_RUNNERS.get(provider)
    if runner is None:
        raise ValueError(f"Unknown provider '{provider}'")

    return runner(
        provider=provider,
        agent_profile=agent_profile,
        mode=mode,
        allow_billing=allow_billing,
        working_directory=working_directory,
    )


# Import provider modules so they can register their runner(s).
try:
    from cli_agent_orchestrator.diagnostics.providers import codex as _codex  # noqa: F401
except Exception:
    # Diagnostics should remain importable even if optional provider deps are missing.
    pass

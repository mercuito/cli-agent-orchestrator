"""Provider diagnostics framework.

Diagnostics are intended to be runnable:
- at runtime (as a CLI command),
- and as opt-in E2E tests.
"""

from cli_agent_orchestrator.diagnostics.runner import run_provider_diagnostics

__all__ = ["run_provider_diagnostics"]

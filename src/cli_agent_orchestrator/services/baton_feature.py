"""Feature exposure controls for the experimental baton system."""

from __future__ import annotations

from cli_agent_orchestrator.features import env_enabled


def is_baton_enabled() -> bool:
    """Whether the experimental local baton feature is exposed on public surfaces."""

    return env_enabled("CAO_BATON_ENABLED", default=False)


BATON_MCP_TOOL_NAMES = {
    "create_baton",
    "pass_baton",
    "return_baton",
    "complete_baton",
    "block_baton",
    "get_my_batons",
    "get_baton",
}

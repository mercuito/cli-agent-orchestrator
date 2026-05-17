"""Resolve which cao-mcp-server tools an agent is allowed to call."""

from __future__ import annotations

from typing import List, Optional

from cli_agent_orchestrator.agent import Agent


def resolve_cao_tool_allowlist(agent: Agent) -> Optional[List[str]]:
    """Return the allowlist for an agent, or ``None`` if unconfigured."""
    if agent.cao_tools is not None:
        return list(agent.cao_tools)

    return None

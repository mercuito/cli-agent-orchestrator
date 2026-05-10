"""Resolve which cao-mcp-server tools an agent is allowed to call.

Lookup order:
  1. ``profile.caoTools`` — explicit per-profile allowlist (wins if set,
     including the empty list which means "deny all cao-mcp-server tools").
  2. ``None`` — nothing configured. Callers decide whether ``None`` means
     "no restriction" (permissive) or "deny everything" (strict). During
     the rollout of MCP tool filtering, callers will treat ``None`` as
     permissive for backward compatibility.

The distinction between ``None`` (not configured) and ``[]`` (explicitly
empty) is load-bearing — do not collapse them.
"""

from __future__ import annotations

from typing import List, Optional

from cli_agent_orchestrator.models.agent_profile import AgentProfile

def resolve_cao_tool_allowlist(profile: AgentProfile) -> Optional[List[str]]:
    """Return the allowlist for an agent, or ``None`` if unconfigured."""
    if profile.caoTools is not None:
        return list(profile.caoTools)

    return None

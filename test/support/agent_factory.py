"""Test helpers for constructing cutover Agent values."""

from __future__ import annotations

from typing import Any, Optional

from cli_agent_orchestrator.agent import Agent as CaoAgent


def make_agent(
    *,
    name: str = "developer",
    description: Optional[str] = None,
    prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    cli_provider: str = "codex",
    mcp_servers: Optional[dict[str, Any]] = None,
    runtime_capabilities: Optional[list[str]] = None,
    cao_tools: Optional[list[str]] = None,
    tools: Optional[list[str]] = None,
    tool_aliases: Optional[dict[str, str]] = None,
    tools_settings: Optional[dict[str, Any]] = None,
    hooks: Optional[dict[str, Any]] = None,
    model: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    **_: Any,
) -> CaoAgent:
    body = system_prompt if system_prompt is not None else prompt
    return CaoAgent(
        id=name,
        display_name=description or name,
        description=description,
        cli_provider=cli_provider,
        workdir="/tmp",
        session_name=name,
        prompt=body or "",
        model=model,
        reasoning_effort=reasoning_effort,
        mcp_servers=mcp_servers or {},
        tools=tuple(tools or ()),
        tool_aliases=tool_aliases or {},
        tools_settings=tools_settings or {},
        cao_tools=None if cao_tools is None else tuple(cao_tools),
        runtime_capabilities=(
            None if runtime_capabilities is None else tuple(runtime_capabilities)
        ),
        hooks=hooks or {},
    )


Agent = make_agent

"""Test helpers for constructing cutover Agent values."""

from __future__ import annotations

from typing import Any, Optional

import frontmatter

from cli_agent_orchestrator.agent import Agent as CaoAgent


def make_agent(
    *,
    name: str = "developer",
    description: Optional[str] = None,
    prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    mcpServers: Optional[dict[str, Any]] = None,
    runtimeCapabilities: Optional[list[str]] = None,
    caoTools: Optional[list[str]] = None,
    tools: Optional[list[str]] = None,
    toolAliases: Optional[dict[str, str]] = None,
    toolsSettings: Optional[dict[str, Any]] = None,
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
        cli_provider="codex",
        workdir="/tmp",
        session_name=name,
        prompt=body or "",
        model=model,
        reasoning_effort=reasoning_effort,
        mcp_servers=mcpServers or {},
        tools=tuple(tools or ()),
        tool_aliases=toolAliases or {},
        tools_settings=toolsSettings or {},
        cao_tools=None if caoTools is None else tuple(caoTools),
        runtime_capabilities=(
            None if runtimeCapabilities is None else tuple(runtimeCapabilities)
        ),
        hooks=hooks or {},
    )


Agent = make_agent


def parse_agent_id_text(resolved_text: str, profile_name: str) -> CaoAgent:
    post = frontmatter.loads(resolved_text)
    metadata = post.metadata
    return make_agent(
        name=str(metadata.get("name") or profile_name),
        description=metadata.get("description"),
        prompt=post.content or metadata.get("prompt"),
        mcpServers=metadata.get("mcpServers"),
        runtimeCapabilities=metadata.get("runtimeCapabilities"),
        caoTools=metadata.get("caoTools"),
        tools=metadata.get("tools"),
        toolAliases=metadata.get("toolAliases"),
        toolsSettings=metadata.get("toolsSettings"),
        hooks=metadata.get("hooks"),
        model=metadata.get("model"),
    )

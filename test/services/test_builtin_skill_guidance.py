"""Tests for role-aware guidance in bundled CAO skills."""

from __future__ import annotations

from importlib import resources


def _skill_body(skill_name: str) -> str:
    return (
        resources.files("cli_agent_orchestrator.skills")
        .joinpath(skill_name, "SKILL.md")
        .read_text()
    )


def test_supervisor_protocols_do_not_promise_hidden_tools():
    body = _skill_body("cao-supervisor-protocols")

    assert "Only use CAO MCP tools that are visible in your current tool list" in body
    assert "When granted by `cao-mcp-server`" in body
    assert "From `cao-mcp-server`, supervisors orchestrate work with" not in body


def test_worker_protocols_do_not_promise_hidden_callback_or_baton_tools():
    body = _skill_body("cao-worker-protocols")

    assert "Only use CAO MCP tools that are visible in your current tool list" in body
    assert "If `send_message` is available" in body
    assert "Use baton tools this way when they are available" in body

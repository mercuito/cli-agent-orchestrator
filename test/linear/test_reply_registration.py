"""Tests for Linear inbox reply handler registration."""

from __future__ import annotations

import importlib

import cli_agent_orchestrator.linear as linear_package
from cli_agent_orchestrator.inbox.source_registry import can_reply
from cli_agent_orchestrator.inbox import source_registry


def test_linear_package_import_registers_provider_conversation_reply_handler():
    source_registry._reply_handlers.pop("provider_conversation", None)

    importlib.reload(linear_package)

    assert can_reply("provider_conversation")

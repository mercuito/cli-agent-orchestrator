"""Integration tests for the GET /providers endpoint."""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.providers.claude_code import ClaudeCodeProvider
from cli_agent_orchestrator.providers.codex import CodexProvider


def test_list_providers_returns_one_entry_per_provider_type(client, monkeypatch):
    """Every ``ProviderType`` value surfaces exactly once on the endpoint."""
    monkeypatch.setattr(
        "cli_agent_orchestrator.providers.manager.shutil.which",
        lambda _binary: None,
    )

    response = client.get("/providers")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    names = [entry["name"] for entry in body]
    assert sorted(names) == sorted(provider.value for provider in ProviderType)


def test_list_providers_install_status_follows_shutil_which(client, monkeypatch):
    """The ``installed`` flag flips with ``shutil.which`` resolution."""
    installed_binaries = {ClaudeCodeProvider.binary, CodexProvider.binary}

    def fake_which(binary: str) -> str | None:
        return f"/usr/local/bin/{binary}" if binary in installed_binaries else None

    monkeypatch.setattr(
        "cli_agent_orchestrator.providers.manager.shutil.which",
        fake_which,
    )

    response = client.get("/providers")

    by_name = {entry["name"]: entry for entry in response.json()}
    assert by_name[ProviderType.CLAUDE_CODE.value]["installed"] is True
    assert by_name[ProviderType.CODEX.value]["installed"] is True
    assert by_name[ProviderType.Q_CLI.value]["installed"] is False


def test_list_providers_capability_fields_match_provider_declarations(client, monkeypatch):
    """Capability fields surface what each provider class declares — no parallel source."""
    monkeypatch.setattr(
        "cli_agent_orchestrator.providers.manager.shutil.which",
        lambda _binary: None,
    )

    response = client.get("/providers")

    by_name = {entry["name"]: entry for entry in response.json()}
    claude_entry = by_name[ProviderType.CLAUDE_CODE.value]
    assert claude_entry["supported_reasoning_efforts"] == list(
        ClaudeCodeProvider.supported_reasoning_efforts()
    )
    assert claude_entry["suggested_models"] == list(ClaudeCodeProvider.suggested_models())
    assert claude_entry["binary"] == ClaudeCodeProvider.binary

    codex_entry = by_name[ProviderType.CODEX.value]
    assert codex_entry["supported_reasoning_efforts"] is None
    assert codex_entry["suggested_models"] is None
    assert codex_entry["binary"] == CodexProvider.binary

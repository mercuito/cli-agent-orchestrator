"""Integration tests for the GET /providers endpoint."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.providers.claude_code import ClaudeCodeProvider
from cli_agent_orchestrator.providers.codex import CodexProvider

FIXTURE_PATH = (
    Path(__file__).parents[1] / "providers" / "fixtures" / "anthropic_v1_models_response.json"
)
CODEX_FIXTURE_PATH = (
    Path(__file__).parents[1] / "providers" / "fixtures" / "codex_debug_models_response.json"
)


def _load_models_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _load_codex_models_fixture_text() -> str:
    return CODEX_FIXTURE_PATH.read_text()


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


def test_list_providers_catalog_flag_matches_provider_capability(client, monkeypatch):
    """Catalog availability is derived from the provider's opt-in capability."""
    monkeypatch.setattr(
        "cli_agent_orchestrator.providers.manager.shutil.which",
        lambda _binary: None,
    )

    response = client.get("/providers")

    by_name = {entry["name"]: entry for entry in response.json()}
    claude_entry = by_name[ProviderType.CLAUDE_CODE.value]
    assert claude_entry["model_catalog_available"] is True
    assert claude_entry["binary"] == ClaudeCodeProvider.binary

    codex_entry = by_name[ProviderType.CODEX.value]
    assert codex_entry["model_catalog_available"] is True


def test_get_provider_catalog_returns_live_discovery_shape(client, monkeypatch):
    """The catalog endpoint exercises Claude's discovery capability."""
    monkeypatch.setattr(
        "cli_agent_orchestrator.providers.claude_code._read_claude_oauth_token",
        lambda: "oauth-test-token",
    )
    response_stub = MagicMock(status_code=200)
    response_stub.json.return_value = _load_models_fixture()
    monkeypatch.setattr(
        "cli_agent_orchestrator.providers.claude_code.requests.get",
        lambda *args, **kwargs: response_stub,
    )

    response = client.get(f"/providers/{ProviderType.CLAUDE_CODE.value}/catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["provider_type"] == ProviderType.CLAUDE_CODE.value
    assert body["source"] == "anthropic-api"
    assert isinstance(body["discovered_at"], str)
    assert body["models"]
    for model in body["models"]:
        assert model["id"].startswith("claude-")
        assert model["thinking_supported"] is True
        assert isinstance(model["reasoning_efforts"], list)
        assert set(model) == {
            "id",
            "display_name",
            "reasoning_efforts",
            "thinking_supported",
            "max_input_tokens",
            "max_output_tokens",
        }


def test_get_codex_provider_catalog_uses_cli_discovery_shape(client, monkeypatch):
    """Codex catalog endpoint exercises Codex's CLI-owned debug model surface."""
    monkeypatch.setattr(
        "cli_agent_orchestrator.providers.codex.shutil.which",
        lambda _binary: "/bin/codex",
    )
    proc = MagicMock(returncode=0, stdout=_load_codex_models_fixture_text(), stderr="")
    monkeypatch.setattr(
        "cli_agent_orchestrator.providers.codex.subprocess.run",
        lambda *args, **kwargs: proc,
    )

    response = client.get(f"/providers/{ProviderType.CODEX.value}/catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["provider_type"] == ProviderType.CODEX.value
    assert body["source"] == "codex-debug-models"
    assert [model["id"] for model in body["models"]] == ["test-frontier", "test-cli-only"]
    assert body["models"][1]["reasoning_efforts"] == ["high"]


def test_get_provider_catalog_returns_503_when_discovery_fails(client, monkeypatch):
    """Discovery errors surface as actionable service-unavailable responses."""
    monkeypatch.setattr(
        "cli_agent_orchestrator.providers.claude_code._read_claude_oauth_token",
        lambda: None,
    )

    response = client.get(f"/providers/{ProviderType.CLAUDE_CODE.value}/catalog")

    assert response.status_code == 503
    assert "credentials" in response.json()["detail"].lower()


def test_get_provider_catalog_returns_404_for_unknown_provider(client):
    """Unknown provider types remain a 404."""
    response = client.get("/providers/not_a_provider/catalog")

    assert response.status_code == 404
    assert "Unknown provider type" in response.json()["detail"]


def test_get_provider_catalog_returns_404_without_capability(client):
    """Registered providers opt in; no capability means no catalog surface."""
    response = client.get(f"/providers/{ProviderType.Q_CLI.value}/catalog")

    assert response.status_code == 404
    assert "no model-discovery capability" in response.json()["detail"]

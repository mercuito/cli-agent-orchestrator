"""Tests for Claude Code's model catalog discovery capability."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.providers.base import (
    CatalogDiscoveryError,
    ModelDiscoveryCapability,
    ProviderCatalog,
    ProviderModel,
)
from cli_agent_orchestrator.providers.claude_code import (
    ClaudeCodeProvider,
    ClaudeModelDiscoveryCapability,
    _build_provider_model,
    _read_claude_oauth_token,
    _routed_auth_var,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "anthropic_v1_models_response.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _is_stale_claude_oauth_error(error: CatalogDiscoveryError) -> bool:
    """Return True when Claude Code's cached access token was rejected."""
    message = str(error).lower()
    return "anthropic /v1/models returned http 401" in message and (
        "authentication" in message or "credentials" in message
    )


class TestProviderModelBuilder:
    """Tests for the per-entry filter/mapping logic."""

    def _claude_entry(self, **overrides) -> dict:
        base = {
            "type": "model",
            "id": "claude-capable-test",
            "display_name": "Claude Capable Test",
            "max_input_tokens": 1_000_000,
            "max_tokens": 128_000,
            "capabilities": {
                "thinking": {"supported": True},
                "effort": {
                    "supported": True,
                    "low": {"supported": True},
                    "medium": {"supported": True},
                    "high": {"supported": True},
                    "xhigh": {"supported": False},
                    "max": {"supported": True},
                },
            },
        }
        base.update(overrides)
        return base

    def test_non_claude_prefix_is_filtered_out(self):
        # Given
        raw = {"id": "text-embedding-3-small", "capabilities": {"thinking": {"supported": True}}}

        # When
        result = _build_provider_model(raw)

        # Then
        assert result is None

    def test_thinking_unsupported_is_filtered_out(self):
        # Given
        raw = self._claude_entry(
            id="claude-legacy-test",
            capabilities={"thinking": {"supported": False}, "effort": {}},
        )

        # When
        result = _build_provider_model(raw)

        # Then
        assert result is None

    def test_effort_levels_extracted_per_model(self):
        # Given
        raw = self._claude_entry()

        # When
        result = _build_provider_model(raw)

        # Then
        assert result is not None
        assert result.id == "claude-capable-test"
        assert result.reasoning_efforts == ("low", "medium", "high", "max")
        assert result.thinking_supported is True
        assert result.max_input_tokens == 1_000_000
        assert result.max_output_tokens == 128_000

    def test_thinking_model_without_effort_returns_empty_efforts(self):
        # Given — a thinking-supporting model with no effort sub-flags enabled
        raw = self._claude_entry(
            capabilities={
                "thinking": {"supported": True},
                "effort": {
                    "supported": False,
                    "low": {"supported": False},
                    "medium": {"supported": False},
                    "high": {"supported": False},
                    "xhigh": {"supported": False},
                    "max": {"supported": False},
                },
            },
        )

        # When
        result = _build_provider_model(raw)

        # Then — kept, with empty effort tuple
        assert result is not None
        assert result.reasoning_efforts == ()

    def test_real_response_fixture_produces_valid_models(self):
        # Given — recorded /v1/models response from a real account
        fixture = _load_fixture()

        # When
        models = [
            model
            for model in (_build_provider_model(item) for item in fixture["data"])
            if model is not None
        ]

        # Then
        assert len(models) >= 1
        assert any("max" in model.reasoning_efforts for model in models)
        for model in models:
            assert model.id.startswith("claude-")
            assert model.thinking_supported is True


class TestDiscoverCatalog:
    """End-to-end tests for `ClaudeModelDiscoveryCapability.discover_catalog`."""

    @patch("cli_agent_orchestrator.providers.claude_code._read_claude_oauth_token")
    def test_missing_credentials_raises_catalog_discovery_error(self, mock_token):
        # Given
        mock_token.return_value = None
        capability = ClaudeModelDiscoveryCapability()

        # When / Then
        with pytest.raises(CatalogDiscoveryError) as exc_info:
            capability.discover_catalog()
        assert "credentials" in str(exc_info.value).lower()

    @patch("cli_agent_orchestrator.providers.claude_code.requests.get")
    @patch("cli_agent_orchestrator.providers.claude_code._read_claude_oauth_token")
    def test_happy_path_returns_filtered_catalog(self, mock_token, mock_get):
        # Given — token resolves and the API returns the recorded fixture
        mock_token.return_value = "oauth-test-token"
        response = MagicMock(status_code=200)
        response.json.return_value = _load_fixture()
        mock_get.return_value = response
        capability = ClaudeModelDiscoveryCapability()

        # When
        catalog = capability.discover_catalog()

        # Then
        assert isinstance(catalog, ProviderCatalog)
        assert catalog.provider_type == "claude_code"
        assert catalog.source == "anthropic-api"
        assert len(catalog.models) > 0
        for model in catalog.models:
            assert isinstance(model, ProviderModel)
            assert model.id.startswith("claude-")

    @patch("cli_agent_orchestrator.providers.claude_code.requests.get")
    @patch("cli_agent_orchestrator.providers.claude_code._read_claude_oauth_token")
    def test_non_200_response_raises_catalog_discovery_error(self, mock_token, mock_get):
        # Given
        mock_token.return_value = "t"
        response = MagicMock(status_code=500)
        response.text = "internal error"
        mock_get.return_value = response
        capability = ClaudeModelDiscoveryCapability()

        # When / Then
        with pytest.raises(CatalogDiscoveryError) as exc_info:
            capability.discover_catalog()
        assert "500" in str(exc_info.value)

    @patch("cli_agent_orchestrator.providers.claude_code._read_claude_oauth_token")
    def test_routed_auth_raises_before_credentials_are_read(self, mock_token, monkeypatch):
        # Given
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        capability = ClaudeModelDiscoveryCapability()

        # When / Then
        with pytest.raises(CatalogDiscoveryError) as exc_info:
            capability.discover_catalog()
        assert "CLAUDE_CODE_USE_BEDROCK" in str(exc_info.value)
        mock_token.assert_not_called()

    def test_routed_auth_ignores_disabled_values(self):
        # Given
        environ = {
            "CLAUDE_CODE_USE_BEDROCK": "false",
            "CLAUDE_CODE_USE_VERTEX": "0",
            "CLAUDE_CODE_USE_FOUNDRY": "off",
        }

        # When / Then
        assert _routed_auth_var(environ) is None


class TestCapabilityExposure:
    """Tests for how the provider exposes the capability."""

    def test_claude_code_provider_exposes_model_discovery_capability(self):
        # When
        capability = ClaudeCodeProvider.model_discovery_capability()

        # Then — structural typing satisfies the protocol
        typed: ModelDiscoveryCapability = capability
        assert isinstance(capability, ClaudeModelDiscoveryCapability)
        assert typed is capability


class TestRealAnthropicApi:
    """Live calls to ``api.anthropic.com``. Skipped without local credentials."""

    def test_stale_oauth_error_is_treated_as_live_environment_state(self):
        # Given
        error = CatalogDiscoveryError(
            'Anthropic /v1/models returned HTTP 401: {"type":"error",'
            '"error":{"type":"authentication_error",'
            '"message":"Invalid authentication credentials"}}'
        )

        # When
        is_stale_credential_error = _is_stale_claude_oauth_error(error)

        # Then
        assert is_stale_credential_error is True

    def test_non_auth_discovery_error_is_not_treated_as_stale_oauth(self):
        # Given
        error = CatalogDiscoveryError("Anthropic /v1/models returned HTTP 500: internal error")

        # When
        is_stale_credential_error = _is_stale_claude_oauth_error(error)

        # Then
        assert is_stale_credential_error is False

    @pytest.mark.integration
    def test_real_api_returns_non_empty_catalog(self):
        # Given — only run when the dev has a logged-in Claude Code on macOS
        if _read_claude_oauth_token() is None:
            pytest.skip("Claude Code is not logged in (or not on macOS)")
        capability = ClaudeModelDiscoveryCapability()

        # When
        try:
            catalog = capability.discover_catalog()
        except CatalogDiscoveryError as exc:
            if _is_stale_claude_oauth_error(exc):
                pytest.skip(
                    "Claude Code's cached OAuth access token is stale; "
                    "running `claude` may refresh it without requiring a new login"
                )
            raise

        # Then
        assert catalog.provider_type == "claude_code"
        assert catalog.source == "anthropic-api"
        assert len(catalog.models) > 0
        assert all(model.id.startswith("claude-") for model in catalog.models)
        assert any(model.reasoning_efforts for model in catalog.models)

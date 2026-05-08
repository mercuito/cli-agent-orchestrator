"""Tests for CLI provider runtime configuration."""

import json
from unittest.mock import patch

import pytest

from cli_agent_orchestrator.providers.runtime_config import get_provider_paste_enter_count


@pytest.fixture
def settings_file(tmp_path):
    """Patch settings storage to use a temp file."""
    fake_settings = tmp_path / "settings.json"
    with (
        patch(
            "cli_agent_orchestrator.services.settings_service.SETTINGS_FILE",
            fake_settings,
        ),
        patch(
            "cli_agent_orchestrator.services.settings_service.CAO_HOME_DIR",
            tmp_path,
        ),
    ):
        yield fake_settings


def test_returns_packaged_provider_default_when_user_has_no_override(settings_file):
    assert get_provider_paste_enter_count("codex") == 3
    assert get_provider_paste_enter_count("copilot_cli") == 1
    assert get_provider_paste_enter_count("unknown_provider") == 2


def test_user_provider_override_wins_over_packaged_default(settings_file):
    settings_file.write_text(json.dumps({"provider_runtime": {"codex": {"paste_enter_count": 4}}}))

    assert get_provider_paste_enter_count("codex") == 4


def test_user_default_override_applies_to_unknown_provider(settings_file):
    settings_file.write_text(
        json.dumps({"provider_runtime": {"default": {"paste_enter_count": 5}}})
    )

    assert get_provider_paste_enter_count("unknown_provider") == 5


def test_provider_override_wins_over_user_default_override(settings_file):
    settings_file.write_text(
        json.dumps(
            {
                "provider_runtime": {
                    "default": {"paste_enter_count": 5},
                    "codex": {"paste_enter_count": 4},
                }
            }
        )
    )

    assert get_provider_paste_enter_count("codex") == 4


@pytest.mark.parametrize("value", [0, 11, True, "nope"])
def test_invalid_paste_enter_count_is_rejected(settings_file, value):
    settings_file.write_text(
        json.dumps({"provider_runtime": {"codex": {"paste_enter_count": value}}})
    )

    with pytest.raises(RuntimeError, match="paste_enter_count"):
        get_provider_paste_enter_count("codex")

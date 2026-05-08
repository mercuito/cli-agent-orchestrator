"""Runtime configuration for CLI providers."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict, Optional

from cli_agent_orchestrator.services.settings_service import get_settings

PROVIDER_RUNTIME_DEFAULTS_RESOURCE = "runtime_defaults.json"
PROVIDER_RUNTIME_SETTINGS_KEY = "provider_runtime"
PASTE_ENTER_COUNT_KEY = "paste_enter_count"
MIN_PASTE_ENTER_COUNT = 1
MAX_PASTE_ENTER_COUNT = 10


def _load_provider_runtime_defaults() -> Dict[str, Any]:
    """Load packaged provider runtime defaults."""
    defaults_file = resources.files("cli_agent_orchestrator.providers").joinpath(
        PROVIDER_RUNTIME_DEFAULTS_RESOURCE
    )
    try:
        data = json.loads(defaults_file.read_text())
    except Exception as e:
        raise RuntimeError(
            f"Failed to read packaged provider runtime defaults: {defaults_file}"
        ) from e
    if not isinstance(data, dict):
        raise RuntimeError("Packaged provider runtime defaults must be a JSON object")
    return data


def _provider_runtime_settings_from(
    data: Dict[str, Any], *, nested: bool
) -> Dict[str, Dict[str, Any]]:
    """Return provider runtime settings from raw defaults or user settings."""
    value = data.get(PROVIDER_RUNTIME_SETTINGS_KEY, {}) if nested else data
    if not isinstance(value, dict):
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    for provider, provider_settings in value.items():
        if isinstance(provider, str) and isinstance(provider_settings, dict):
            result[provider] = dict(provider_settings)
    return result


def _merged_provider_runtime_config(provider: Optional[str]) -> Dict[str, Any]:
    """Merge packaged defaults and user overrides for a provider."""
    defaults = _provider_runtime_settings_from(_load_provider_runtime_defaults(), nested=False)
    overrides = _provider_runtime_settings_from(get_settings(), nested=True)

    result: Dict[str, Any] = {}
    for source in (
        defaults.get("default"),
        defaults.get(provider or ""),
        overrides.get("default"),
        overrides.get(provider or ""),
    ):
        if source:
            result.update(source)
    return result


def get_provider_runtime_config(provider: Optional[str]) -> Dict[str, Any]:
    """Return the merged runtime configuration for provider-owned descriptors."""
    return _merged_provider_runtime_config(provider)


def _parse_paste_enter_count(value: Any) -> Optional[int]:
    """Parse a configured paste Enter count, returning None when invalid."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        count = value
    elif isinstance(value, str) and value.strip().isdigit():
        count = int(value.strip())
    else:
        return None

    if MIN_PASTE_ENTER_COUNT <= count <= MAX_PASTE_ENTER_COUNT:
        return count
    return None


def get_provider_paste_enter_count(provider: Optional[str]) -> int:
    """Get the configured Enter count for pasted input for a CLI provider."""
    config = _merged_provider_runtime_config(provider)
    count = _parse_paste_enter_count(config.get(PASTE_ENTER_COUNT_KEY))
    if count is None:
        provider_label = provider or "default"
        raise RuntimeError(
            f"Provider runtime config for {provider_label!r} must define "
            f"{PASTE_ENTER_COUNT_KEY!r} as an integer from "
            f"{MIN_PASTE_ENTER_COUNT} to {MAX_PASTE_ENTER_COUNT}"
        )
    return count

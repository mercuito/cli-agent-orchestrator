"""Generic helpers for runtime feature flags."""

from __future__ import annotations

import os


def env_enabled(name: str, *, default: bool = False) -> bool:
    """Return whether an environment variable is set to a truthy value."""

    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

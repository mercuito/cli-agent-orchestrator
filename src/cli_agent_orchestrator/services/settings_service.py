"""Settings service for persisting user configuration."""

import json
import logging
from typing import Any, Dict

from cli_agent_orchestrator.constants import CAO_HOME_DIR

logger = logging.getLogger(__name__)

SETTINGS_FILE = CAO_HOME_DIR / "settings.json"


def _load() -> Dict[str, Any]:
    """Load settings from disk."""
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning(f"Failed to read settings: {e}")
    return {}


def _save(data: Dict[str, Any]) -> None:
    """Save settings to disk."""
    CAO_HOME_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))


def get_settings() -> Dict[str, Any]:
    """Load raw user settings."""
    return _load()

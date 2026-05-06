"""Signed dashboard links for public CAO terminal views."""

from __future__ import annotations

import base64
import hmac
import os
import secrets
import time
from hashlib import sha256
from pathlib import Path
from typing import Optional

from cli_agent_orchestrator.constants import CAO_HOME_DIR

DASHBOARD_LINK_TTL_SECONDS = int(
    os.environ.get("CAO_DASHBOARD_LINK_TTL_SECONDS", str(7 * 24 * 60 * 60))
)
_SECRET_FILE = CAO_HOME_DIR / "dashboard-link-secret"


def _base64_urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unbase64_urlsafe(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _dashboard_link_secret() -> bytes:
    configured = os.environ.get("CAO_DASHBOARD_LINK_SECRET")
    if configured:
        return configured.encode("utf-8")

    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _SECRET_FILE.exists():
        _SECRET_FILE.write_text(secrets.token_urlsafe(48) + "\n")
        try:
            _SECRET_FILE.chmod(0o600)
        except OSError:
            pass
    return _SECRET_FILE.read_text().strip().encode("utf-8")


def create_terminal_dashboard_token(
    terminal_id: str,
    *,
    now: Optional[int] = None,
    ttl_seconds: int = DASHBOARD_LINK_TTL_SECONDS,
) -> str:
    """Create a signed, time-limited token for opening a terminal websocket."""

    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + ttl_seconds
    payload = f"{terminal_id}:{expires_at}"
    signature = hmac.new(_dashboard_link_secret(), payload.encode("utf-8"), sha256).hexdigest()
    return f"{_base64_urlsafe(payload.encode('utf-8'))}.{signature}"


def create_agent_dashboard_token(
    agent_id: str,
    *,
    now: Optional[int] = None,
    ttl_seconds: int = DASHBOARD_LINK_TTL_SECONDS,
) -> str:
    """Create a signed, time-limited token for resolving an agent dashboard link."""

    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + ttl_seconds
    payload = f"agent:{agent_id}:{expires_at}"
    signature = hmac.new(_dashboard_link_secret(), payload.encode("utf-8"), sha256).hexdigest()
    return f"{_base64_urlsafe(payload.encode('utf-8'))}.{signature}"


def validate_terminal_dashboard_token(
    token: str,
    terminal_id: str,
    *,
    now: Optional[int] = None,
) -> bool:
    """Return whether a dashboard token authorizes websocket access to a terminal."""

    try:
        encoded_payload, provided_signature = token.split(".", 1)
        payload = _unbase64_urlsafe(encoded_payload).decode("utf-8")
        token_terminal_id, raw_expires_at = payload.rsplit(":", 1)
        expires_at = int(raw_expires_at)
    except Exception:
        return False

    if token_terminal_id != terminal_id:
        return False
    current_time = int(time.time()) if now is None else now
    if expires_at < current_time:
        return False

    expected_signature = hmac.new(
        _dashboard_link_secret(), payload.encode("utf-8"), sha256
    ).hexdigest()
    return hmac.compare_digest(provided_signature, expected_signature)


def validate_agent_dashboard_token(
    token: str,
    agent_id: str,
    *,
    now: Optional[int] = None,
) -> bool:
    """Return whether a dashboard token authorizes resolving a durable agent link."""

    try:
        encoded_payload, provided_signature = token.split(".", 1)
        payload = _unbase64_urlsafe(encoded_payload).decode("utf-8")
        token_kind, token_agent_id, raw_expires_at = payload.rsplit(":", 2)
        expires_at = int(raw_expires_at)
    except Exception:
        return False

    if token_kind != "agent" or token_agent_id != agent_id:
        return False
    current_time = int(time.time()) if now is None else now
    if expires_at < current_time:
        return False

    expected_signature = hmac.new(
        _dashboard_link_secret(), payload.encode("utf-8"), sha256
    ).hexdigest()
    return hmac.compare_digest(provided_signature, expected_signature)

"""Tests for provider-bound presence reference helpers."""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.presence.models import ExternalRef
from cli_agent_orchestrator.presence.refs import ProviderRefFactory


def test_provider_ref_factory_creates_refs_bound_to_declared_provider():
    refs = ProviderRefFactory("workspace")

    assert refs.ref("thread-1") == ExternalRef(provider="workspace", id="thread-1")
    assert refs.ref("work-1", url="https://workspace/work-1") == ExternalRef(
        provider="workspace",
        id="work-1",
        url="https://workspace/work-1",
    )


def test_provider_ref_factory_rejects_missing_identity_or_id():
    with pytest.raises(ValueError, match="provider name is required"):
        ProviderRefFactory("")

    refs = ProviderRefFactory("workspace")
    with pytest.raises(ValueError, match="external ref id is required"):
        refs.ref("")

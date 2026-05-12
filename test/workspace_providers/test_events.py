"""Tests for workspace-provider event publication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from cli_agent_orchestrator.workspace_providers.events import (
    UnknownWorkspaceProviderEventError,
    WorkspaceProviderEvent,
    WorkspaceProviderEventConfigError,
    WorkspaceProviderEventDispatcher,
)


@dataclass(frozen=True)
class ExampleEvent(WorkspaceProviderEvent):
    provider_name: ClassVar[str] = "example"
    event_name: ClassVar[str] = "created"

    value: str


def test_workspace_provider_event_dispatcher_requires_declared_events():
    dispatcher = WorkspaceProviderEventDispatcher()

    with pytest.raises(UnknownWorkspaceProviderEventError):
        dispatcher.subscribe(
            event_type=ExampleEvent,
            handler=lambda event: None,
            subscription_id="subscriber",
        )

    dispatcher.register_events((ExampleEvent,))

    seen = []
    dispatcher.subscribe(
        event_type=ExampleEvent,
        handler=lambda event: seen.append(event) or "handled",
        subscription_id="subscriber",
    )
    publication = dispatcher.publish(ExampleEvent(value="hello"))

    assert seen == [publication.event]
    assert publication.handler_results[0].result == "handled"


def test_workspace_provider_event_dispatcher_requires_event_instances():
    dispatcher = WorkspaceProviderEventDispatcher()
    dispatcher.register_events((ExampleEvent,))

    with pytest.raises(WorkspaceProviderEventConfigError, match="must extend"):
        dispatcher.publish(object())  # type: ignore[arg-type]

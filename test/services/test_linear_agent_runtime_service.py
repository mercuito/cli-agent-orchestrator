"""Tests for routing Linear agent sessions into CAO terminals."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest

from cli_agent_orchestrator.agent_identity import AgentIdentityRegistry
from cli_agent_orchestrator.clients.database import create_inbox_delivery
from cli_agent_orchestrator.linear import runtime
from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearPresence,
    LinearResolvedPresence,
    LinearWorkspaceProvider,
)
from cli_agent_orchestrator.models.agent_profile import AgentProfile
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.presence.manager import PresenceProviderManager
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationMessageRecord,
    ConversationThread,
    ConversationThreadRecord,
    ExternalRef,
    PersistedPresenceEvent,
    PresenceEvent,
)
from cli_agent_orchestrator.presence.persistence import get_thread, upsert_thread
from cli_agent_orchestrator.providers.base import ProviderRuntimePreparation
from cli_agent_orchestrator.runtime import agent as runtime_agent
from cli_agent_orchestrator.runtime.agent import (
    AgentRuntimeDeliveryResult,
    AgentRuntimeFreshnessAction,
    AgentRuntimeNotifyResult,
    AgentRuntimeStatus,
)


@pytest.fixture
def test_db(runtime_inbox_db_session):
    return runtime_inbox_db_session


@pytest.fixture
def resolved_presence(implementation_partner_identity_factory):
    def _resolved_presence(
        *,
        app_key: str = "implementation_partner",
        agent_id: str = "implementation_partner",
        session_name: str = "implementation-partner",
        agent_profile: str = "developer",
        cli_provider: str = "codex",
        workdir: str = "/repo",
    ) -> LinearResolvedPresence:
        return LinearResolvedPresence(
            presence=LinearPresence(
                presence_id=app_key,
                agent_id=agent_id,
                app_key=app_key,
                app_user_name="Implementation Partner",
            ),
            identity=implementation_partner_identity_factory(
                id=agent_id,
                agent_profile=agent_profile,
                cli_provider=cli_provider,
                workdir=workdir,
                session_name=session_name,
            ),
        )

    return _resolved_presence


def _presence_event(
    *,
    action: str = "created",
    thread_id: str = "session-1",
    prompt_context: str | None = None,
    prompt_body: str | None = None,
) -> PresenceEvent:
    return PresenceEvent(
        provider="linear",
        event_type="AgentSessionEvent",
        action=action,
        thread=ConversationThread(
            ref=ExternalRef(provider="linear", id=thread_id),
            prompt_context=prompt_context,
        ),
        message=ConversationMessage(kind="prompt", body=prompt_body) if prompt_body else None,
        raw_payload={"action": action},
    )


def _linear_agent_session_payload() -> dict:
    return {
        "type": "AgentSessionEvent",
        "action": "prompted",
        "_cao_linear_app_key": "implementation_partner",
        "appUserId": "fresh-linear-app-user-id",
        "data": {
            "promptContext": '<issue identifier="CAO-43"><title>Durable identity</title></issue>',
            "agentSession": {
                "id": "session-1",
                "url": "https://linear.app/session/session-1",
                "issue": {
                    "id": "issue-43",
                    "identifier": "CAO-43",
                    "title": "Durable identity",
                    "url": "https://linear.app/issue/CAO-43",
                },
            },
            "agentActivity": {
                "id": "activity-1",
                "content": {
                    "type": "prompt",
                    "body": "Please instantiate the durable identity runtime.",
                },
            },
        },
    }


def test_build_terminal_message_does_not_include_prompt_context():
    event = _presence_event(prompt_context='<issue identifier="CAO-13"><title>Demo</title></issue>')

    message = runtime.build_terminal_message(event)

    assert "Action: created" in message
    assert "Conversation thread ID: session-1" in message
    assert '<issue identifier="CAO-13">' not in message
    assert "Linear prompt context:" not in message


def test_build_terminal_message_uses_prompted_body():
    event = _presence_event(action="prompted", prompt_body="Can you scope this?")

    message = runtime.build_terminal_message(event)

    assert "Action: prompted" in message
    assert "User prompt:" in message
    assert "Can you scope this?" in message


def test_ensure_discovery_terminal_reuses_existing_terminal(monkeypatch, resolved_presence):
    terminal = {"id": "terminal-1", "tmux_session": "cao-linear-discovery-partner"}
    handle = Mock()
    handle.ensure_started.return_value.as_terminal_metadata.return_value = terminal
    monkeypatch.setattr(
        runtime,
        "_resolve_linear_event",
        lambda event: resolved_presence(session_name="linear-discovery-partner"),
    )
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)

    assert runtime.ensure_discovery_terminal() == terminal
    handle.ensure_started.assert_called_once()


def test_terminal_config_comes_from_cao_identity_mapping(monkeypatch, resolved_presence):
    handle = Mock()
    handle.ensure_started.return_value.as_terminal_metadata.return_value = {"id": "terminal-1"}
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)

    assert runtime._terminal_for_resolved_presence(resolved_presence())["id"] == "terminal-1"
    handle.ensure_started.assert_called_once()


def test_handle_agent_session_event_updates_linear_and_sends_terminal_input(
    monkeypatch,
    resolved_presence,
):
    event = _presence_event(prompt_context="<issue/>")
    calls = []
    handle = Mock()
    handle.notify.return_value = Mock(
        terminal_id="terminal-1",
        status=Mock(value="idle"),
        notification=Mock(created=True),
    )
    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: resolved_presence())
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)
    update_url = Mock(side_effect=lambda *args, **kwargs: calls.append("update_url"))
    create_activity = Mock(side_effect=lambda *args, **kwargs: calls.append("create_activity"))
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)

    assert runtime.handle_presence_event(event) == "terminal-1"
    assert calls == ["update_url", "create_activity"]
    handle.notify.assert_called_once()
    assert handle.notify.call_args.kwargs["source_kind"] == runtime.LINEAR_RUNTIME_SOURCE_KIND
    update_url.assert_called_once_with(
        "session-1",
        "terminal-1",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )
    create_activity.assert_called_once()


def test_handle_presence_event_uses_verified_linear_app_key(monkeypatch, resolved_presence):
    event = _presence_event(prompt_context="<issue/>")
    event.raw_payload["_cao_linear_app_key"] = "implementation_partner"
    handle = Mock()
    handle.notify.return_value = Mock(
        terminal_id="terminal-implementation_partner",
        status=Mock(value="idle"),
        notification=Mock(created=True),
    )
    monkeypatch.setattr(
        runtime,
        "_resolve_linear_event",
        lambda event: resolved_presence(app_key=event.raw_payload["_cao_linear_app_key"]),
    )
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)
    monkeypatch.setattr(runtime.app_client, "linear_app_env", lambda app_key, name: None)
    update_url = Mock()
    create_activity = Mock()
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)

    assert runtime.handle_presence_event(event) == "terminal-implementation_partner"

    update_url.assert_called_once_with(
        "session-1",
        "terminal-implementation_partner",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )
    create_activity.assert_called_once()
    assert create_activity.call_args.kwargs["app_key"] == "implementation_partner"
    assert handle.notify.call_args.kwargs["sender_id"] == "linear:implementation_partner"


def test_publish_external_url_repairs_stale_published_url(test_db, monkeypatch):
    upsert_thread(
        provider="linear",
        external_id="session-1",
        metadata={
            runtime.LINEAR_EXTERNAL_URL_PUBLISHED_METADATA_KEY: True,
            runtime.LINEAR_EXTERNAL_URL_METADATA_KEY: "https://old.example/?agent_id=old",
        },
    )
    monkeypatch.setattr(
        runtime.app_client,
        "public_cao_runtime_url",
        Mock(return_value="https://cao.example/?agent_id=implementation_partner"),
    )
    update_url = Mock(return_value=True)
    monkeypatch.setattr(runtime, "_update_external_url_once", update_url)

    assert runtime._publish_persisted_external_url_once(
        thread_id="session-1",
        terminal_id="terminal-1",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )

    update_url.assert_called_once_with(
        thread_id="session-1",
        terminal_id="terminal-1",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )
    metadata = get_thread("linear", "session-1").metadata
    assert metadata[runtime.LINEAR_EXTERNAL_URL_METADATA_KEY] == (
        "https://cao.example/?agent_id=implementation_partner"
    )


def test_publish_external_url_skips_when_current_url_already_published(test_db, monkeypatch):
    upsert_thread(
        provider="linear",
        external_id="session-1",
        metadata={
            runtime.LINEAR_EXTERNAL_URL_PUBLISHED_METADATA_KEY: True,
            runtime.LINEAR_EXTERNAL_URL_METADATA_KEY: "https://cao.example/?agent_id=impl",
        },
    )
    monkeypatch.setattr(
        runtime.app_client,
        "public_cao_runtime_url",
        Mock(return_value="https://cao.example/?agent_id=impl"),
    )
    update_url = Mock(return_value=True)
    monkeypatch.setattr(runtime, "_update_external_url_once", update_url)

    assert not runtime._publish_persisted_external_url_once(
        thread_id="session-1",
        terminal_id="terminal-1",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )

    update_url.assert_not_called()


def test_publish_external_url_repairs_legacy_published_metadata_without_url(test_db, monkeypatch):
    upsert_thread(
        provider="linear",
        external_id="session-1",
        metadata={runtime.LINEAR_EXTERNAL_URL_PUBLISHED_METADATA_KEY: True},
    )
    monkeypatch.setattr(
        runtime.app_client,
        "public_cao_runtime_url",
        Mock(return_value="https://cao.example/?agent_id=implementation_partner"),
    )
    update_url = Mock(return_value=True)
    monkeypatch.setattr(runtime, "_update_external_url_once", update_url)

    assert runtime._publish_persisted_external_url_once(
        thread_id="session-1",
        terminal_id="terminal-1",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )

    update_url.assert_called_once()


def test_notify_agent_for_persisted_event_hands_semantic_delivery_to_runtime(
    test_db,
    monkeypatch,
    resolved_presence,
):
    event = _presence_event(prompt_body="Can you inspect this?")
    persisted_event = PersistedPresenceEvent(
        processed_event=None,
        work_item=None,
        thread=ConversationThreadRecord(
            id=1,
            provider="linear",
            external_id="session-1",
            external_url=None,
            work_item_id=None,
            kind="conversation",
            state="active",
            prompt_context=None,
            raw_snapshot=None,
            metadata=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
        message=ConversationMessageRecord(
            id=1,
            thread_id=1,
            provider="linear",
            external_id="activity-1",
            direction="inbound",
            kind="prompt",
            body="Can you inspect this?",
            state="received",
            raw_snapshot=None,
            metadata=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
    )
    delivery = create_inbox_delivery(
        "presence",
        "agent:implementation_partner",
        "Can you inspect this?",
        source_kind="presence_thread",
        source_id="1",
        route_kind="presence_thread",
        route_id="1",
    )
    bridge_notification = Mock(delivery=delivery, created=True)
    accepted = []

    def accept_notification(notification):
        accepted.append(notification)
        return AgentRuntimeNotifyResult(
            notification=notification,
            status=AgentRuntimeStatus.BUSY,
            terminal_id=None,
            started=False,
            delivery=AgentRuntimeDeliveryResult(
                status=AgentRuntimeStatus.BUSY,
                terminal_id=None,
                attempted=False,
                delivered=False,
            ),
        )

    handle = Mock(inbox_receiver_id="agent:implementation_partner")
    handle.accept_notification.side_effect = accept_notification
    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: resolved_presence())
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)
    monkeypatch.setattr(
        runtime,
        "create_notification_for_persisted_event",
        Mock(return_value=bridge_notification),
    )
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", Mock())
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", Mock())

    result = runtime.notify_agent_for_persisted_event(persisted_event, event)

    assert result is not None
    assert accepted[0].delivery.message.body == "Can you inspect this?"


def test_linear_agent_session_vertical_path_reaches_terminal_send_boundary(
    test_db,
    tmp_path,
    monkeypatch,
    implementation_partner_identity_factory,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    identity = implementation_partner_identity_factory(workdir=str(tmp_path / "repo"))
    registry = AgentIdentityRegistry({identity.id: identity})
    config_path = tmp_path / "linear.toml"
    config_path.write_text("""
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
app_user_name = "Implementation Partner"
""")
    workspace_provider = LinearWorkspaceProvider(
        agent_registry=registry,
        config_path=config_path,
        preflight_credentials=False,
    )
    monkeypatch.setattr(runtime, "get_linear_workspace_provider", lambda: workspace_provider)
    monkeypatch.setattr(
        "cli_agent_orchestrator.agent_identity.AGENT_IDENTITY_DATA_ROOT",
        tmp_path / "agents",
    )

    tmux = Mock()
    tmux.session_exists.return_value = False
    monkeypatch.setattr(runtime_agent, "tmux_client", tmux)
    monkeypatch.setattr(runtime_agent.terminal_service, "tmux_client", tmux)
    monkeypatch.setattr(runtime_agent.terminal_service, "TERMINAL_LOG_DIR", tmp_path)
    monkeypatch.setattr(
        runtime_agent.terminal_service, "generate_terminal_id", lambda: "terminal-a"
    )
    monkeypatch.setattr(
        runtime_agent.terminal_service, "generate_window_name", lambda profile: "dev-a"
    )
    monkeypatch.setattr(
        runtime_agent.terminal_service,
        "load_agent_profile",
        lambda profile: AgentProfile(name=profile, description="Developer"),
    )
    monkeypatch.setattr(runtime_agent.terminal_service, "build_skill_catalog", lambda: "")
    monkeypatch.setattr(
        runtime_agent.terminal_service.provider_manager,
        "prepare_terminal_runtime",
        Mock(return_value=ProviderRuntimePreparation()),
    )
    created_provider = Mock()
    created_provider.initialize.return_value = True
    monkeypatch.setattr(
        runtime_agent.terminal_service.provider_manager,
        "create_provider",
        Mock(return_value=created_provider),
    )
    monkeypatch.setattr(
        runtime_agent.provider_manager,
        "runtime_state_capability",
        lambda provider: None,
    )
    terminal_provider_patcher(runtime_agent.provider_manager, TerminalStatus.IDLE)
    send_input = terminal_send_patcher(runtime_agent.terminal_service)
    update_url = Mock(return_value=True)
    create_activity = Mock()
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)

    payload = _linear_agent_session_payload()
    manager = PresenceProviderManager({"linear": LinearPresenceProvider()})
    persisted_event = manager.ingest_event("linear", payload, delivery_id="delivery-1")
    event = manager.normalize_event("linear", payload, delivery_id="delivery-1")

    result = runtime.notify_agent_for_persisted_event(persisted_event, event)

    assert result is not None
    assert result.started is True
    assert result.freshness is not None
    assert result.freshness.action == AgentRuntimeFreshnessAction.STARTED
    assert result.terminal_id == "terminal-a"
    assert result.delivery.attempted is True
    assert result.delivery.delivered is True
    send_input.assert_called_once()
    assert send_input.call_args.args[0] == "terminal-a"
    assert "[CAO inbox notification]" in send_input.call_args.args[1]
    assert "Please instantiate the durable identity runtime." in send_input.call_args.args[1]
    update_url.assert_called_once_with(
        "session-1",
        "terminal-a",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )
    create_activity.assert_called()


def test_handle_presence_event_still_routes_through_agent_runtime_notify(
    monkeypatch, resolved_presence
):
    event = _presence_event(prompt_context="<issue/>")
    handle = Mock()
    handle.notify.return_value = Mock(
        terminal_id="terminal-1",
        status=Mock(value="idle"),
        notification=Mock(created=True),
    )
    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: resolved_presence())
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", Mock())
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", Mock())

    assert runtime.handle_presence_event(event) == "terminal-1"
    handle.notify.assert_called_once()


def test_notify_agent_for_persisted_event_still_routes_through_runtime_accept_notification(
    test_db,
    monkeypatch,
    resolved_presence,
):
    event = _presence_event(prompt_body="Can you inspect this?")
    persisted_event = PersistedPresenceEvent(
        processed_event=None,
        work_item=None,
        thread=ConversationThreadRecord(
            id=1,
            provider="linear",
            external_id="session-1",
            external_url=None,
            work_item_id=None,
            kind="conversation",
            state="active",
            prompt_context=None,
            raw_snapshot=None,
            metadata=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
        message=ConversationMessageRecord(
            id=1,
            thread_id=1,
            provider="linear",
            external_id="activity-1",
            direction="inbound",
            kind="prompt",
            body="Can you inspect this?",
            state="received",
            raw_snapshot=None,
            metadata=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
    )
    delivery = create_inbox_delivery("presence", "agent:implementation_partner", "Can you inspect")
    bridge_notification = Mock(delivery=delivery, created=True)
    handle = Mock(inbox_receiver_id="agent:implementation_partner")
    handle.accept_notification.return_value = AgentRuntimeNotifyResult(
        notification=bridge_notification,
        status=AgentRuntimeStatus.BUSY,
        terminal_id=None,
        started=False,
        delivery=AgentRuntimeDeliveryResult(
            status=AgentRuntimeStatus.BUSY,
            terminal_id=None,
            attempted=False,
            delivered=False,
        ),
    )
    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: resolved_presence())
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)
    monkeypatch.setattr(
        runtime,
        "create_notification_for_persisted_event",
        Mock(return_value=bridge_notification),
    )
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", Mock())
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", Mock())

    runtime.notify_agent_for_persisted_event(persisted_event, event)

    handle.accept_notification.assert_called_once()

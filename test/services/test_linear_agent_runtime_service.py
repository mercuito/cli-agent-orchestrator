"""Tests for routing Linear agent sessions into CAO terminals."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from test.support.agent_factory import Agent
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cli_agent_orchestrator.agent import (
    AgentRegistry,
    AgentWorkspaceConfig,
    LinearConfig,
    write_agent,
)
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import create_inbox_delivery
from cli_agent_orchestrator.linear import runtime
from cli_agent_orchestrator.linear.workspace_events import (
    LinearIssueContextEvent,
    publish_linear_provider_event,
)
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearPresence,
    LinearResolvedPresence,
    LinearWorkspaceProvider,
)
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.provider_conversations.models import (
    ConversationMessageRecord,
    ConversationThreadRecord,
    PersistedProviderEventRecords,
)
from cli_agent_orchestrator.provider_conversations.persistence import get_thread, upsert_thread
from cli_agent_orchestrator.providers.base import ProviderRuntimePreparation
from cli_agent_orchestrator.runtime import agent as runtime_agent
from cli_agent_orchestrator.runtime.agent import (
    AgentRuntimeDeliveryResult,
    AgentRuntimeFreshnessAction,
    AgentRuntimeHandle,
    AgentRuntimeNotifyResult,
    AgentRuntimeStatus,
)


@pytest.fixture
def test_db(runtime_inbox_db_session):
    return runtime_inbox_db_session


@pytest.fixture(autouse=True)
def _disable_agent_policies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runtime, "should_enable_linear_agent_policies", lambda: False)


@pytest.fixture
def resolved_presence(implementation_partner_agent_factory):
    def _resolved_presence(
        *,
        app_key: str = "implementation_partner",
        agent_id: str = "implementation_partner",
        session_name: str = "implementation-partner",
        cli_provider: str = "codex",
        workdir: str = "/repo",
        team: str | None = "cao_delivery",
    ) -> LinearResolvedPresence:
        return LinearResolvedPresence(
            presence=LinearPresence(
                presence_id=app_key,
                agent_id=agent_id,
                app_key=app_key,
                app_user_name="Implementation Partner",
            ),
            agent=implementation_partner_agent_factory(
                id=agent_id,
                cli_provider=cli_provider,
                workdir=workdir,
                session_name=session_name,
                workspace=AgentWorkspaceConfig(team=team),
            ),
        )

    return _resolved_presence


def _linear_provider_event(
    *,
    app_key: str = "implementation_partner",
    app_user_id: str | None = None,
    app_user_name: str | None = "Implementation Partner",
    action: str = "created",
    thread_id: str = "session-1",
    prompt_context: str | None = None,
    prompt_body: str | None = None,
    issue_id: str = "issue-1",
    issue_identifier: str = "CAO-1",
    parent_issue_id: str | None = None,
    parent_issue_identifier: str | None = None,
) -> LinearIssueContextEvent:
    return LinearIssueContextEvent(
        event_type="AgentSessionEvent",
        action=action,
        app_key=app_key,
        app_user_id=app_user_id,
        app_user_name=app_user_name,
        issue_id=issue_id,
        issue_identifier=issue_identifier,
        parent_issue_id=parent_issue_id,
        parent_issue_identifier=parent_issue_identifier,
        agent_session_id=thread_id,
        thread_id=thread_id,
        prompt_context=prompt_context,
        message_id="activity-1" if prompt_body else None,
        message_body=prompt_body,
        message_kind="prompt" if prompt_body else None,
        raw_payload={
            "type": "AgentSessionEvent",
            "action": action,
        },
    )


def _linear_agent_session_payload() -> dict:
    return {
        "type": "AgentSessionEvent",
        "action": "prompted",
        "_cao_linear_app_key": "implementation_partner",
        "appUserId": "fresh-linear-app-user-id",
        "data": {
            "promptContext": '<issue identifier="CAO-43"><title>Durable agent</title></issue>',
            "agentSession": {
                "id": "session-1",
                "url": "https://linear.app/session/session-1",
                "issue": {
                    "id": "issue-43",
                    "identifier": "CAO-43",
                    "title": "Durable agent",
                    "url": "https://linear.app/issue/CAO-43",
                },
            },
            "agentActivity": {
                "id": "activity-1",
                "content": {
                    "type": "prompt",
                    "body": "Please instantiate the durable agent runtime.",
                },
            },
        },
    }


def test_build_terminal_message_does_not_include_prompt_context():
    event = _linear_provider_event(
        prompt_context='<issue identifier="CAO-13"><title>Demo</title></issue>'
    )

    message = runtime.build_terminal_message(event)

    assert "Action: created" in message
    assert "Conversation thread ID: session-1" in message
    assert '<issue identifier="CAO-13">' not in message
    assert "Linear prompt context:" not in message


def test_build_terminal_message_uses_prompted_body():
    event = _linear_provider_event(action="prompted", prompt_body="Can you scope this?")

    message = runtime.build_terminal_message(event)

    assert "Action: prompted" in message
    assert "User prompt:" in message
    assert "Can you scope this?" in message


def test_ensure_discovery_terminal_reuses_existing_terminal(monkeypatch, resolved_presence):
    terminal = SimpleNamespace(id="terminal-1", session_name="cao-linear-discovery-partner")
    handle = Mock()
    handle.ensure_started.return_value = terminal
    resolved = resolved_presence(session_name="linear-discovery-partner")
    provider = Mock()
    provider.resolve_presence.return_value = resolved.presence
    provider.resolve_agent_for_presence.return_value = resolved.agent
    monkeypatch.setattr(runtime, "get_linear_workspace_provider", lambda: provider)
    monkeypatch.setattr(
        runtime,
        "_runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )

    assert runtime.ensure_discovery_terminal() == terminal
    handle.ensure_started.assert_called_once()


def test_terminal_config_comes_from_cao_agent_mapping(monkeypatch, resolved_presence):
    handle = Mock()
    handle.ensure_started.return_value = SimpleNamespace(id="terminal-1")
    monkeypatch.setattr(
        runtime,
        "_runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )

    assert runtime._terminal_for_resolved_presence(resolved_presence()).id == "terminal-1"
    handle.ensure_started.assert_called_once()


def test_agent_without_workspace_setup_gets_default_runtime_context(test_db, resolved_presence):
    resolved = resolved_presence(team=None)

    handle = AgentRuntimeHandle(
        resolved.agent,
        agent_manager=runtime.AgentManager(
            configured_agents=AgentRegistry({resolved.agent.id: resolved.agent})
        ),
    )

    assert handle.workspace_context_id == db_module.default_workspace_context_id(
        resolved.agent.id
    )


def test_handle_agent_session_event_updates_linear_and_sends_terminal_input(
    test_db,
    monkeypatch,
    resolved_presence,
):
    event = _linear_provider_event(prompt_context="<issue/>")
    calls = []
    handle = Mock()
    handle.notify.return_value = Mock(
        terminal_id="terminal-1",
        status=Mock(value="idle"),
        notification=Mock(created=True),
    )
    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: resolved_presence())
    monkeypatch.setattr(
        runtime,
        "_runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )
    update_url = Mock(side_effect=lambda *args, **kwargs: calls.append("update_url"))
    create_activity = Mock(side_effect=lambda *args, **kwargs: calls.append("create_activity"))
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)

    assert runtime.handle_provider_event(event) == "terminal-1"
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


def test_context_enabled_linear_event_starts_runtime_in_resolved_issue_context(
    test_db,
    monkeypatch,
    resolved_presence,
):
    event = _linear_provider_event(
        prompt_context="<issue/>",
        issue_id="issue-79",
        issue_identifier="CAO-79",
    )
    captured = {}

    def resolved_with_context():
        resolved = resolved_presence()
        return LinearResolvedPresence(
            presence=resolved.presence,
            agent=implementation_partner_agent_factory_with_context(resolved.agent),
        )

    def fake_handle(agent, workspace_context_id=None, agent_manager=None):
        captured["workspace_context_id"] = workspace_context_id
        handle = Mock()
        handle.notify.return_value = Mock(
            terminal_id="terminal-1",
            status=Mock(value="idle"),
            notification=Mock(created=True),
        )
        return handle

    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: resolved_with_context())
    monkeypatch.setattr(runtime, "AgentRuntimeHandle", fake_handle)
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", Mock())
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", Mock())

    assert runtime.handle_provider_event(event) == "terminal-1"
    context = db_module.get_workspace_context_for_object(
        provider_id="linear",
        object_type="issue",
        object_id="CAO-79",
    )
    assert context is not None
    assert captured["workspace_context_id"] == context.id


def test_context_enabled_linear_event_fails_closed_for_unknown_setup(
    test_db,
    monkeypatch,
    resolved_presence,
):
    event = _linear_provider_event(
        prompt_context="<issue/>",
        issue_id="issue-79",
        issue_identifier="CAO-79",
    )
    calls = []

    def resolved_with_context():
        resolved = resolved_presence()
        return LinearResolvedPresence(
            presence=resolved.presence,
            agent=replace(
                resolved.agent,
                workspace=AgentWorkspaceConfig(team="future_setup"),
            ),
        )

    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: resolved_with_context())
    monkeypatch.setattr(runtime, "AgentRuntimeHandle", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", Mock())
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", Mock())

    with pytest.raises(
        runtime.LinearWorkspaceProviderConfigError,
        match="Unknown workspace team",
    ):
        runtime.handle_provider_event(event)
    assert calls == []


def test_context_enabled_linear_events_switch_only_across_distinct_boundaries(
    test_db,
    monkeypatch,
    resolved_presence,
):
    captured_contexts = []

    def resolved_with_context():
        resolved = resolved_presence()
        return LinearResolvedPresence(
            presence=resolved.presence,
            agent=implementation_partner_agent_factory_with_context(resolved.agent),
        )

    def fake_handle(agent, workspace_context_id=None, agent_manager=None):
        captured_contexts.append(workspace_context_id)
        handle = Mock()
        handle.notify.return_value = Mock(
            terminal_id=f"terminal-{len(captured_contexts)}",
            status=Mock(value="idle"),
            notification=Mock(created=True),
        )
        return handle

    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: resolved_with_context())
    monkeypatch.setattr(runtime, "AgentRuntimeHandle", fake_handle)
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", Mock())
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", Mock())

    issue_a = _linear_provider_event(
        thread_id="session-a",
        prompt_context="<issue/>",
        issue_id="issue-a",
        issue_identifier="CAO-100",
    )
    child_of_a = _linear_provider_event(
        thread_id="session-a-child",
        prompt_context="<issue/>",
        issue_id="issue-a-child",
        issue_identifier="CAO-101",
        parent_issue_id="issue-a",
        parent_issue_identifier="CAO-100",
    )
    issue_b = _linear_provider_event(
        thread_id="session-b",
        prompt_context="<issue/>",
        issue_id="issue-b",
        issue_identifier="CAO-200",
    )

    assert runtime.handle_provider_event(issue_a) == "terminal-1"
    assert runtime.handle_provider_event(child_of_a) == "terminal-2"
    assert runtime.handle_provider_event(issue_b) == "terminal-3"

    assert captured_contexts[0] == captured_contexts[1]
    assert captured_contexts[2] != captured_contexts[0]


def implementation_partner_agent_factory_with_context(agent):
    return replace(
        agent,
        workspace=AgentWorkspaceConfig(team="cao_delivery"),
    )


def test_handle_linear_provider_event_uses_verified_linear_app_key(
    test_db, monkeypatch, resolved_presence
):
    event = _linear_provider_event(prompt_context="<issue/>")
    handle = Mock()
    handle.notify.return_value = Mock(
        terminal_id="terminal-implementation_partner",
        status=Mock(value="idle"),
        notification=Mock(created=True),
    )
    monkeypatch.setattr(
        runtime,
        "_resolve_linear_event",
        lambda event: resolved_presence(app_key=event.app_key),
    )
    monkeypatch.setattr(
        runtime,
        "_runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )
    monkeypatch.setattr(runtime.app_client, "linear_app_env", lambda app_key, name: None)
    update_url = Mock()
    create_activity = Mock()
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)

    assert runtime.handle_provider_event(event) == "terminal-implementation_partner"

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


def test_publish_external_url_repairs_missing_published_url_metadata(test_db, monkeypatch):
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
    event = _linear_provider_event(prompt_body="Can you inspect this?")
    persisted_event = PersistedProviderEventRecords(
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
        "provider_conversation",
        "agent:implementation_partner",
        "Can you inspect this?",
        source_kind="provider_conversation_thread",
        source_id="1",
        route_kind="provider_conversation_thread",
        route_id="1",
    )
    bridge_notification = Mock(delivery=delivery, created=True)
    accepted = []

    def accept_notification(notification, *, causing_event=None):
        accepted.append(notification)
        assert causing_event is provider_event
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
    monkeypatch.setattr(
        runtime,
        "_runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )
    monkeypatch.setattr(
        runtime,
        "create_notification_for_persisted_event",
        Mock(return_value=bridge_notification),
    )
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", Mock())
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", Mock())

    provider_event = event

    result = runtime.notify_agent_for_persisted_event(persisted_event, provider_event)

    assert result is not None
    assert accepted[0].delivery.message.body == "Can you inspect this?"


def test_linear_agent_session_vertical_path_reaches_terminal_send_boundary(
    test_db,
    tmp_path,
    monkeypatch,
    implementation_partner_agent_factory,
    terminal_provider_patcher,
    terminal_send_patcher,
):
    agent = replace(
        implementation_partner_agent_factory(workdir=str(tmp_path / "repo")),
        linear=LinearConfig(
            app_key="implementation_partner",
            app_user_name="Implementation Partner",
        ),
        workspace=AgentWorkspaceConfig(team="cao_delivery"),
    )
    registry = AgentRegistry({agent.id: agent})
    agents_root = tmp_path / "agents"
    write_agent(agent, agents_root=agents_root)
    workspace_provider = LinearWorkspaceProvider(
        agent_registry=registry,
        preflight_credentials=False,
    )
    monkeypatch.setattr(runtime, "get_linear_workspace_provider", lambda: workspace_provider)
    monkeypatch.setattr(
        "cli_agent_orchestrator.agent.AGENTS_ROOT",
        agents_root,
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
        "load_agent",
        lambda agent_id: agent,
    )
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
    publication = publish_linear_provider_event(payload, delivery_id="delivery-1")
    assert publication is not None
    provider_event = publication.event
    assert isinstance(provider_event, LinearIssueContextEvent)
    persisted_event = runtime.persist_linear_provider_event(provider_event)

    result = runtime.notify_agent_for_persisted_event(persisted_event, provider_event)

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
    assert "Please instantiate the durable agent runtime." in send_input.call_args.args[1]
    update_url.assert_called_once_with(
        "session-1",
        "terminal-a",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )
    create_activity.assert_called()


def test_out_of_setup_linear_event_rejects_before_runtime_or_inbox_creation(
    test_db,
    tmp_path,
    monkeypatch,
    implementation_partner_agent_factory,
):
    agent_a = replace(
        implementation_partner_agent_factory(id="agent_a", session_name="agent-a"),
        workspace=AgentWorkspaceConfig(team="cao_delivery"),
        linear=LinearConfig(app_key="agent-a", app_user_id="linear-user-a"),
    )
    agent_b = replace(
        implementation_partner_agent_factory(id="agent_b", session_name="agent-b"),
        workspace=AgentWorkspaceConfig(),
        linear=LinearConfig(app_key="agent-b", app_user_id="linear-user-b"),
    )
    provider = LinearWorkspaceProvider(
        agent_registry=AgentRegistry({agent_a.id: agent_a, agent_b.id: agent_b}),
        preflight_credentials=False,
    )
    monkeypatch.setattr(runtime, "get_linear_workspace_provider", lambda: provider)
    handle = Mock()
    bridge = Mock()
    monkeypatch.setattr(runtime, "AgentRuntimeHandle", handle)
    monkeypatch.setattr(runtime, "create_notification_for_persisted_event", bridge)

    event = _linear_provider_event(
        app_key="agent-b",
        app_user_id="linear-user-b",
        app_user_name=None,
        prompt_body="Can you inspect this?",
    )
    persisted_event = PersistedProviderEventRecords(
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

    assert runtime.notify_agent_for_persisted_event(persisted_event, event) is None
    handle.assert_not_called()
    bridge.assert_not_called()


def test_handle_linear_provider_event_routes_through_agent_runtime_notify(
    test_db, monkeypatch, resolved_presence
):
    event = _linear_provider_event(prompt_context="<issue/>")
    handle = Mock()
    handle.notify.return_value = Mock(
        terminal_id="terminal-1",
        status=Mock(value="idle"),
        notification=Mock(created=True),
    )
    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: resolved_presence())
    monkeypatch.setattr(
        runtime,
        "_runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", Mock())
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", Mock())

    assert runtime.handle_provider_event(event) == "terminal-1"
    handle.notify.assert_called_once()


def test_notify_agent_for_persisted_event_routes_through_runtime_accept_notification(
    test_db,
    monkeypatch,
    resolved_presence,
):
    event = _linear_provider_event(prompt_body="Can you inspect this?")
    persisted_event = PersistedProviderEventRecords(
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
        "provider_conversation", "agent:implementation_partner", "Can you inspect"
    )
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
    monkeypatch.setattr(
        runtime,
        "_runtime_handle_for_resolved_presence",
        lambda resolved, **_kwargs: handle,
    )
    monkeypatch.setattr(
        runtime,
        "create_notification_for_persisted_event",
        Mock(return_value=bridge_notification),
    )
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", Mock())
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", Mock())

    provider_event = event

    runtime.notify_agent_for_persisted_event(persisted_event, provider_event)

    handle.accept_notification.assert_called_once()

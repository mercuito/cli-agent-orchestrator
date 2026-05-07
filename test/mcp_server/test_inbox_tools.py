"""Tests for CAO MCP inbox read/reply tools."""

from __future__ import annotations

import json
from typing import Any, List, Mapping, Optional
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import (
    Base,
    create_inbox_delivery,
    create_inbox_notification_event,
    create_terminal,
)
from cli_agent_orchestrator.mcp_server.server import (
    _read_inbox_message_impl,
    _reply_to_inbox_message_impl,
    read_inbox_message,
)
from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider
from cli_agent_orchestrator.presence.inbox_bridge import (
    PRESENCE_INBOX_SOURCE_KIND,
    create_notification_for_message,
)
from cli_agent_orchestrator.presence.manager import presence_provider_manager
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    MessageKind,
    PresenceEvent,
    StopAcknowledgement,
)
from cli_agent_orchestrator.presence.inbox_read_presentation import inbox_read_presentation_metadata
from cli_agent_orchestrator.presence.persistence import (
    get_thread,
    list_messages,
    upsert_message,
    upsert_thread,
    upsert_work_item,
)


@pytest.fixture
def test_session(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=engine))
    presence_provider_manager.clear_providers()
    yield
    presence_provider_manager.clear_providers()


class FakePresenceProvider:
    name = "example"

    def __init__(self) -> None:
        self.replies: List[dict[str, Any]] = []

    def normalize_event(
        self,
        raw_event: Mapping[str, Any],
        *,
        delivery_id: Optional[str] = None,
    ) -> Optional[PresenceEvent]:
        return None

    def fetch_thread(self, thread_ref: ExternalRef) -> ConversationThread:
        return ConversationThread(ref=thread_ref)

    def fetch_messages(self, thread_ref: ExternalRef) -> List[ConversationMessage]:
        return []

    def reply_to_thread(
        self,
        thread_ref: ExternalRef,
        body: str,
        *,
        kind: MessageKind = "response",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ConversationMessage:
        self.replies.append(
            {"thread_ref": thread_ref, "body": body, "kind": kind, "metadata": metadata}
        )
        return ConversationMessage(
            kind=kind,
            body=body,
            ref=ExternalRef(provider="example", id="reply-1"),
            direction="outbound",
            state="delivered",
        )

    def acknowledge_stop(
        self,
        thread_ref: ExternalRef,
        *,
        message_ref: Optional[ExternalRef] = None,
        reason: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> StopAcknowledgement:
        return StopAcknowledgement(thread_ref=thread_ref, supported=False)


class LeakyFailurePresenceProvider(FakePresenceProvider):
    def reply_to_thread(
        self,
        thread_ref: ExternalRef,
        body: str,
        *,
        kind: MessageKind = "response",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ConversationMessage:
        raise RuntimeError(
            "Linear API failed access_token=secret-token "
            'password="correct horse battery staple" '
            "Authorization: Bearer bearer-secret "
            f"payload={'x' * 5000}\n"
            '  File "/tmp/provider.py", line 1, in reply\n'
            "stack locals include refresh_token=refresh-secret"
        )


def _presence_notification() -> int:
    thread = upsert_thread(
        provider="example",
        external_id="thread-1",
        external_url="https://presence.example/thread-1",
        kind="conversation",
        prompt_context="Full context from provider",
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-1",
        direction="inbound",
        kind="prompt",
        body="Full provider body",
        raw_snapshot={"provider": {"body": "Full provider body", "extra": "metadata"}},
    )
    return create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:example",
    ).delivery.notification.id


def _presence_notification_with_large_raw_snapshot() -> int:
    thread = upsert_thread(
        provider="example",
        external_id="thread-raw",
        raw_snapshot={"large": "x" * 50_000},
        metadata={"large": "y" * 50_000},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-raw",
        direction="inbound",
        kind="prompt",
        body="Small provider body",
        raw_snapshot={"large": "z" * 50_000},
        metadata={"actor": {"name": "Provider Author"}},
    )
    return create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:example",
    ).delivery.notification.id


def _linear_presence_notification() -> int:
    thread = upsert_thread(
        provider="linear",
        external_id="session-1",
        kind="conversation",
        raw_snapshot={"_cao_linear_app_key": "implementation_partner"},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-1",
        direction="inbound",
        kind="prompt",
        body="Linear body",
    )
    return create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:implementation_partner",
    ).delivery.notification.id


def _linear_presence_notification_with_work_item_and_metadata() -> int:
    work_item = upsert_work_item(
        provider="linear",
        external_id="issue-uuid-1",
        identifier="CAO-34",
        title="Add workspace breadcrumb contribution path",
        raw_snapshot={"large": "issue-raw-" * 5000},
    )
    thread = upsert_thread(
        provider="linear",
        external_id="session-123",
        kind="conversation",
        work_item_id=work_item.id,
        raw_snapshot={"large": "thread-raw-" * 5000},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-123",
        direction="inbound",
        kind="prompt",
        body="Please implement the breadcrumb.",
        metadata=inbox_read_presentation_metadata(
            workspace={
                "name": "Linear",
                "breadcrumb": {
                    "agent_session_id": "session-123",
                    "issue": "CAO-34",
                },
            },
            source_label="Implementation Partner",
        ),
        raw_snapshot={
            "actor": {"name": "Raw Snapshot Author Should Not Leak"},
            "large": "message-raw-" * 5000,
        },
    )
    return create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:implementation_partner",
    ).delivery.notification.id


def _linear_presence_notification_with_prompt_context(prompt_context: str) -> int:
    thread = upsert_thread(
        provider="linear",
        external_id="session-context",
        kind="conversation",
        prompt_context=prompt_context,
        raw_snapshot={"data": {"promptContext": prompt_context, "token": "raw-secret"}},
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="linear",
        external_id="activity-context",
        direction="inbound",
        kind="prompt",
        body="Please use the bounded context.",
        metadata=inbox_read_presentation_metadata(
            context={"linear_prompt_context": prompt_context[:3500]},
            source_label="Linear",
        ),
    )
    return create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:implementation_partner",
    ).delivery.notification.id


@pytest.mark.asyncio
async def test_read_inbox_message_returns_terminal_backed_slim_payload_with_workspace_null(
    test_session,
):
    create_terminal(
        "terminal-sender",
        "session",
        "window",
        "codex",
        agent_profile="implementation_partner",
    )
    delivery = create_inbox_delivery(
        "terminal-sender",
        "terminal-receiver",
        "I finished the patch. Can you review it?",
    )

    result = await read_inbox_message(delivery.notification.id)

    assert result == {
        "success": True,
        "notification_id": delivery.notification.id,
        "message_id": delivery.message.id,
        "from": "Implementation Partner",
        "body": "I finished the patch. Can you review it?",
        "replyable": False,
        "workspace": None,
        "reply_error": "no provider reply route",
    }


def test_provider_backed_read_returns_slim_payload_without_raw_context(test_session):
    notification_id = _presence_notification()

    result = _read_inbox_message_impl(notification_id)

    assert result == {
        "success": True,
        "notification_id": notification_id,
        "message_id": result["message_id"],
        "from": "Example",
        "body": "Full provider body",
        "replyable": True,
        "workspace": None,
    }
    assert "id" not in result
    assert "provider_context" not in result
    assert "inbox_message" not in result
    assert "reply" not in result


def test_linear_backed_read_returns_provider_owned_workspace_breadcrumb(test_session):
    notification_id = _linear_presence_notification_with_work_item_and_metadata()

    result = _read_inbox_message_impl(notification_id)

    assert result == {
        "success": True,
        "notification_id": notification_id,
        "message_id": result["message_id"],
        "from": "Implementation Partner",
        "body": "Please implement the breadcrumb.",
        "replyable": True,
        "workspace": {
            "name": "Linear",
            "breadcrumb": {
                "agent_session_id": "session-123",
                "issue": "CAO-34",
            },
        },
    }


def test_linear_backed_read_returns_bounded_named_prompt_context(test_session):
    # Shape sources:
    # https://linear.app/developers/agent-interaction/
    # https://linear.app/developers/agents
    # https://hexdocs.pm/linear_sdk/LinearSDK.Objects.AgentSessionEventWebhookPayload.html
    prompt_context = "<issue>Current scope</issue>\n" + ("prior comment " * 800)
    notification_id = _linear_presence_notification_with_prompt_context(prompt_context)

    result = _read_inbox_message_impl(notification_id)
    encoded = json.dumps(result)

    assert result["success"] is True
    assert result["body"] == "Please use the bounded context."
    assert result["context"]["linear_prompt_context"].startswith("<issue>Current scope</issue>")
    assert len(result["context"]["linear_prompt_context"]) <= 4000
    assert "token" not in encoded
    assert "raw-secret" not in encoded
    assert "prior comment " * 500 not in encoded


def test_provider_backed_read_body_is_backing_message_not_notification_wrapper(test_session):
    notification_id = _presence_notification()

    result = _read_inbox_message_impl(notification_id)

    assert result["body"] == "Full provider body"
    assert "[CAO inbox notification]" not in result["body"]
    assert "read_inbox_message" not in result["body"]


def test_provider_backed_read_missing_backing_message_fails_clearly(test_session):
    notification_id = _presence_notification()

    with db_module.SessionLocal() as session:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        session.query(db_module.PresenceMessageModel).delete()
        session.commit()

    result = _read_inbox_message_impl(notification_id)

    assert result["success"] is False
    assert result["error_type"] == "InboxReadNotFoundError"
    assert "presence message" in result["error"]
    assert "not found" in result["error"]


def test_provider_backed_read_missing_backing_thread_fails_clearly(test_session):
    notification_id = _presence_notification()

    with db_module.SessionLocal() as session:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        session.query(db_module.PresenceThreadModel).delete()
        session.commit()

    result = _read_inbox_message_impl(notification_id)

    assert result["success"] is False
    assert result["error_type"] == "InboxReadNotFoundError"
    assert "presence thread" in result["error"]
    assert "not found" in result["error"]


def test_read_inbox_message_uses_bounded_sender_fallback_without_internal_ids(test_session):
    delivery = create_inbox_delivery(
        "missing-terminal-id",
        "terminal-receiver",
        "Plain terminal message",
    )

    result = _read_inbox_message_impl(delivery.notification.id)

    assert result["from"] == "Terminal sender"
    assert "missing-terminal-id" not in json.dumps(result)


def test_large_raw_snapshots_do_not_inflate_default_read_response(test_session):
    notification_id = _presence_notification_with_large_raw_snapshot()

    result = _read_inbox_message_impl(notification_id)
    encoded = json.dumps(result)

    assert result["body"] == "Small provider body"
    assert result["from"] == "Example"
    assert len(encoded) < 500
    assert "z" * 1000 not in encoded


def test_large_linear_raw_snapshots_do_not_leak_through_breadcrumb_or_sender_label(test_session):
    notification_id = _linear_presence_notification_with_work_item_and_metadata()

    result = _read_inbox_message_impl(notification_id)
    encoded = json.dumps(result)

    assert result["from"] == "Implementation Partner"
    assert result["workspace"]["breadcrumb"] == {
        "agent_session_id": "session-123",
        "issue": "CAO-34",
    }
    assert "Raw Snapshot Author Should Not Leak" not in encoded
    assert "message-raw-message-raw" not in encoded
    assert len(encoded) < 500


def test_invalid_provider_authored_workspace_metadata_is_omitted_from_slim_read(test_session):
    thread = upsert_thread(provider="example", external_id="thread-invalid-workspace")
    message = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-invalid-workspace",
        direction="inbound",
        kind="prompt",
        body="Full provider body",
        metadata=inbox_read_presentation_metadata(
            workspace={"name": "Example", "breadcrumb": ["not", "a", "mapping"]}
        ),
    )
    notification_id = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:example",
    ).delivery.notification.id

    result = _read_inbox_message_impl(notification_id)

    assert result["success"] is True
    assert result["workspace"] is None
    assert result["body"] == "Full provider body"


def test_oversized_provider_authored_workspace_metadata_is_omitted_from_slim_read(test_session):
    thread = upsert_thread(provider="example", external_id="thread-oversized-workspace")
    message = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-oversized-workspace",
        direction="inbound",
        kind="prompt",
        body="Full provider body",
        metadata=inbox_read_presentation_metadata(
            workspace={
                "name": "Example",
                "breadcrumb": {"thread_id": "thread-oversized-workspace", "snapshot": "x" * 2000},
            }
        ),
    )
    notification_id = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:example",
    ).delivery.notification.id

    result = _read_inbox_message_impl(notification_id)
    encoded = json.dumps(result)

    assert result["success"] is True
    assert result["workspace"] is None
    assert "x" * 1000 not in encoded


def test_provider_backed_read_without_marker_fails_clearly(test_session):
    thread = upsert_thread(
        provider="example",
        external_id="thread-with-reply",
        external_url="https://presence.example/thread-with-reply",
        kind="conversation",
    )
    upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-inbound",
        direction="inbound",
        kind="prompt",
        body="Original provider prompt",
    )
    upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-outbound",
        direction="outbound",
        kind="response",
        body="Previous CAO reply",
    )
    delivery = create_inbox_delivery(
        "presence",
        "agent:example",
        "Presence update",
        source_kind=PRESENCE_INBOX_SOURCE_KIND,
        source_id=str(thread.id),
        route_kind=PRESENCE_INBOX_SOURCE_KIND,
        route_id=str(thread.id),
    )

    result = _read_inbox_message_impl(delivery.notification.id)

    assert result["success"] is False
    assert result["error_type"] == "InboxReadNotFoundError"
    assert "presence notification marker" in result["error"]


def test_reply_to_inbox_message_routes_through_provider_presence_registry(test_session):
    notification_id = _presence_notification()
    provider = FakePresenceProvider()
    presence_provider_manager.register_provider("example", provider)

    result = _reply_to_inbox_message_impl(notification_id, "Reply through CAO")

    assert result["success"] is True
    assert result["provider"] == "example"
    assert result["thread_id"] == "thread-1"
    assert result["outbound_message"]["external_id"] == "reply-1"
    assert provider.replies[0]["thread_ref"] == ExternalRef(
        provider="example",
        id="thread-1",
        url="https://presence.example/thread-1",
    )
    assert provider.replies[0]["metadata"]["inbox_notification_id"] == notification_id


def test_reply_to_inbox_message_ignores_agent_visible_breadcrumb_for_routing(test_session):
    work_item = upsert_work_item(
        provider="example",
        external_id="work-breadcrumb",
        identifier="CAO-39",
        title="Breadcrumb is presentation only",
    )
    thread = upsert_thread(
        provider="example",
        external_id="thread-route",
        external_url="https://presence.example/thread-route",
        work_item_id=work_item.id,
        kind="conversation",
    )
    message = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-route",
        direction="inbound",
        kind="prompt",
        body="Reply using hidden route data.",
        metadata=inbox_read_presentation_metadata(
            workspace={
                "name": "Example",
                "breadcrumb": {
                    "thread_id": "misleading-agent-visible-thread",
                    "issue": "CAO-39",
                },
            },
            source_label="Example Workspace",
        ),
    )
    notification_id = create_notification_for_message(
        presence_message_id=message.id,
        receiver_id="agent:example",
    ).delivery.notification.id
    provider = FakePresenceProvider()
    presence_provider_manager.register_provider("example", provider)

    result = _reply_to_inbox_message_impl(notification_id, "Routed reply")

    assert result["success"] is True
    assert provider.replies[0]["thread_ref"] == ExternalRef(
        provider="example",
        id="thread-route",
        url="https://presence.example/thread-route",
    )
    assert "misleading-agent-visible-thread" not in json.dumps(provider.replies[0]["metadata"])


def test_reply_to_inbox_message_registers_linear_provider_in_mcp_process(
    test_session,
    monkeypatch,
):
    notification_id = _linear_presence_notification()
    create_activity = Mock(return_value={"id": "reply-1"})
    monkeypatch.setattr(
        "cli_agent_orchestrator.presence.builtins._create_linear_presence_provider",
        lambda: LinearPresenceProvider(client=Mock(create_agent_activity=create_activity)),
    )

    read_result = _read_inbox_message_impl(notification_id)
    result = _reply_to_inbox_message_impl(notification_id, "Reply through default Linear provider")

    assert "implementation_partner" not in json.dumps(read_result)
    assert "provider_context" not in read_result
    assert result["success"] is True
    create_activity.assert_called_once_with(
        "session-1",
        {"type": "response", "body": "Reply through default Linear provider"},
        app_key="implementation_partner",
    )


def test_read_and_reply_fail_clearly_for_non_replyable_inbox_message(test_session):
    delivery = create_inbox_delivery("terminal-a", "terminal-b", "Plain terminal message")

    read_result = _read_inbox_message_impl(delivery.notification.id)
    reply_result = _reply_to_inbox_message_impl(delivery.notification.id, "No provider target")

    assert read_result == {
        "success": True,
        "notification_id": delivery.notification.id,
        "message_id": delivery.message.id,
        "from": "Terminal sender",
        "body": "Plain terminal message",
        "replyable": False,
        "workspace": None,
        "reply_error": "no provider reply route",
    }
    assert reply_result["success"] is False
    assert reply_result["error_type"] == "PresenceReplyUnsupportedSourceError"


def test_read_inbox_message_distinguishes_notification_without_backing_message(test_session):
    notification = create_inbox_notification_event(
        "agent:implementation_partner",
        "CAO-123 has new comments.",
        source_kind="linear_issue",
        source_id="CAO-123",
    )

    result = _read_inbox_message_impl(notification.id)

    assert result["success"] is False
    assert result["error_type"] == "InboxReadUnsupportedNotificationError"
    assert "not backed by a CAO message" in result["error"]


def test_agent_runtime_backed_message_is_slim_and_not_replyable(test_session):
    delivery = create_inbox_delivery(
        "linear-runtime",
        "agent:implementation_partner",
        "Agent runtime accepted a Linear event.",
        source_kind="linear_event",
        source_id="event-1",
    )

    read_result = _read_inbox_message_impl(delivery.notification.id)
    reply_result = _reply_to_inbox_message_impl(delivery.notification.id, "Reply to runtime event")

    assert read_result == {
        "success": True,
        "notification_id": delivery.notification.id,
        "message_id": delivery.message.id,
        "from": "Linear Event",
        "body": "Agent runtime accepted a Linear event.",
        "replyable": False,
        "workspace": None,
        "reply_error": "no provider reply route",
    }
    assert reply_result["success"] is False
    assert reply_result["error_type"] == "PresenceReplyUnsupportedSourceError"
    assert len(reply_result["error"]) < 180


def test_reply_to_inbox_message_surfaces_provider_failure(test_session):
    notification_id = _presence_notification()

    result = _reply_to_inbox_message_impl(notification_id, "No registered provider")

    assert result["success"] is False
    assert result["error_type"] == "PresenceReplyDeliveryError"
    assert result["failed_message_state"] == "failed"


def test_provider_reply_failure_response_and_record_do_not_leak_provider_context(
    test_session,
):
    notification_id = _presence_notification()
    presence_provider_manager.register_provider("example", LeakyFailurePresenceProvider())

    result = _reply_to_inbox_message_impl(notification_id, "Reply that fails")

    thread = get_thread("example", "thread-1")
    assert thread is not None
    failed_message = list_messages(thread.id)[-1]
    encoded_response = json.dumps(result)
    encoded_failed_metadata = json.dumps(failed_message.metadata)

    assert result["success"] is False
    assert result["error_type"] == "PresenceReplyDeliveryError"
    assert result["failed_message_state"] == "failed"
    assert "secret-token" not in encoded_response
    assert "correct horse battery staple" not in encoded_response
    assert "bearer-secret" not in encoded_response
    assert "refresh-secret" not in encoded_response
    assert "/tmp/provider.py" not in encoded_response
    assert "x" * 1000 not in encoded_response
    assert "secret-token" not in encoded_failed_metadata
    assert "correct horse battery staple" not in encoded_failed_metadata
    assert "bearer-secret" not in encoded_failed_metadata
    assert "refresh-secret" not in encoded_failed_metadata
    assert "/tmp/provider.py" not in encoded_failed_metadata
    assert len(result["error"]) < 360
    assert failed_message.metadata["error"].endswith("...")

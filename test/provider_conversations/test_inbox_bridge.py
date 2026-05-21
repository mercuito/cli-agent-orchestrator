"""Tests for bridging provider-owned messages into the terminal inbox."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.provider_conversations.inbox_bridge import (
    PROVIDER_CONVERSATION_INBOX_SOURCE_KIND,
    create_notification_for_message,
    create_notification_for_persisted_event,
)
from cli_agent_orchestrator.provider_conversations.models import PersistedProviderEventRecords
from cli_agent_orchestrator.provider_conversations.persistence import (
    upsert_message,
    upsert_thread,
    upsert_work_item,
)
from cli_agent_orchestrator.services.tool_service import ToolAccessDecision
from cli_agent_orchestrator.workspaces import WorkspaceConfigError

AUTHORIZED_AGENT_ID = "implementation_partner"
AUTHORIZED_RECEIVER_ID = f"agent:{AUTHORIZED_AGENT_ID}:context:default"


@pytest.fixture
def preview_tool_service(monkeypatch):
    service = _PreviewToolService()
    monkeypatch.setattr(
        "cli_agent_orchestrator.provider_conversations.inbox_bridge.default_tool_service",
        lambda: service,
    )
    return service


@pytest.fixture
def test_session(monkeypatch, preview_tool_service):
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
    TestSession = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


class _PreviewToolService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []
        self.decision = ToolAccessDecision.allow(reason="provider_conversation_allowed")
        self.decisions_by_operation: dict[str, ToolAccessDecision] = {}

    def provider_conversation_decision(self, *args, **kwargs) -> ToolAccessDecision:
        self.calls.append((args, kwargs))
        operation = str(kwargs.get("operation", "")).strip().lower()
        if operation in self.decisions_by_operation:
            return self.decisions_by_operation[operation]
        return self.decision


def _persist_message(
    *,
    provider: str = "example",
    thread_external_id: str = "thread-1",
    message_external_id: str = "message-1",
    body: str = "Please look at the failing handoff test.",
    metadata: dict | None = None,
    raw_snapshot: dict | None = None,
):
    work_item = upsert_work_item(
        provider=provider,
        external_id=f"work-{thread_external_id}",
        identifier="WORK-123",
        title="Bridge durable provider conversation into inbox",
    )
    thread = upsert_thread(
        provider=provider,
        external_id=thread_external_id,
        work_item_id=work_item.id,
        kind="work_item_discussion",
    )
    message = upsert_message(
        thread_id=thread.id,
        provider=provider,
        external_id=message_external_id,
        direction="inbound",
        kind="comment",
        body=body,
        raw_snapshot=raw_snapshot,
        metadata=metadata,
    )
    return work_item, thread, message


def test_provider_conversation_notification_uses_provider_message_source(
    test_session, preview_tool_service
):
    _, thread, message = _persist_message(
        provider="linear",
        metadata={"linear_app_key": "implementation_partner"},
    )

    result = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )

    assert result.created is True
    assert result.delivery.message.source_kind == PROVIDER_CONVERSATION_INBOX_SOURCE_KIND
    assert result.delivery.message.source_id == str(message.id)
    assert result.delivery.message.source_id != thread.external_id
    assert result.delivery.message.route_kind is None
    assert result.delivery.message.route_id is None
    assert result.delivery.notification.receiver_id == AUTHORIZED_RECEIVER_ID
    assert result.delivery.notification.status == MessageStatus.PENDING
    assert preview_tool_service.calls == [
        (
            (AUTHORIZED_AGENT_ID,),
            {
                "provider": "linear",
                "operation": "preview",
                "source": f"provider_conversation_message:{message.id}",
                "provider_identity": "implementation_partner",
            },
        ),
        (
            (AUTHORIZED_AGENT_ID,),
            {
                "provider": "linear",
                "operation": "reply",
                "source": f"provider_conversation_message:{message.id}",
                "provider_identity": "implementation_partner",
            },
        ),
    ]


def test_provider_conversation_notification_denies_preview_before_inbox_write(
    test_session, preview_tool_service
):
    _, _, message = _persist_message()
    preview_tool_service.decision = ToolAccessDecision.deny("provider_conversation_denied")

    with pytest.raises(WorkspaceConfigError, match="preview is not authorized"):
        create_notification_for_message(
            provider_message_id=message.id,
            receiver_id=AUTHORIZED_RECEIVER_ID,
            authorized_agent_id=AUTHORIZED_AGENT_ID,
        )

    with db_module.SessionLocal() as session:
        assert session.query(db_module.InboxNotificationModel).count() == 0


def test_notification_body_is_compact_and_source_points_at_provider_message(test_session):
    _, _, message = _persist_message(
        provider="generic-chat",
        body="The worker is blocked on a missing migration test.",
    )

    result = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )

    assert result.delivery.message is not None
    assert result.delivery.message.source_id == str(message.id)

    body = result.delivery.notification.body
    assert "[CAO inbox notification]" in body
    assert f"ID: {result.delivery.notification.id}" in body
    assert "Source: generic-chat" in body
    assert "Issue: WORK-123 - Bridge durable provider conversation into inbox" in body
    assert f"Read: read_inbox_message(notification_id={result.delivery.notification.id})" in body
    assert (
        f"Reply: reply_to_inbox_message(notification_id={result.delivery.notification.id}" in body
    )
    assert "missing migration test" in body


def test_notification_body_omits_reply_guidance_when_reply_tool_is_hidden(
    test_session, preview_tool_service
):
    _, _, message = _persist_message(
        provider="generic-chat",
        body="The worker only has preview access.",
    )
    preview_tool_service.decisions_by_operation["reply"] = ToolAccessDecision.deny(
        "reply_to_inbox_message is hidden"
    )

    result = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )

    body = result.delivery.notification.body
    assert f"Read: read_inbox_message(notification_id={result.delivery.notification.id})" in body
    assert "reply_to_inbox_message" not in body
    assert [call[1]["operation"] for call in preview_tool_service.calls] == [
        "preview",
        "reply",
    ]


def test_semantic_notification_body_is_bounded(test_session):
    _, _, message = _persist_message(
        body="Latest actionable line. "
        + "older transcript line that should not be copied wholesale " * 20,
    )

    result = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
        preview_chars=35,
        notification_chars=180,
    )

    assert len(result.delivery.notification.body) <= 180
    assert "Latest actionable line" in result.delivery.notification.body
    assert result.delivery.notification.body.count("older transcript line") <= 1
    assert result.delivery.message.source_id == str(message.id)


def test_duplicate_notification_for_same_receiver_and_provider_message_is_idempotent(
    test_session,
):
    _, _, message = _persist_message()

    first = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )
    second = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )

    assert first.created is True
    assert second.created is False
    assert second.delivery.notification.id == first.delivery.notification.id
    assert len(db_module.list_pending_inbox_notifications(AUTHORIZED_RECEIVER_ID, limit=10)) == 1
    with db_module.SessionLocal() as session:
        assert session.query(db_module.InboxNotificationModel).count() == 1


def test_persisted_event_wrapper_bridges_its_message(test_session):
    _, thread, message = _persist_message()

    result = create_notification_for_persisted_event(
        PersistedProviderEventRecords(
            processed_event=None, work_item=None, thread=None, message=message
        ),
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )

    assert result.created is True
    assert result.delivery.message.source_kind == PROVIDER_CONVERSATION_INBOX_SOURCE_KIND
    assert result.delivery.message.source_id == str(message.id)


def test_different_provider_conversation_threads_do_not_coalesce_into_same_source(test_session):
    _, first_thread, first_message = _persist_message(
        thread_external_id="thread-1",
        message_external_id="message-1",
    )
    _, second_thread, second_message = _persist_message(
        thread_external_id="thread-2",
        message_external_id="message-2",
    )

    first = create_notification_for_message(
        provider_message_id=first_message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )
    second = create_notification_for_message(
        provider_message_id=second_message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )

    assert first.delivery.message.source_id == str(first_message.id)
    assert second.delivery.message.source_id == str(second_message.id)
    assert first.delivery.message.source_id != second.delivery.message.source_id


def test_missing_provider_conversation_thread_or_message_fails_clearly(test_session):
    with pytest.raises(ValueError, match="provider conversation message 999 not found"):
        create_notification_for_message(
            provider_message_id=999,
            receiver_id=AUTHORIZED_RECEIVER_ID,
            authorized_agent_id=AUTHORIZED_AGENT_ID,
        )

    _, _, message = _persist_message()
    with db_module.SessionLocal() as session:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        session.query(db_module.ProviderConversationThreadModel).delete()
        session.commit()

    with pytest.raises(
        ValueError, match=f"provider conversation thread .* for message {message.id} not found"
    ):
        create_notification_for_message(
            provider_message_id=message.id,
            receiver_id=AUTHORIZED_RECEIVER_ID,
            authorized_agent_id=AUTHORIZED_AGENT_ID,
        )


def test_attachment_metadata_does_not_block_semantic_message(test_session):
    _, _, message = _persist_message(
        body="Text that should still notify.",
        metadata={"attachments": [{"content_type": "image/png", "name": "trace.png"}]},
    )

    result = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )

    assert result.created is True
    assert "Attachment/media metadata present." in result.delivery.notification.body
    assert result.delivery.message.origin == {
        "attachments": [{"content_type": "image/png", "name": "trace.png"}],
        "provider_thread_id": 1,
    }


def test_provider_conversation_notification_rejects_mismatched_receiver_agent(test_session):
    _, _, message = _persist_message()

    with pytest.raises(WorkspaceConfigError, match="not owned"):
        create_notification_for_message(
            provider_message_id=message.id,
            receiver_id="agent:other_agent:context:default",
            authorized_agent_id=AUTHORIZED_AGENT_ID,
        )


def test_semantic_message_origin_does_not_copy_raw_snapshot(test_session):
    _, _, message = _persist_message(
        body="Text that should still notify.",
        raw_snapshot={"author": {"name": "Raw Snapshot Author Should Not Leak"}},
        metadata=None,
    )

    result = create_notification_for_message(
        provider_message_id=message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )

    assert result.delivery.message.origin == {"provider_thread_id": 1}


def test_provider_conversation_sources_use_existing_inbox_batching_behavior(test_session):
    _, thread, first_message = _persist_message(
        message_external_id="message-1",
        body="First update",
    )
    second_message = upsert_message(
        thread_id=thread.id,
        provider="example",
        external_id="message-2",
        kind="comment",
        body="Second update",
    )

    first = create_notification_for_message(
        provider_message_id=first_message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )
    create_notification_for_message(
        provider_message_id=second_message.id,
        receiver_id=AUTHORIZED_RECEIVER_ID,
        authorized_agent_id=AUTHORIZED_AGENT_ID,
    )

    batch = db_module.list_pending_inbox_deliveries_for_effective_source(
        AUTHORIZED_RECEIVER_ID, first.delivery
    )

    assert [delivery.message.source_kind for delivery in batch] == [
        PROVIDER_CONVERSATION_INBOX_SOURCE_KIND,
    ]
    assert [delivery.message.source_id for delivery in batch] == [str(first_message.id)]
    assert [delivery.notification.id for delivery in batch] == [1]

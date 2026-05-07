"""Tests for the database client."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import (
    AgentRuntimeNotificationModel,
    Base,
    FlowModel,
    InboxMessageModel,
    InboxModel,
    InboxNotificationModel,
    TerminalModel,
    create_flow,
    create_inbox_delivery,
    create_inbox_message,
    create_inbox_message_record,
    create_inbox_notification,
    create_terminal,
    delete_flow,
    delete_terminal,
    delete_terminals_by_session,
    get_effective_message_source,
    get_flow,
    get_inbox_delivery,
    get_inbox_message,
    get_inbox_messages,
    get_oldest_pending_message,
    get_pending_messages,
    get_pending_messages_for_effective_source,
    get_terminal_metadata,
    init_db,
    list_flows,
    list_pending_inbox_notifications,
    list_terminals_by_session,
    update_flow_enabled,
    update_flow_run_times,
    update_inbox_notification_status,
    update_last_active,
    update_message_status,
    update_message_statuses,
)
from cli_agent_orchestrator.models.inbox import MessageStatus


@pytest.fixture
def test_db():
    """Create an in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    return TestSession


@pytest.fixture
def live_inbox_db(monkeypatch):
    """Create an isolated in-memory database wired into database helpers."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


class TestTerminalOperations:
    """Tests for terminal database operations."""

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_create_terminal(self, mock_session_class):
        """Test creating a terminal record."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session_class.return_value = mock_session

        result = create_terminal("test123", "cao-session", "window-0", "kiro_cli", "developer")

        assert result["id"] == "test123"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_get_terminal_metadata_found(self, mock_session_class):
        """Test getting terminal metadata that exists."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_terminal = MagicMock()
        mock_terminal.id = "test123"
        mock_terminal.tmux_session = "cao-session"
        mock_terminal.tmux_window = "window-0"
        mock_terminal.provider = "kiro_cli"
        mock_terminal.agent_profile = "developer"
        mock_terminal.allowed_tools = None
        mock_terminal.last_active = datetime.now()

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_terminal
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = get_terminal_metadata("test123")

        assert result is not None
        assert result["id"] == "test123"

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_get_terminal_metadata_not_found(self, mock_session_class):
        """Test getting terminal metadata that doesn't exist."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = get_terminal_metadata("nonexistent")

        assert result is None

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_update_last_active(self, mock_session_class):
        """Test updating last active timestamp."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_terminal = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_terminal
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        update_last_active("test123")

        mock_session.commit.assert_called_once()

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_delete_terminal(self, mock_session_class):
        """Test deleting a terminal."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.delete.return_value = 1
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = delete_terminal("test123")

        assert result is True
        mock_session.commit.assert_called_once()

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_delete_terminal_not_found(self, mock_session_class):
        """Test deleting a terminal that doesn't exist."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.delete.return_value = 0
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = delete_terminal("nonexistent")

        assert result is False

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_list_terminals_by_session(self, mock_session_class):
        """Test listing terminals by session."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_terminal = MagicMock()
        mock_terminal.id = "test123"
        mock_terminal.tmux_session = "cao-session"
        mock_terminal.tmux_window = "window-0"
        mock_terminal.provider = "kiro_cli"
        mock_terminal.agent_profile = "developer"
        mock_terminal.last_active = datetime.now()

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [mock_terminal]
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = list_terminals_by_session("cao-session")

        assert len(result) == 1
        assert result[0]["id"] == "test123"

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_delete_terminals_by_session(self, mock_session_class):
        """Test deleting all terminals in a session."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.delete.return_value = 2
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = delete_terminals_by_session("cao-session")

        assert result == 2


class TestInboxOperations:
    """Tests for inbox database operations."""

    def test_inbox_model_has_source_columns(self):
        """Inbox rows support provider-neutral source identity columns."""
        columns = {column.name for column in Base.metadata.tables["inbox"].columns}

        assert "source_kind" in columns
        assert "source_id" in columns

    def test_semantic_inbox_tables_are_declared(self):
        """The schema has separate durable message and notification tables."""
        message_columns = {column.name for column in Base.metadata.tables["inbox_messages"].columns}
        notification_columns = {
            column.name for column in Base.metadata.tables["inbox_notifications"].columns
        }

        assert {"body", "source_kind", "source_id", "origin_json", "route_kind", "route_id"} <= (
            message_columns
        )
        assert {"message_id", "receiver_id", "status", "legacy_inbox_id"} <= (notification_columns)

    def test_create_inbox_delivery_creates_one_message_and_one_notification(self, live_inbox_db):
        """New owner creation persists durable body separately from delivery state."""
        delivery = create_inbox_delivery(
            "sender-123",
            "receiver-456",
            "Hello",
            source_kind="linear_thread",
            source_id="thread-9",
            origin={"identifier": "CAO-37"},
            route_kind="presence_thread",
            route_id="linear:thread-9",
        )

        assert delivery.message.body == "Hello"
        assert delivery.message.source_kind == "linear_thread"
        assert delivery.message.origin == {"identifier": "CAO-37"}
        assert delivery.message.route_kind == "presence_thread"
        assert delivery.notification.receiver_id == "receiver-456"
        assert delivery.notification.status == MessageStatus.PENDING
        assert delivery.notification.legacy_inbox_id is None

        with live_inbox_db() as session:
            assert session.query(InboxMessageModel).count() == 1
            assert session.query(InboxNotificationModel).count() == 1
            assert session.query(InboxModel).count() == 0

    def test_message_and_notification_can_be_created_as_separate_owner_steps(self, live_inbox_db):
        """The owner surface supports explicit durable message then notification creation."""
        message = create_inbox_message_record(
            "sender-123",
            "Hello",
            source_kind="external",
            source_id="thread-9",
        )
        notification = create_inbox_notification(message.id, "receiver-456")

        delivery = get_inbox_delivery(notification.id)

        assert delivery.message == message
        assert delivery.notification == notification

    def test_create_notification_rejects_missing_message(self, live_inbox_db):
        """Notifications must point at an existing durable message."""
        with pytest.raises(ValueError, match="Inbox message not found"):
            create_inbox_notification(999, "receiver-456")

    def test_create_inbox_message_wrapper_returns_compatible_shape(self, live_inbox_db):
        """Old creation returns InboxMessage while semantic rows own new data."""
        result = create_inbox_message("sender-123", "receiver-456", "Hello")

        assert result.sender_id == "sender-123"
        assert result.receiver_id == "receiver-456"
        assert result.message == "Hello"
        assert result.source_kind == "terminal"
        assert result.source_id == "sender-123"
        assert result.status == MessageStatus.PENDING

        assert get_inbox_message(result.id) == result
        assert get_inbox_messages("receiver-456") == [result]

        with live_inbox_db() as session:
            notification = session.query(InboxNotificationModel).one()
            durable_message = session.query(InboxMessageModel).one()
            legacy_row = session.query(InboxModel).one()

        assert notification.message_id == durable_message.id
        assert notification.legacy_inbox_id == legacy_row.id == result.id

    def test_semantic_only_delivery_uses_semantic_helpers(self, live_inbox_db):
        """Semantic-only deliveries stay out of legacy compatibility helpers."""
        delivery = create_inbox_delivery(
            "agent:linear",
            "agent:implementation_partner",
            "Please inspect the failing job.",
            source_kind="presence_message",
            source_id="linear:comment-1",
            origin={"breadcrumb": "Linear / CAO-37"},
            route_kind="linear_comment",
            route_id="comment-1",
        )

        listed = get_inbox_messages("agent:implementation_partner")
        pending = list_pending_inbox_notifications("agent:implementation_partner")
        read = get_inbox_delivery(delivery.notification.id)

        assert listed == []
        assert get_inbox_message(delivery.notification.id) is None
        assert pending[0].message.body == "Please inspect the failing job."
        assert "comment-1" not in pending[0].message.body
        assert pending == [delivery]
        assert read == delivery

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_update_message_status(self, mock_session_class):
        """Test updating message status."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_message = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_message
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        update_message_status(1, MessageStatus.DELIVERED)

        mock_session.commit.assert_called_once()

    def test_create_inbox_message_defaults_source_to_sender_terminal(self, live_inbox_db):
        """New agent-to-agent messages default to terminal:<sender_id>."""
        result = create_inbox_message("sender-123", "receiver-456", "Hello")

        assert result.source_kind == "terminal"
        assert result.source_id == "sender-123"

        persisted = get_inbox_messages("receiver-456")[0]
        assert persisted.source_kind == "terminal"
        assert persisted.source_id == "sender-123"

    def test_get_inbox_message_reads_one_message_by_id(self, live_inbox_db):
        result = create_inbox_message("sender-123", "receiver-456", "Hello")

        persisted = get_inbox_message(result.id)

        assert persisted is not None
        assert persisted.id == result.id
        assert persisted.message == "Hello"
        assert get_inbox_message(999) is None

    def test_create_inbox_message_persists_explicit_source(self, live_inbox_db):
        """Callers can provide a non-terminal provider-neutral source."""
        result = create_inbox_message(
            "sender-123",
            "receiver-456",
            "Hello",
            source_kind="external",
            source_id="thread-9",
        )

        assert result.source_kind == "external"
        assert result.source_id == "thread-9"
        assert get_effective_message_source(result).kind == "external"
        assert get_effective_message_source(result).id == "thread-9"
        assert get_effective_message_source(result).is_legacy_message is False

    def test_create_inbox_message_rejects_partial_source(self, live_inbox_db):
        """Source identity must be complete so incomplete rows do not masquerade as legacy."""
        with pytest.raises(ValueError, match="source_kind and source_id"):
            create_inbox_message(
                "sender-123",
                "receiver-456",
                "Hello",
                source_kind="external",
            )

        with pytest.raises(ValueError, match="source_kind and source_id"):
            create_inbox_message(
                "sender-123",
                "receiver-456",
                "Hello",
                source_id="thread-9",
            )

    def test_semantic_create_rejects_partial_source_or_route(self, live_inbox_db):
        """Semantic input boundaries fail clearly for incomplete identities."""
        with pytest.raises(ValueError, match="source_kind and source_id"):
            create_inbox_delivery(
                "sender-123",
                "receiver-456",
                "Hello",
                source_kind="external",
            )

        with pytest.raises(ValueError, match="route_kind and route_id"):
            create_inbox_delivery(
                "sender-123",
                "receiver-456",
                "Hello",
                route_kind="presence_thread",
            )

    def test_legacy_no_source_messages_remain_deliverable(self, live_inbox_db):
        """No-source rows are selected as a unique per-message source."""
        with live_inbox_db() as session:
            row = InboxModel(
                sender_id="old-sender",
                receiver_id="receiver-456",
                message="legacy",
                status=MessageStatus.PENDING.value,
                created_at=datetime(2026, 1, 1, 9, 0, 0),
            )
            session.add(row)
            session.commit()

        oldest = get_oldest_pending_message("receiver-456")
        assert oldest is not None
        assert oldest.source_kind is None
        assert oldest.source_id is None

        batch = get_pending_messages_for_effective_source("receiver-456", oldest)
        assert [message.message for message in batch] == ["legacy"]
        source = get_effective_message_source(oldest)
        assert source.kind == "legacy_message"
        assert source.id == str(oldest.id)
        assert source.is_legacy_message is True

    def test_legacy_old_table_rows_remain_readable_listable_and_deliverable(self, live_inbox_db):
        """Rows with no semantic notification keep the old compatibility behavior."""
        with live_inbox_db() as session:
            row = InboxModel(
                sender_id="old-sender",
                receiver_id="receiver-456",
                message="legacy only",
                status=MessageStatus.PENDING.value,
                created_at=datetime(2026, 1, 1, 9, 0, 0),
            )
            session.add(row)
            session.commit()
            legacy_id = row.id

        assert get_inbox_message(legacy_id).message == "legacy only"
        assert [message.id for message in get_inbox_messages("receiver-456")] == [legacy_id]

        oldest = get_oldest_pending_message("receiver-456")
        batch = get_pending_messages_for_effective_source("receiver-456", oldest)
        assert [message.message for message in batch] == ["legacy only"]

        assert update_message_status(legacy_id, MessageStatus.DELIVERED) is True
        assert get_inbox_message(legacy_id).status == MessageStatus.DELIVERED

    def test_status_updates_mutate_notification_not_durable_message(self, live_inbox_db):
        """Delivery status changes stay on notification rows."""
        result = create_inbox_message(
            "sender-123",
            "receiver-456",
            "Original body",
            source_kind="external",
            source_id="thread-9",
        )

        assert update_message_statuses([result.id], MessageStatus.DELIVERED) == 1

        with live_inbox_db() as session:
            durable_message = session.query(InboxMessageModel).one()
            notification = session.query(InboxNotificationModel).one()
            legacy_row = session.query(InboxModel).one()

        assert durable_message.body == "Original body"
        assert durable_message.source_kind == "external"
        assert notification.status == MessageStatus.DELIVERED.value
        assert notification.delivered_at is not None
        assert legacy_row.status == MessageStatus.DELIVERED.value

    def test_compatibility_list_honors_legacy_receiver_moves(self, live_inbox_db):
        """Old callers that move legacy rows still see the compatibility delivery move."""
        result = create_inbox_message("sender-123", "agent:worker", "Offline hello")

        with live_inbox_db() as session:
            legacy_row = session.get(InboxModel, result.id)
            legacy_row.receiver_id = "terminal-1"
            session.commit()

        assert get_inbox_messages("agent:worker", limit=10) == []
        moved = get_inbox_messages("terminal-1", limit=10)
        assert len(moved) == 1
        assert moved[0].receiver_id == "terminal-1"
        assert moved[0].message == "Offline hello"

    def test_semantic_notification_status_update_uses_notification_id(self, live_inbox_db):
        """New delivery-state helper updates notification ids directly."""
        delivery = create_inbox_delivery("sender-123", "receiver-456", "Hello")

        assert update_inbox_notification_status(
            delivery.notification.id, MessageStatus.FAILED, error_detail="send failed"
        )

        updated = get_inbox_delivery(delivery.notification.id)
        assert updated.notification.status == MessageStatus.FAILED
        assert updated.notification.failed_at is not None
        assert updated.notification.error_detail == "send failed"

    def test_compatibility_reads_use_notification_status_for_mapped_rows(self, live_inbox_db):
        """Legacy-shaped reads still treat notification status as delivery state."""
        result = create_inbox_message("sender-123", "receiver-456", "Hello")
        with live_inbox_db() as session:
            notification = session.query(InboxNotificationModel).one()
            notification_id = notification.id

        assert update_inbox_notification_status(notification_id, MessageStatus.FAILED)

        assert get_inbox_message(result.id).status == MessageStatus.FAILED
        assert get_inbox_messages("receiver-456", status=MessageStatus.PENDING) == []
        failed_messages = get_inbox_messages("receiver-456", status=MessageStatus.FAILED)
        assert [message.id for message in failed_messages] == [result.id]

    def test_legacy_id_collision_does_not_make_old_reads_return_semantic_delivery(
        self, live_inbox_db
    ):
        """Old get helpers stay in legacy inbox.id space when notification ids collide."""
        semantic_delivery = create_inbox_delivery(
            "semantic-sender", "semantic-receiver", "Semantic"
        )
        legacy_result = create_inbox_message("legacy-sender", "legacy-receiver", "Legacy")

        assert semantic_delivery.notification.id == legacy_result.id

        legacy_read = get_inbox_message(legacy_result.id)

        assert legacy_read.message == "Legacy"
        assert legacy_read.receiver_id == "legacy-receiver"
        assert get_inbox_messages("semantic-receiver") == []
        assert [message.message for message in get_inbox_messages("legacy-receiver")] == ["Legacy"]
        assert get_inbox_delivery(semantic_delivery.notification.id) == semantic_delivery

    def test_legacy_id_collision_status_update_does_not_touch_semantic_notification(
        self, live_inbox_db
    ):
        """Old status helpers update legacy/mirrored rows, not raw notification ids."""
        semantic_delivery = create_inbox_delivery(
            "semantic-sender", "semantic-receiver", "Semantic"
        )
        legacy_result = create_inbox_message("legacy-sender", "legacy-receiver", "Legacy")

        assert semantic_delivery.notification.id == legacy_result.id
        assert update_message_statuses([legacy_result.id], MessageStatus.DELIVERED) == 1

        semantic_after_update = get_inbox_delivery(semantic_delivery.notification.id)
        legacy_after_update = get_inbox_message(legacy_result.id)

        assert semantic_after_update.notification.status == MessageStatus.PENDING
        assert legacy_after_update.status == MessageStatus.DELIVERED

    def test_same_source_pending_messages_are_batched_in_created_order(self, live_inbox_db):
        """Messages sharing an explicit source are selected together."""
        with live_inbox_db() as session:
            session.add_all(
                [
                    InboxModel(
                        sender_id="worker-a",
                        receiver_id="supervisor",
                        message="first",
                        source_kind="terminal",
                        source_id="worker-a",
                        status=MessageStatus.PENDING.value,
                        created_at=datetime(2026, 1, 1, 9, 0, 0),
                    ),
                    InboxModel(
                        sender_id="worker-a",
                        receiver_id="supervisor",
                        message="second",
                        source_kind="terminal",
                        source_id="worker-a",
                        status=MessageStatus.PENDING.value,
                        created_at=datetime(2026, 1, 1, 9, 2, 0),
                    ),
                ]
            )
            session.commit()

        oldest = get_oldest_pending_message("supervisor")
        assert oldest is not None
        batch = get_pending_messages_for_effective_source("supervisor", oldest)

        assert [message.message for message in batch] == ["first", "second"]

    def test_effective_source_batching_distinguishes_semantic_provider_sources(self, live_inbox_db):
        """Compatibility batching separates terminal and provider-backed source refs."""
        create_inbox_message(
            "terminal-a",
            "supervisor",
            "terminal message",
            source_kind="terminal",
            source_id="terminal-a",
        )
        create_inbox_message(
            "linear",
            "supervisor",
            "provider first",
            source_kind="presence_message",
            source_id="linear-thread-1",
        )
        create_inbox_message(
            "linear",
            "supervisor",
            "provider second",
            source_kind="presence_message",
            source_id="linear-thread-1",
        )

        messages = get_inbox_messages("supervisor", limit=10)
        terminal_message = messages[0]
        provider_message = messages[1]

        terminal_batch = get_pending_messages_for_effective_source("supervisor", terminal_message)
        provider_batch = get_pending_messages_for_effective_source("supervisor", provider_message)

        assert [message.message for message in terminal_batch] == ["terminal message"]
        assert [message.message for message in provider_batch] == [
            "provider first",
            "provider second",
        ]

    def test_explicit_source_kind_cannot_collide_with_legacy_marker(self, live_inbox_db):
        """Provider-neutral source strings are not reserved for internal sentinels."""
        with live_inbox_db() as session:
            session.add_all(
                [
                    InboxModel(
                        sender_id="external-a",
                        receiver_id="supervisor",
                        message="first",
                        source_kind="legacy_message",
                        source_id="external-1",
                        status=MessageStatus.PENDING.value,
                        created_at=datetime(2026, 1, 1, 9, 0, 0),
                    ),
                    InboxModel(
                        sender_id="external-a",
                        receiver_id="supervisor",
                        message="second",
                        source_kind="legacy_message",
                        source_id="external-1",
                        status=MessageStatus.PENDING.value,
                        created_at=datetime(2026, 1, 1, 9, 1, 0),
                    ),
                ]
            )
            session.commit()

        oldest = get_oldest_pending_message("supervisor")
        assert oldest is not None
        source = get_effective_message_source(oldest)
        assert source.kind == "legacy_message"
        assert source.id == "external-1"
        assert source.is_legacy_message is False

        batch = get_pending_messages_for_effective_source("supervisor", oldest)
        assert [message.message for message in batch] == ["first", "second"]

    def test_different_sources_are_not_batched_with_oldest_source(self, live_inbox_db):
        """A later pending message from another source stays out of the selected batch."""
        with live_inbox_db() as session:
            session.add_all(
                [
                    InboxModel(
                        sender_id="worker-a",
                        receiver_id="supervisor",
                        message="oldest source",
                        source_kind="terminal",
                        source_id="worker-a",
                        status=MessageStatus.PENDING.value,
                        created_at=datetime(2026, 1, 1, 9, 0, 0),
                    ),
                    InboxModel(
                        sender_id="worker-b",
                        receiver_id="supervisor",
                        message="other source",
                        source_kind="terminal",
                        source_id="worker-b",
                        status=MessageStatus.PENDING.value,
                        created_at=datetime(2026, 1, 1, 9, 1, 0),
                    ),
                    InboxModel(
                        sender_id="worker-a",
                        receiver_id="supervisor",
                        message="same source later",
                        source_kind="terminal",
                        source_id="worker-a",
                        status=MessageStatus.PENDING.value,
                        created_at=datetime(2026, 1, 1, 9, 2, 0),
                    ),
                ]
            )
            session.commit()

        oldest = get_oldest_pending_message("supervisor")
        assert oldest is not None
        batch = get_pending_messages_for_effective_source("supervisor", oldest)

        assert [message.message for message in batch] == ["oldest source", "same source later"]

    def test_batch_status_update_marks_only_selected_messages(self, live_inbox_db):
        """Batch status updates leave unselected later messages pending."""
        selected = []
        with live_inbox_db() as session:
            rows = [
                InboxModel(
                    sender_id="worker-a",
                    receiver_id="supervisor",
                    message="selected one",
                    source_kind="terminal",
                    source_id="worker-a",
                    status=MessageStatus.PENDING.value,
                    created_at=datetime(2026, 1, 1, 9, 0, 0),
                ),
                InboxModel(
                    sender_id="worker-a",
                    receiver_id="supervisor",
                    message="selected two",
                    source_kind="terminal",
                    source_id="worker-a",
                    status=MessageStatus.PENDING.value,
                    created_at=datetime(2026, 1, 1, 9, 1, 0),
                ),
                InboxModel(
                    sender_id="worker-b",
                    receiver_id="supervisor",
                    message="still pending",
                    source_kind="terminal",
                    source_id="worker-b",
                    status=MessageStatus.PENDING.value,
                    created_at=datetime(2026, 1, 1, 9, 2, 0),
                ),
            ]
            session.add_all(rows)
            session.commit()
            selected = [rows[0].id, rows[1].id]

        updated = update_message_statuses(selected, MessageStatus.DELIVERED)
        assert updated == 2

        messages = get_inbox_messages("supervisor", limit=10)
        assert [message.status for message in messages] == [
            MessageStatus.DELIVERED,
            MessageStatus.DELIVERED,
            MessageStatus.PENDING,
        ]


class TestFlowOperations:
    """Tests for flow database operations."""

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_get_flow_not_found(self, mock_session_class):
        """Test getting a flow that doesn't exist."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = get_flow("nonexistent")

        assert result is None

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_update_flow_enabled(self, mock_session_class):
        """Test updating flow enabled status."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_flow = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_flow
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        update_flow_enabled("test-flow", False)

        mock_session.commit.assert_called_once()

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_update_flow_run_times(self, mock_session_class):
        """Test updating flow run times."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_flow = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_flow
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = update_flow_run_times("test-flow", datetime.now(), datetime.now())

        assert result is True
        mock_session.commit.assert_called_once()

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_update_flow_run_times_not_found(self, mock_session_class):
        """Test updating flow run times when flow doesn't exist."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = update_flow_run_times("nonexistent", datetime.now(), datetime.now())

        assert result is False

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_update_flow_enabled_not_found(self, mock_session_class):
        """Test updating flow enabled when flow doesn't exist."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = update_flow_enabled("nonexistent", False)

        assert result is False

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_update_flow_enabled_with_next_run(self, mock_session_class):
        """Test updating flow enabled with next_run."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_flow = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_flow
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        next_run = datetime.now()
        result = update_flow_enabled("test-flow", True, next_run=next_run)

        assert result is True
        assert mock_flow.next_run == next_run

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_create_flow(self, mock_session_class):
        """Test creating a flow."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session_class.return_value = mock_session

        # Setup mock to update flow attributes on refresh
        def mock_refresh(flow):
            flow.name = "test-flow"
            flow.file_path = "/path/to/file.yaml"
            flow.schedule = "0 * * * *"
            flow.agent_profile = "developer"
            flow.provider = "kiro_cli"
            flow.script = "echo test"
            flow.next_run = datetime.now()
            flow.last_run = None
            flow.enabled = True

        mock_session.refresh.side_effect = mock_refresh

        from cli_agent_orchestrator.clients.database import get_flows_to_run

        next_run = datetime.now()
        result = create_flow(
            name="test-flow",
            file_path="/path/to/file.yaml",
            schedule="0 * * * *",
            agent_profile="developer",
            provider="kiro_cli",
            script="echo test",
            next_run=next_run,
        )

        assert result.name == "test-flow"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_get_flow_found(self, mock_session_class):
        """Test getting a flow that exists."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_flow = MagicMock()
        mock_flow.name = "test-flow"
        mock_flow.file_path = "/path/to/file.yaml"
        mock_flow.schedule = "0 * * * *"
        mock_flow.agent_profile = "developer"
        mock_flow.provider = "kiro_cli"
        mock_flow.script = "echo test"
        mock_flow.last_run = None
        mock_flow.next_run = datetime.now()
        mock_flow.enabled = True

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_flow
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = get_flow("test-flow")

        assert result is not None
        assert result.name == "test-flow"

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_list_flows(self, mock_session_class):
        """Test listing all flows."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_flow = MagicMock()
        mock_flow.name = "test-flow"
        mock_flow.file_path = "/path/to/file.yaml"
        mock_flow.schedule = "0 * * * *"
        mock_flow.agent_profile = "developer"
        mock_flow.provider = "kiro_cli"
        mock_flow.script = "echo test"
        mock_flow.last_run = None
        mock_flow.next_run = datetime.now()
        mock_flow.enabled = True

        mock_query = MagicMock()
        mock_query.order_by.return_value.all.return_value = [mock_flow]
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = list_flows()

        assert len(result) == 1
        assert result[0].name == "test-flow"

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_delete_flow(self, mock_session_class):
        """Test deleting a flow."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.delete.return_value = 1
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = delete_flow("test-flow")

        assert result is True
        mock_session.commit.assert_called_once()

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_delete_flow_not_found(self, mock_session_class):
        """Test deleting a flow that doesn't exist."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.delete.return_value = 0
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = delete_flow("nonexistent")

        assert result is False

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_get_flows_to_run(self, mock_session_class):
        """Test getting flows that are due to run."""
        from cli_agent_orchestrator.clients.database import get_flows_to_run

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_flow = MagicMock()
        mock_flow.name = "due-flow"
        mock_flow.file_path = "/path/to/file.yaml"
        mock_flow.schedule = "0 * * * *"
        mock_flow.agent_profile = "developer"
        mock_flow.provider = "kiro_cli"
        mock_flow.script = "echo test"
        mock_flow.last_run = None
        mock_flow.next_run = datetime.now()
        mock_flow.enabled = True

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [mock_flow]
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = get_flows_to_run()

        assert len(result) == 1
        assert result[0].name == "due-flow"

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_update_last_active_not_found(self, mock_session_class):
        """Test updating last active when terminal doesn't exist."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = update_last_active("nonexistent")

        assert result is False

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_update_message_status_not_found(self, mock_session_class):
        """Test updating message status when message doesn't exist."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = update_message_status(999, MessageStatus.DELIVERED)

        assert result is False

    def test_create_inbox_message(self, live_inbox_db):
        """Test creating an inbox message."""
        result = create_inbox_message("sender-123", "receiver-456", "Hello")

        assert result.sender_id == "sender-123"
        assert result.receiver_id == "receiver-456"
        assert result.message == "Hello"
        assert get_inbox_message(result.id) == result


class TestInitDb:
    """Tests for init_db function."""

    @patch("cli_agent_orchestrator.clients.database.Base")
    def test_init_db(self, mock_base):
        """Test database initialization."""
        init_db()

        mock_base.metadata.create_all.assert_called_once()

    def test_semantic_inbox_migration_creates_tables_idempotently(self, tmp_path, monkeypatch):
        """Existing databases get the new semantic inbox tables safely."""
        db_path = tmp_path / "existing.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)

        db_module._migrate_ensure_semantic_inbox_tables()
        db_module._migrate_ensure_semantic_inbox_tables()

        table_names = inspect(test_engine).get_table_names()
        assert table_names.count("inbox_messages") == 1
        assert table_names.count("inbox_notifications") == 1

    def test_agent_runtime_migration_relaxes_legacy_inbox_message_not_null(
        self, tmp_path, monkeypatch
    ):
        """Old runtime marker tables allow semantic-only marker inserts after migration."""
        db_path = tmp_path / "legacy-runtime.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        TestSession = sessionmaker(bind=test_engine)
        monkeypatch.setattr(db_module, "engine", test_engine)
        monkeypatch.setattr(db_module, "SessionLocal", TestSession)
        monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

        InboxModel.__table__.create(bind=test_engine)
        InboxMessageModel.__table__.create(bind=test_engine)
        InboxNotificationModel.__table__.create(bind=test_engine)
        with test_engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE agent_runtime_notifications (
                    id INTEGER NOT NULL,
                    agent_id VARCHAR NOT NULL,
                    source_kind VARCHAR NOT NULL,
                    source_id VARCHAR NOT NULL,
                    inbox_message_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE (agent_id, source_kind, source_id),
                    FOREIGN KEY(inbox_message_id) REFERENCES inbox (id) ON DELETE CASCADE
                )
            """)

        db_module._migrate_ensure_agent_runtime_tables()

        with test_engine.connect() as connection:
            columns = {
                row[1]: row
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(agent_runtime_notifications)"
                )
            }
        assert "inbox_notification_id" in columns
        assert columns["inbox_message_id"][3] == 0

        delivery = create_inbox_delivery(
            "linear-runtime",
            "agent-123",
            "Runtime notification",
            source_kind="linear_issue",
            source_id="CAO-38",
        )
        with TestSession() as session:
            marker = AgentRuntimeNotificationModel(
                agent_id="agent-123",
                source_kind="linear_issue",
                source_id="CAO-38",
                inbox_notification_id=delivery.notification.id,
            )
            session.add(marker)
            session.commit()
            session.refresh(marker)

            assert marker.inbox_message_id is None
            assert marker.inbox_notification_id == delivery.notification.id

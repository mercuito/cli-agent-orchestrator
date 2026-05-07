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
    Base,
    FlowModel,
    InboxMessageModel,
    InboxNotificationModel,
    PresenceMessageModel,
    PresenceThreadModel,
    TerminalModel,
    create_flow,
    create_inbox_delivery,
    create_inbox_message_record,
    create_inbox_notification,
    create_terminal,
    delete_flow,
    delete_terminal,
    delete_terminals_by_session,
    get_flow,
    get_inbox_delivery,
    get_terminal_metadata,
    init_db,
    list_flows,
    list_inbox_deliveries,
    list_pending_inbox_notifications,
    list_terminals_by_session,
    update_flow_enabled,
    update_flow_run_times,
    update_inbox_notification_status,
    update_last_active,
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

    def test_semantic_inbox_tables_are_declared(self):
        """The schema has separate durable message and notification tables."""
        message_columns = {column.name for column in Base.metadata.tables["inbox_messages"].columns}
        notification_columns = {
            column.name for column in Base.metadata.tables["inbox_notifications"].columns
        }

        assert {"body", "source_kind", "source_id", "origin_json", "route_kind", "route_id"} <= (
            message_columns
        )
        assert {"message_id", "receiver_id", "status"} <= notification_columns
        assert "legacy_inbox_id" not in notification_columns
        assert "inbox" not in Base.metadata.tables

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

        with live_inbox_db() as session:
            assert session.query(InboxMessageModel).count() == 1
            assert session.query(InboxNotificationModel).count() == 1

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

    def test_list_inbox_deliveries_reads_semantic_notifications(self, live_inbox_db):
        """Receiver listing returns notification-backed durable messages."""
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

        listed = list_inbox_deliveries("agent:implementation_partner")
        pending = list_pending_inbox_notifications("agent:implementation_partner")
        read = get_inbox_delivery(delivery.notification.id)

        assert listed == [delivery]
        assert pending[0].message.body == "Please inspect the failing job."
        assert "comment-1" not in pending[0].message.body
        assert pending == [delivery]
        assert read == delivery

    def test_create_inbox_delivery_defaults_source_to_sender_terminal(self, live_inbox_db):
        """New agent-to-agent messages default to terminal:<sender_id>."""
        delivery = create_inbox_delivery("sender-123", "receiver-456", "Hello")

        assert delivery.message.source_kind == "terminal"
        assert delivery.message.source_id == "sender-123"

        persisted = list_inbox_deliveries("receiver-456")[0]
        assert persisted.message.source_kind == "terminal"
        assert persisted.message.source_id == "sender-123"

    def test_get_inbox_delivery_reads_one_notification_by_id(self, live_inbox_db):
        delivery = create_inbox_delivery("sender-123", "receiver-456", "Hello")

        persisted = get_inbox_delivery(delivery.notification.id)

        assert persisted == delivery
        assert get_inbox_delivery(999) is None

    def test_create_inbox_delivery_persists_explicit_source(self, live_inbox_db):
        """Callers can provide a non-terminal provider-neutral source."""
        delivery = create_inbox_delivery(
            "sender-123",
            "receiver-456",
            "Hello",
            source_kind="external",
            source_id="thread-9",
        )

        assert delivery.message.source_kind == "external"
        assert delivery.message.source_id == "thread-9"

    def test_create_inbox_delivery_rejects_partial_source(self, live_inbox_db):
        """Source identity must be complete so incomplete rows do not masquerade as legacy."""
        with pytest.raises(ValueError, match="source_kind and source_id"):
            create_inbox_delivery(
                "sender-123",
                "receiver-456",
                "Hello",
                source_kind="external",
            )

        with pytest.raises(ValueError, match="source_kind and source_id"):
            create_inbox_delivery(
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

    def test_status_updates_mutate_notification_not_durable_message(self, live_inbox_db):
        """Delivery status changes stay on notification rows."""
        delivery = create_inbox_delivery(
            "sender-123",
            "receiver-456",
            "Original body",
            source_kind="external",
            source_id="thread-9",
        )

        assert update_inbox_notification_status(delivery.notification.id, MessageStatus.DELIVERED)

        with live_inbox_db() as session:
            durable_message = session.query(InboxMessageModel).one()
            notification = session.query(InboxNotificationModel).one()

        assert durable_message.body == "Original body"
        assert durable_message.source_kind == "external"
        assert notification.status == MessageStatus.DELIVERED.value
        assert notification.delivered_at is not None

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

    def test_same_source_pending_messages_are_batched_in_created_order(self, live_inbox_db):
        """Messages sharing an explicit source are selected together."""
        first = create_inbox_delivery("worker-a", "supervisor", "first")
        second = create_inbox_delivery("worker-a", "supervisor", "second")

        oldest = db_module.get_oldest_pending_inbox_delivery("supervisor")
        assert oldest is not None
        batch = db_module.list_pending_inbox_deliveries_for_effective_source("supervisor", oldest)

        assert [delivery.message.body for delivery in batch] == ["first", "second"]
        assert [delivery.notification.id for delivery in batch] == [
            first.notification.id,
            second.notification.id,
        ]

    def test_effective_source_batching_distinguishes_semantic_provider_sources(self, live_inbox_db):
        """Batching separates terminal and provider-backed source refs."""
        create_inbox_delivery(
            "terminal-a",
            "supervisor",
            "terminal message",
            source_kind="terminal",
            source_id="terminal-a",
        )
        create_inbox_delivery(
            "linear",
            "supervisor",
            "provider first",
            source_kind="presence_message",
            source_id="linear-thread-1",
        )
        create_inbox_delivery(
            "linear",
            "supervisor",
            "provider second",
            source_kind="presence_message",
            source_id="linear-thread-1",
        )

        deliveries = list_inbox_deliveries("supervisor", limit=10)
        terminal_delivery = deliveries[0]
        provider_delivery = deliveries[1]

        terminal_batch = db_module.list_pending_inbox_deliveries_for_effective_source(
            "supervisor", terminal_delivery
        )
        provider_batch = db_module.list_pending_inbox_deliveries_for_effective_source(
            "supervisor", provider_delivery
        )

        assert [delivery.message.body for delivery in terminal_batch] == ["terminal message"]
        assert [delivery.message.body for delivery in provider_batch] == [
            "provider first",
            "provider second",
        ]

    def test_different_sources_are_not_batched_with_oldest_source(self, live_inbox_db):
        """A later pending message from another source stays out of the selected batch."""
        create_inbox_delivery("worker-a", "supervisor", "oldest source")
        create_inbox_delivery("worker-b", "supervisor", "other source")
        create_inbox_delivery("worker-a", "supervisor", "same source later")

        oldest = db_module.get_oldest_pending_inbox_delivery("supervisor")
        assert oldest is not None
        batch = db_module.list_pending_inbox_deliveries_for_effective_source("supervisor", oldest)

        assert [delivery.message.body for delivery in batch] == [
            "oldest source",
            "same source later",
        ]

    def test_batch_status_update_marks_only_selected_messages(self, live_inbox_db):
        """Batch status updates leave unselected later messages pending."""
        selected_one = create_inbox_delivery("worker-a", "supervisor", "selected one")
        selected_two = create_inbox_delivery("worker-a", "supervisor", "selected two")
        create_inbox_delivery("worker-b", "supervisor", "still pending")

        updated = db_module.update_inbox_notification_statuses(
            [selected_one.notification.id, selected_two.notification.id],
            MessageStatus.DELIVERED,
        )
        assert updated == 2

        deliveries = list_inbox_deliveries("supervisor", limit=10)
        assert [delivery.notification.status for delivery in deliveries] == [
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

    def test_notification_marker_migrations_translate_legacy_inbox_ids(self, tmp_path, monkeypatch):
        """Old marker tables are rebuilt around notification ids before legacy ids drop."""
        db_path = tmp_path / "legacy-markers.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)
        monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

        InboxMessageModel.__table__.create(bind=test_engine)
        PresenceThreadModel.__table__.create(bind=test_engine)
        PresenceMessageModel.__table__.create(bind=test_engine)
        with test_engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE inbox_notifications (
                    id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    receiver_id VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL,
                    delivered_at DATETIME,
                    failed_at DATETIME,
                    error_detail TEXT,
                    legacy_inbox_id INTEGER UNIQUE,
                    PRIMARY KEY (id)
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO inbox_messages (
                    id,
                    sender_id,
                    body,
                    source_kind,
                    source_id,
                    created_at
                )
                VALUES (
                    201,
                    'linear-runtime',
                    'Runtime notification',
                    'linear_issue',
                    'CAO-38',
                    '2026-05-07 12:00:00'
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO inbox_notifications (
                    id,
                    message_id,
                    receiver_id,
                    status,
                    created_at,
                    legacy_inbox_id
                )
                VALUES (301, 201, 'agent-123', 'pending', '2026-05-07 12:00:00', 101)
            """)
            connection.exec_driver_sql("""
                INSERT INTO presence_threads (
                    id,
                    provider,
                    external_id,
                    kind,
                    state,
                    created_at,
                    updated_at
                )
                VALUES (
                    501,
                    'linear',
                    'thread-1',
                    'conversation',
                    'active',
                    '2026-05-07 12:00:00',
                    '2026-05-07 12:00:00'
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO presence_messages (
                    id,
                    thread_id,
                    provider,
                    external_id,
                    direction,
                    kind,
                    body,
                    state,
                    created_at,
                    updated_at
                )
                VALUES (
                    601,
                    501,
                    'linear',
                    'message-1',
                    'inbound',
                    'comment',
                    'Please handle CAO-38',
                    'received',
                    '2026-05-07 12:00:00',
                    '2026-05-07 12:00:00'
                )
            """)
            connection.exec_driver_sql("""
                CREATE TABLE presence_inbox_notifications (
                    id INTEGER NOT NULL,
                    receiver_id VARCHAR NOT NULL,
                    presence_message_id INTEGER NOT NULL,
                    inbox_message_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE (receiver_id, presence_message_id)
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO presence_inbox_notifications (
                    id,
                    receiver_id,
                    presence_message_id,
                    inbox_message_id,
                    created_at
                )
                VALUES (401, 'agent-123', 601, 101, '2026-05-07 12:00:00')
            """)
            connection.exec_driver_sql("""
                CREATE TABLE agent_runtime_notifications (
                    id INTEGER NOT NULL,
                    agent_id VARCHAR NOT NULL,
                    source_kind VARCHAR NOT NULL,
                    source_id VARCHAR NOT NULL,
                    inbox_message_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE (agent_id, source_kind, source_id)
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO agent_runtime_notifications (
                    id,
                    agent_id,
                    source_kind,
                    source_id,
                    inbox_message_id,
                    created_at
                )
                VALUES (
                    701,
                    'agent-123',
                    'linear_issue',
                    'CAO-38',
                    101,
                    '2026-05-07 12:00:00'
                )
            """)

        db_module._migrate_ensure_presence_tables()
        db_module._migrate_ensure_agent_runtime_tables()
        db_module._migrate_drop_legacy_inbox_notification_ids()

        with test_engine.connect() as connection:
            presence_columns = {
                row[1]: row
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(presence_inbox_notifications)"
                )
            }
            runtime_columns = {
                row[1]: row
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(agent_runtime_notifications)"
                )
            }
            notification_columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(inbox_notifications)")
            }
            presence_notification_id = connection.exec_driver_sql(
                "SELECT inbox_notification_id FROM presence_inbox_notifications"
            ).scalar_one()
            runtime_notification_id = connection.exec_driver_sql(
                "SELECT inbox_notification_id FROM agent_runtime_notifications"
            ).scalar_one()

        assert "inbox_notification_id" in presence_columns
        assert "inbox_message_id" not in presence_columns
        assert presence_columns["inbox_notification_id"][3] == 1
        assert "inbox_notification_id" in runtime_columns
        assert "inbox_message_id" not in runtime_columns
        assert runtime_columns["inbox_notification_id"][3] == 1
        assert presence_notification_id == 301
        assert runtime_notification_id == 301
        assert "legacy_inbox_id" not in notification_columns

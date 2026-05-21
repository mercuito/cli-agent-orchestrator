"""Tests for the database client."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients import database_migrations
from cli_agent_orchestrator.clients.database import (
    Base,
    FlowModel,
    TerminalAgentAlreadyRunningError,
    TerminalModel,
    create_flow,
    create_terminal,
    delete_flow,
    delete_terminal,
    delete_terminals_by_session,
    get_flow,
    get_terminal_metadata,
    init_db,
    list_flows,
    list_terminals_by_agent,
    list_terminals_by_session,
    update_flow_enabled,
    update_flow_run_times,
    update_last_active,
)
from cli_agent_orchestrator.inbox import (
    get_notification,
    oldest_pending_notification,
    list_notifications,
    list_pending_notifications,
    list_pending_notifications_for_sender,
    send as create_inbox_notification,
    update_notification_status,
    update_notification_statuses,
)
from cli_agent_orchestrator.inbox.store import InboxNotificationModel
from cli_agent_orchestrator.models.inbox import MessageStatus


def _notification_fk_targets(connection, table_name: str) -> list[str]:
    return [
        row[2]
        for row in connection.exec_driver_sql(f"PRAGMA foreign_key_list({table_name})")
        if row[3] == "inbox_notification_id"
    ]


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

        result = create_terminal(
            "test123",
            "cao-session",
            "window-0",
            "kiro_cli",
            "developer",
            "ctx_developer_default",
        )

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
        mock_terminal.agent_id = "developer"
        mock_terminal.workspace_context_id = "ctx_developer_default"
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
        mock_terminal.agent_id = "developer"
        mock_terminal.workspace_context_id = "ctx_developer_default"
        mock_terminal.last_active = datetime.now()

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [mock_terminal]
        mock_session.query.return_value = mock_query
        mock_session_class.return_value = mock_session

        result = list_terminals_by_session("cao-session")

        assert len(result) == 1
        assert result[0]["id"] == "test123"

    def test_terminal_metadata_carries_agent_id(self, live_inbox_db):
        """Persisted terminal metadata carries the durable agent id."""
        create_terminal(
            "test123",
            "cao-session",
            "window-0",
            "codex",
            "implementation_partner",
            "ctx_implementation_partner_default",
        )

        result = get_terminal_metadata("test123")

        assert result is not None
        assert result["agent_id"] == "implementation_partner"
        assert result["workspace_context_id"] == "ctx_implementation_partner_default"
        assert list_terminals_by_agent("implementation_partner")[0]["id"] == "test123"

    def test_terminal_metadata_enforces_one_live_terminal_per_agent(self, live_inbox_db):
        """The database claim prevents concurrent duplicate agent terminals."""
        create_terminal(
            "terminal-a",
            "cao-session",
            "window-a",
            "codex",
            "implementation_partner",
            "ctx_implementation_partner_default",
        )

        with pytest.raises(TerminalAgentAlreadyRunningError) as exc_info:
            create_terminal(
                "terminal-b",
                "cao-session",
                "window-b",
                "codex",
                "implementation_partner",
                "ctx_implementation_partner_default",
            )

        assert exc_info.value.agent_id == "implementation_partner"
        assert exc_info.value.terminal_id == "terminal-a"

    def test_terminal_metadata_requires_workspace_context(self, live_inbox_db):
        """Terminal metadata must be fully specified."""
        with pytest.raises(TypeError):
            create_terminal(
                "test123",
                "cao-session",
                "window-0",
                "codex",
                "developer",
            )

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
        """The schema has one agent-to-agent notification table."""
        notification_columns = {
            column.name for column in Base.metadata.tables["inbox_notifications"].columns
        }

        assert {
            "sender_agent_id",
            "receiver_agent_id",
            "body",
            "status",
        } <= notification_columns
        assert "inbox_messages" not in Base.metadata.tables
        assert "inbox_notification_targets" not in Base.metadata.tables
        assert "sender_kind" not in notification_columns
        assert "sender_id" not in notification_columns
        assert "metadata_json" not in notification_columns
        assert "message_id" not in notification_columns
        assert "legacy_inbox_id" not in notification_columns
        assert "inbox" not in Base.metadata.tables

    def test_create_inbox_notification_persists_agent_to_agent_row(self, live_inbox_db):
        notification = create_inbox_notification(
            "receiver-456",
            "Hello",
            sender_agent_id="sender-123",
        )

        assert notification.body == "Hello"
        assert notification.sender_agent_id == "sender-123"
        assert notification.receiver_agent_id == "receiver-456"
        assert notification.status == MessageStatus.PENDING

        with live_inbox_db() as session:
            row = session.query(InboxNotificationModel).one()
        assert row.sender_agent_id == "sender-123"
        assert row.receiver_agent_id == "receiver-456"

    def testlist_notifications_reads_semantic_notifications(self, live_inbox_db):
        notification = create_inbox_notification(
            "agent:implementation_partner",
            "Please inspect the failing job.",
            sender_agent_id="agent:reviewer",
        )

        listed = list_notifications("agent:implementation_partner")
        pending = list_pending_notifications("agent:implementation_partner")
        read = get_notification(notification.id)

        assert listed[0] == notification
        assert pending[0].body == "Please inspect the failing job."
        assert read == notification

    def testget_notification_reads_one_notification_by_id(self, live_inbox_db):
        notification = create_inbox_notification(
            "receiver-456",
            "Hello",
            sender_agent_id="sender-123",
        )

        assert get_notification(notification.id) == notification
        assert get_notification(999) is None

    def test_status_updates_mutate_notification_not_durable_message(self, live_inbox_db):
        notification = create_inbox_notification(
            "receiver-456",
            "Original body",
            sender_agent_id="sender-123",
        )

        assert update_notification_status(notification.id, MessageStatus.DELIVERED)

        with live_inbox_db() as session:
            row = session.query(InboxNotificationModel).one()

        assert row.body == "Original body"
        assert row.status == MessageStatus.DELIVERED.value
        assert row.delivered_at is not None

    def test_semantic_notification_status_update_uses_notification_id(self, live_inbox_db):
        notification = create_inbox_notification(
            "receiver-456",
            "Hello",
            sender_agent_id="sender-123",
        )

        assert update_notification_status(
            notification.id, MessageStatus.FAILED, error_detail="send failed"
        )

        updated = get_notification(notification.id)
        assert updated.status == MessageStatus.FAILED
        assert updated.failed_at is not None
        assert updated.error_detail == "send failed"

    def test_same_sender_pending_messages_are_batched_in_created_order(self, live_inbox_db):
        first = create_inbox_notification("supervisor", "first", sender_agent_id="worker-a")
        second = create_inbox_notification("supervisor", "second", sender_agent_id="worker-a")

        oldest = oldest_pending_notification("supervisor")
        assert oldest is not None
        batch = list_pending_notifications_for_sender("supervisor", oldest)

        assert [delivery.body for delivery in batch] == ["first", "second"]
        assert [delivery.id for delivery in batch] == [
            first.id,
            second.id,
        ]

    def test_sender_batching_distinguishes_sender_agents(self, live_inbox_db):
        create_inbox_notification("supervisor", "sender a", sender_agent_id="worker-a")
        create_inbox_notification("supervisor", "sender b first", sender_agent_id="worker-b")
        create_inbox_notification("supervisor", "sender b second", sender_agent_id="worker-b")

        deliveries = list_notifications("supervisor", limit=10)
        first_sender_delivery = deliveries[0]
        second_sender_delivery = deliveries[1]

        first_sender_batch = list_pending_notifications_for_sender(
            "supervisor", first_sender_delivery
        )
        second_sender_batch = list_pending_notifications_for_sender(
            "supervisor", second_sender_delivery
        )

        assert [delivery.body for delivery in first_sender_batch] == ["sender a"]
        assert [delivery.body for delivery in second_sender_batch] == [
            "sender b first",
            "sender b second",
        ]

    def test_different_senders_are_not_batched_with_oldest_sender(self, live_inbox_db):
        create_inbox_notification("supervisor", "oldest sender", sender_agent_id="worker-a")
        create_inbox_notification("supervisor", "other sender", sender_agent_id="worker-b")
        create_inbox_notification("supervisor", "same sender later", sender_agent_id="worker-a")

        oldest = oldest_pending_notification("supervisor")
        assert oldest is not None
        batch = list_pending_notifications_for_sender("supervisor", oldest)

        assert [delivery.body for delivery in batch] == [
            "oldest sender",
            "same sender later",
        ]

    def test_batch_status_update_marks_only_selected_messages(self, live_inbox_db):
        selected_one = create_inbox_notification(
            "supervisor", "selected one", sender_agent_id="worker-a"
        )
        selected_two = create_inbox_notification(
            "supervisor", "selected two", sender_agent_id="worker-a"
        )
        create_inbox_notification("supervisor", "still pending", sender_agent_id="worker-b")

        updated = update_notification_statuses(
            [selected_one.id, selected_two.id],
            MessageStatus.DELIVERED,
        )
        assert updated == 2

        deliveries = list_notifications("supervisor", limit=10)
        assert [delivery.status for delivery in deliveries] == [
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
            flow.agent_id = "developer"
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
            agent_id="developer",
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
        mock_flow.agent_id = "developer"
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
        mock_flow.agent_id = "developer"
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
        mock_flow.agent_id = "developer"
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

    def test_init_db(self, tmp_path, monkeypatch):
        """Test database initialization."""
        db_path = tmp_path / "init.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)
        monkeypatch.setattr(database_migrations.constants, "DATABASE_FILE", db_path)

        init_db()

        table_names = inspect(test_engine).get_table_names()
        assert "terminals" in table_names
        assert "cao_events" in table_names

    def test_semantic_inbox_migration_creates_tables_idempotently(self, tmp_path, monkeypatch):
        """Existing databases get the new semantic inbox tables safely."""
        db_path = tmp_path / "existing.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)

        db_module._migrate_ensure_semantic_inbox_tables()
        db_module._migrate_ensure_semantic_inbox_tables()

        table_names = inspect(test_engine).get_table_names()
        assert table_names.count("inbox_notifications") == 1
        assert "inbox_messages" not in table_names
        assert "inbox_notification_targets" not in table_names

    def test_inbox_schema_cutover_addresses_notifications_by_agent_and_drops_old_tables(
        self, tmp_path, monkeypatch
    ):
        """Old terminal-addressed inbox rows are cut over to agent-addressed notifications."""
        # Given
        db_path = tmp_path / "legacy-inbox-cutover.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)
        monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

        with test_engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE terminals (
                    id VARCHAR NOT NULL,
                    tmux_session VARCHAR NOT NULL,
                    tmux_window VARCHAR NOT NULL,
                    provider VARCHAR NOT NULL,
                    agent_id VARCHAR NOT NULL,
                    workspace_context_id VARCHAR NOT NULL,
                    allowed_tools TEXT,
                    last_active DATETIME,
                    PRIMARY KEY (id)
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO terminals (
                    id, tmux_session, tmux_window, provider, agent_id, workspace_context_id
                )
                VALUES
                    (
                        'terminal-1', 'cao-session', 'developer-1', 'codex',
                        'implementation_partner', 'default'
                    ),
                    (
                        'sender-terminal', 'cao-session', 'developer-2', 'codex',
                        'reviewer', 'default'
                    )
            """)
            connection.exec_driver_sql("""
                CREATE TABLE inbox_messages (
                    id INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    source_kind VARCHAR NOT NULL,
                    source_id VARCHAR NOT NULL,
                    origin_json TEXT,
                    route_kind VARCHAR,
                    route_id VARCHAR,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id)
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO inbox_messages (
                    id, body, source_kind, source_id, created_at
                )
                VALUES (
                    42, 'Please review this',
                    'terminal', 'sender-terminal', '2026-05-20 12:00:00'
                )
            """)
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
                    PRIMARY KEY (id)
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO inbox_notifications (
                    id, message_id, receiver_id, status, created_at
                )
                VALUES (7, 42, 'terminal-1', 'pending', '2026-05-20 12:00:01')
            """)
            connection.exec_driver_sql("""
                CREATE TABLE inbox_notification_targets (
                    id INTEGER NOT NULL,
                    notification_id INTEGER NOT NULL,
                    target_kind VARCHAR NOT NULL,
                    target_id VARCHAR NOT NULL,
                    role VARCHAR NOT NULL,
                    PRIMARY KEY (id)
                )
            """)
            connection.exec_driver_sql("""
                CREATE TABLE provider_conversation_inbox_notifications (
                    id INTEGER NOT NULL,
                    receiver_id VARCHAR NOT NULL,
                    provider_message_id INTEGER NOT NULL,
                    inbox_notification_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id)
                )
            """)

        # When
        db_module._migrate_ensure_semantic_inbox_tables()
        db_module._migrate_drop_linear_and_provider_conversation_tables()

        # Then
        with test_engine.connect() as connection:
            table_names = inspect(test_engine).get_table_names()
            columns = {
                row[1]: row
                for row in connection.exec_driver_sql("PRAGMA table_info(inbox_notifications)")
            }
            row = connection.exec_driver_sql("""
                SELECT sender_agent_id, receiver_agent_id, body, status
                FROM inbox_notifications
                WHERE id = 7
            """).fetchone()

        assert row == (
            "reviewer",
            "implementation_partner",
            "Please review this",
            "pending",
        )
        assert "sender_agent_id" in columns
        assert "receiver_agent_id" in columns
        assert columns["receiver_agent_id"][3] == 1
        assert "receiver_id" not in columns
        assert "sender_kind" not in columns
        assert "sender_id" not in columns
        assert "metadata_json" not in columns
        assert "message_id" not in columns
        assert "inbox_messages" not in table_names
        assert "inbox_notification_targets" not in table_names
        assert "provider_conversation_inbox_notifications" not in table_names

    def test_linear_cao_event_migration_drops_removed_event_rows(self, tmp_path, monkeypatch):
        """Persisted Linear CAO events are removed so timelines do not deserialize dead classes."""
        # Given
        db_path = tmp_path / "legacy-linear-events.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)
        Base.metadata.create_all(bind=test_engine)

        with test_engine.begin() as connection:
            connection.exec_driver_sql("""
                INSERT INTO cao_events (
                    event_id, event_name, kind, source_type, source_id,
                    occurred_at, correlation_id, causation_id, event_data_json
                )
                VALUES
                    (
                        'linear-event', 'linear.agent_mentioned', 'linear.agent_mentioned',
                        'linear', 'LIN-1', '2026-05-20 12:00:00',
                        NULL, NULL, '{}'
                    ),
                    (
                        'runtime-event', 'agent_ready', 'agent.ready',
                        'runtime', 'agent:implementation_partner',
                        '2026-05-20 12:01:00', NULL, NULL, '{}'
                    )
            """)
            connection.exec_driver_sql("""
                INSERT INTO cao_event_agent_participants (
                    event_id, agent_id, participant_role, occurred_at
                )
                VALUES
                    ('linear-event', 'implementation_partner', 'mentioned', '2026-05-20 12:00:00'),
                    ('runtime-event', 'implementation_partner', 'ready', '2026-05-20 12:01:00')
            """)

        # When
        db_module._migrate_drop_removed_linear_cao_events()

        # Then
        with test_engine.connect() as connection:
            event_ids = {
                row[0] for row in connection.exec_driver_sql("SELECT event_id FROM cao_events")
            }
            participant_event_ids = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT event_id FROM cao_event_agent_participants"
                )
            }

        assert event_ids == {"runtime-event"}
        assert participant_event_ids == {"runtime-event"}

    def test_flow_migration_adds_runtime_columns_to_existing_table(self, tmp_path, monkeypatch):
        """Older flow tables receive agent/provider/script columns before the daemon queries them."""
        # Given
        db_path = tmp_path / "legacy-flows.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)

        with test_engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE flows (
                    name VARCHAR NOT NULL,
                    file_path VARCHAR NOT NULL,
                    schedule VARCHAR NOT NULL,
                    last_run DATETIME,
                    next_run DATETIME,
                    enabled BOOLEAN,
                    PRIMARY KEY (name)
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO flows (name, file_path, schedule, enabled)
                VALUES ('daily', '/repo/flows/daily.md', '0 9 * * *', 1)
            """)

        # When
        database_migrations._migrate_ensure_flow_tables()

        # Then
        with test_engine.connect() as connection:
            columns = {
                row[1] for row in connection.exec_driver_sql("PRAGMA table_info(flows)")
            }
            row = connection.exec_driver_sql("""
                SELECT agent_id, provider, script
                FROM flows
                WHERE name = 'daily'
            """).fetchone()

        assert {"agent_id", "provider", "script"}.issubset(columns)
        assert row == ("code_supervisor", "kiro_cli", "")

    def test_terminal_agent_migration_preserves_agent_id(self, tmp_path, monkeypatch):
        """Existing agent-owned terminal rows keep required agent_id values."""
        db_path = tmp_path / "legacy-terminals.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

        with test_engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE terminals (
                    id VARCHAR NOT NULL,
                    tmux_session VARCHAR NOT NULL,
                    tmux_window VARCHAR NOT NULL,
                    provider VARCHAR NOT NULL,
                    agent_id VARCHAR,
                    allowed_tools TEXT,
                    last_active DATETIME,
                    PRIMARY KEY (id)
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO terminals (
                    id, tmux_session, tmux_window, provider, agent_id
                )
                VALUES ('terminal-1', 'cao-session', 'developer-1', 'codex', 'developer')
            """)

        database_migrations._migrate_add_terminal_agent_id()
        database_migrations._migrate_enforce_single_terminal_per_agent()

        with test_engine.connect() as connection:
            table_info = connection.exec_driver_sql("PRAGMA table_info(terminals)").fetchall()
            index_info = connection.exec_driver_sql("PRAGMA index_list(terminals)").fetchall()
            columns = {row[1] for row in table_info}
            not_null_by_column = {row[1]: bool(row[3]) for row in table_info}
            row = connection.exec_driver_sql(
                "SELECT agent_id FROM terminals WHERE id = 'terminal-1'"
            ).fetchone()

        assert "agent_id" in columns
        assert not_null_by_column["agent_id"] is True
        assert any(row[1] == "uq_terminals_agent_id" and row[2] for row in index_info)
        assert "agent_profile" not in columns
        assert row == ("developer",)

    def test_terminal_agent_migration_refuses_anonymous_rows(self, tmp_path, monkeypatch):
        """Anonymous terminal rows must be deleted before the hard-cutover migration."""
        old_agent_column = "agent_" + "identity_id"
        db_path = tmp_path / "anonymous-terminals.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

        with test_engine.begin() as connection:
            connection.exec_driver_sql(f"""
                CREATE TABLE terminals (
                    id VARCHAR NOT NULL,
                    tmux_session VARCHAR NOT NULL,
                    tmux_window VARCHAR NOT NULL,
                    provider VARCHAR NOT NULL,
                    {old_agent_column} VARCHAR,
                    agent_profile VARCHAR,
                    PRIMARY KEY (id)
                )
            """)
            connection.exec_driver_sql(f"""
                INSERT INTO terminals (
                    id, tmux_session, tmux_window, provider, {old_agent_column}, agent_profile
                )
                VALUES
                    ('terminal-null', 'cao-session', 'window-a', 'codex', NULL, 'developer'),
                    ('terminal-blank', 'cao-session', 'window-b', 'codex', '  ', 'reviewer')
            """)

        with pytest.raises(RuntimeError) as exc_info:
            database_migrations._migrate_add_terminal_agent_id()

        message = str(exc_info.value)
        assert "agent_id NOT NULL" in message
        assert "anonymous terminal rows exist" in message
        assert "terminal-null" in message
        assert "terminal-blank" in message

    def test_terminal_agent_uniqueness_migration_refuses_duplicate_agents(
        self, tmp_path, monkeypatch
    ):
        """Existing duplicate live agent rows must be cleaned before enforcing T09."""
        db_path = tmp_path / "duplicate-agent-terminals.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

        with test_engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE terminals (
                    id TEXT PRIMARY KEY,
                    tmux_session TEXT NOT NULL,
                    tmux_window TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    workspace_context_id TEXT NOT NULL,
                    allowed_tools TEXT,
                    last_active DATETIME
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO terminals (
                    id, tmux_session, tmux_window, provider, agent_id, workspace_context_id
                )
                VALUES
                    ('terminal-a', 'cao-session', 'window-a', 'codex', 'developer', 'ctx-a'),
                    ('terminal-b', 'cao-session', 'window-b', 'codex', 'developer', 'ctx-b')
            """)

        with pytest.raises(RuntimeError) as exc_info:
            database_migrations._migrate_enforce_single_terminal_per_agent()

        message = str(exc_info.value)
        assert "one live terminal per agent" in message
        assert "developer" in message
        assert "terminal-a" in message
        assert "terminal-b" in message

    def test_terminal_workspace_context_backfill_binds_renamed_agent_terminal(
        self, tmp_path, monkeypatch
    ):
        """Renamed agent-managed terminals get an explicit default workspace context."""
        old_agent_column = "agent_" + "identity_id"
        db_path = tmp_path / "renamed-agent-terminal.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)
        monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

        with test_engine.begin() as connection:
            connection.exec_driver_sql(f"""
                CREATE TABLE terminals (
                    id VARCHAR NOT NULL,
                    tmux_session VARCHAR NOT NULL,
                    tmux_window VARCHAR NOT NULL,
                    provider VARCHAR NOT NULL,
                    allowed_tools TEXT,
                    {old_agent_column} TEXT,
                    workspace_context_id TEXT,
                    last_active DATETIME,
                    PRIMARY KEY (id)
                )
            """)
            connection.exec_driver_sql(f"""
                INSERT INTO terminals (
                    id,
                    tmux_session,
                    tmux_window,
                    provider,
                    {old_agent_column},
                    workspace_context_id
                )
                VALUES (
                    'terminal-1',
                    'cao-discovery-partner',
                    'yards-discovery-partner',
                    'codex',
                    'discovery_partner',
                    NULL
                )
            """)

        database_migrations._migrate_ensure_workspace_context_tables()
        database_migrations._migrate_add_terminal_agent_id()
        database_migrations._migrate_backfill_terminal_workspace_context_id()

        with test_engine.connect() as connection:
            terminal_agent_id, terminal_context_id = connection.exec_driver_sql(
                "SELECT agent_id, workspace_context_id FROM terminals WHERE id = 'terminal-1'"
            ).fetchone()
            context_boundary = connection.exec_driver_sql(
                """
                SELECT boundary_provider_id, boundary_object_type, boundary_object_id
                FROM workspace_contexts
                WHERE id = ?
                """,
                (terminal_context_id,),
            ).fetchone()

        assert terminal_agent_id == "discovery_partner"
        assert terminal_context_id.startswith("wctx_")
        assert context_boundary == (
            "cao",
            "agent_default",
            "discovery_partner",
        )

    def test_workspace_context_migration_renames_agent_identity_column(self, tmp_path, monkeypatch):
        """Existing context workspaces are rebuilt to use durable agent ids."""
        old_agent_column = "agent_" + "identity_id"
        db_path = tmp_path / "legacy-context-workspaces.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        monkeypatch.setattr(db_module, "engine", test_engine)
        monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

        with test_engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE workspace_contexts (
                    id VARCHAR NOT NULL,
                    resolver_id VARCHAR NOT NULL,
                    boundary_provider_id VARCHAR NOT NULL,
                    boundary_object_type VARCHAR NOT NULL,
                    boundary_object_id VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    metadata_json TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id)
                )
            """)
            connection.exec_driver_sql(f"""
                CREATE TABLE context_workspaces (
                    id INTEGER NOT NULL,
                    {old_agent_column} VARCHAR NOT NULL,
                    workspace_context_id VARCHAR NOT NULL,
                    root_path VARCHAR NOT NULL,
                    active_terminal_id VARCHAR,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    CONSTRAINT uq_context_workspace_identity_context
                        UNIQUE ({old_agent_column}, workspace_context_id),
                    FOREIGN KEY(workspace_context_id)
                        REFERENCES workspace_contexts (id) ON DELETE CASCADE
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO workspace_contexts (
                    id,
                    resolver_id,
                    boundary_provider_id,
                    boundary_object_type,
                    boundary_object_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (
                    'wctx_default',
                    'default',
                    'cao',
                    'agent_default',
                    'implementation_partner',
                    'active',
                    '2026-01-01 00:00:00',
                    '2026-01-01 00:00:00'
                )
            """)
            connection.exec_driver_sql(f"""
                INSERT INTO context_workspaces (
                    id,
                    {old_agent_column},
                    workspace_context_id,
                    root_path,
                    active_terminal_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    7,
                    'implementation_partner',
                    'wctx_default',
                    '/tmp/workspace',
                    'terminal-1',
                    '2026-01-01 00:00:00',
                    '2026-01-01 00:00:00'
                )
            """)

        database_migrations._migrate_ensure_workspace_context_tables()

        with test_engine.connect() as connection:
            columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(context_workspaces)")
            }
            row = connection.exec_driver_sql("""
                SELECT id, agent_id, workspace_context_id, root_path, active_terminal_id
                FROM context_workspaces
                """).fetchone()

        assert old_agent_column not in columns
        assert "agent_id" in columns
        assert row == (
            7,
            "implementation_partner",
            "wctx_default",
            "/tmp/workspace",
            "terminal-1",
        )

    def test_marker_migrations_repair_notification_fk_targets_after_inbox_rebuild(
        self, tmp_path, monkeypatch
    ):
        """Runtime marker tables are rebuilt if their FKs point at a temp inbox table."""
        db_path = tmp_path / "bad-marker-fks.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        TestSession = sessionmaker(bind=test_engine)
        monkeypatch.setattr(db_module, "engine", test_engine)
        monkeypatch.setattr(db_module, "SessionLocal", TestSession)
        monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_path)

        Base.metadata.create_all(bind=test_engine)
        with test_engine.begin() as connection:
            connection.exec_driver_sql("""
                INSERT INTO inbox_notifications (
                    id, sender_agent_id, receiver_agent_id, body, status, created_at
                )
                VALUES (1, 'sender', 'agent-1', 'body', 'pending', '2026-05-20 12:00:00')
            """)
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.exec_driver_sql("DROP TABLE agent_runtime_notifications")
            connection.exec_driver_sql("""
                CREATE TABLE agent_runtime_notifications (
                    id INTEGER NOT NULL,
                    agent_id VARCHAR NOT NULL,
                    sender_kind VARCHAR NOT NULL,
                    sender_id VARCHAR NOT NULL,
                    inbox_notification_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE (agent_id, sender_kind, sender_id),
                    FOREIGN KEY(inbox_notification_id)
                        REFERENCES "inbox_notifications_old" (id) ON DELETE CASCADE
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO agent_runtime_notifications (
                    id, agent_id, sender_kind, sender_id, inbox_notification_id, created_at
                )
                VALUES (1, 'agent-1', 'runtime_event', 'event-1', 1, '2026-05-20 12:00:00')
            """)
        with test_engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        db_module._migrate_ensure_agent_runtime_tables()

        with test_engine.connect() as connection:
            columns = {
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(agent_runtime_notifications)"
                )
            }
            assert "idempotency_key" in columns
            assert "sender_kind" not in columns
            assert "sender_id" not in columns
            assert _notification_fk_targets(connection, "agent_runtime_notifications") == [
                "inbox_notifications"
            ]
            key = connection.exec_driver_sql(
                "SELECT idempotency_key FROM agent_runtime_notifications WHERE id = 1"
            ).scalar_one()
            assert key == "runtime_event:event-1"

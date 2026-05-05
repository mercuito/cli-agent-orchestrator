"""Tests for the database client."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import (
    Base,
    FlowModel,
    InboxModel,
    TerminalModel,
    create_flow,
    create_inbox_message,
    create_terminal,
    delete_flow,
    delete_terminal,
    delete_terminals_by_session,
    get_effective_message_source,
    get_flow,
    get_inbox_messages,
    get_oldest_pending_message,
    get_pending_messages,
    get_pending_messages_for_effective_source,
    get_terminal_metadata,
    init_db,
    list_flows,
    list_terminals_by_session,
    update_flow_enabled,
    update_flow_run_times,
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

    @patch("cli_agent_orchestrator.clients.database.SessionLocal")
    def test_create_inbox_message(self, mock_session_class):
        """Test creating an inbox message."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session_class.return_value = mock_session

        # Setup mock to update message attributes on refresh
        def mock_refresh(msg):
            msg.id = 1
            msg.sender_id = "sender-123"
            msg.receiver_id = "receiver-456"
            msg.message = "Hello"
            msg.status = MessageStatus.PENDING.value
            msg.created_at = datetime.now()

        mock_session.refresh.side_effect = mock_refresh

        result = create_inbox_message("sender-123", "receiver-456", "Hello")

        assert result.sender_id == "sender-123"
        assert result.receiver_id == "receiver-456"
        assert result.message == "Hello"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


class TestInitDb:
    """Tests for init_db function."""

    @patch("cli_agent_orchestrator.clients.database.Base")
    def test_init_db(self, mock_base):
        """Test database initialization."""
        init_db()

        mock_base.metadata.create_all.assert_called_once()

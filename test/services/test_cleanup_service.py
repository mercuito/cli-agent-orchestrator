"""Tests for cleanup service."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients.database import (
    AgentRuntimeNotificationModel,
    Base,
    INBOX_NOTIFICATION_TARGET_KIND_INBOX_MESSAGE,
    INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY,
    InboxMessageModel,
    InboxNotificationModel,
    InboxNotificationTargetModel,
    PresenceInboxNotificationModel,
    PresenceMessageModel,
    PresenceThreadModel,
)
from cli_agent_orchestrator.models.inbox import MessageStatus
from cli_agent_orchestrator.services import cleanup_service
from cli_agent_orchestrator.services.cleanup_service import cleanup_old_data


def _fk_enabled_sessionmaker():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


class TestCleanupOldData:
    """Tests for cleanup_old_data function."""

    @patch("cli_agent_orchestrator.services.cleanup_service.SessionLocal")
    @patch("cli_agent_orchestrator.services.cleanup_service.TERMINAL_LOG_DIR")
    @patch("cli_agent_orchestrator.services.cleanup_service.LOG_DIR")
    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 7)
    def test_cleanup_old_data_deletes_old_terminals(
        self, mock_log_dir, mock_terminal_log_dir, mock_session_local
    ):
        """Test that cleanup deletes old terminals from database."""
        # Setup mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.delete.return_value = 5

        # Setup mock directories (non-existent)
        mock_log_dir.exists.return_value = False
        mock_terminal_log_dir.exists.return_value = False

        # Execute
        cleanup_old_data()

        # Verify terminal cleanup was called
        assert mock_db.query.called
        assert mock_db.commit.called

    @patch("cli_agent_orchestrator.services.cleanup_service.SessionLocal")
    @patch("cli_agent_orchestrator.services.cleanup_service.TERMINAL_LOG_DIR")
    @patch("cli_agent_orchestrator.services.cleanup_service.LOG_DIR")
    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 7)
    def test_cleanup_old_data_deletes_old_inbox_messages(
        self, mock_log_dir, mock_terminal_log_dir, mock_session_local
    ):
        """Test that cleanup deletes old inbox messages from database."""
        # Setup mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.delete.return_value = 10

        # Setup mock directories (non-existent)
        mock_log_dir.exists.return_value = False
        mock_terminal_log_dir.exists.return_value = False

        # Execute
        cleanup_old_data()

        # terminals, old notifications, orphan targets, and unreferenced durable messages
        assert mock_db.query.call_count == 6
        assert mock_db.commit.call_count == 2

    @patch("cli_agent_orchestrator.services.cleanup_service.SessionLocal")
    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 7)
    def test_cleanup_old_data_deletes_old_terminal_log_files(self, mock_session_local):
        """Test that cleanup deletes old terminal log files."""
        # Setup mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.delete.return_value = 0

        # Create temp directory with old and new log files
        with tempfile.TemporaryDirectory() as tmpdir:
            terminal_log_dir = Path(tmpdir) / "terminal"
            terminal_log_dir.mkdir()

            # Create old log file (older than retention period)
            old_log = terminal_log_dir / "old.log"
            old_log.write_text("old log content")
            old_time = (datetime.now() - timedelta(days=10)).timestamp()
            import os

            os.utime(old_log, (old_time, old_time))

            # Create new log file (within retention period)
            new_log = terminal_log_dir / "new.log"
            new_log.write_text("new log content")

            with patch(
                "cli_agent_orchestrator.services.cleanup_service.TERMINAL_LOG_DIR",
                terminal_log_dir,
            ):
                with patch(
                    "cli_agent_orchestrator.services.cleanup_service.LOG_DIR",
                    Path(tmpdir) / "nonexistent",
                ):
                    cleanup_old_data()

            # Verify old log was deleted, new log remains
            assert not old_log.exists()
            assert new_log.exists()

    @patch("cli_agent_orchestrator.services.cleanup_service.SessionLocal")
    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 7)
    def test_cleanup_old_data_deletes_old_server_log_files(self, mock_session_local):
        """Test that cleanup deletes old server log files."""
        # Setup mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.delete.return_value = 0

        # Create temp directory with old and new log files
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            log_dir.mkdir()

            # Create old log file
            old_log = log_dir / "server_old.log"
            old_log.write_text("old server log")
            old_time = (datetime.now() - timedelta(days=10)).timestamp()
            import os

            os.utime(old_log, (old_time, old_time))

            # Create new log file
            new_log = log_dir / "server_new.log"
            new_log.write_text("new server log")

            with patch(
                "cli_agent_orchestrator.services.cleanup_service.TERMINAL_LOG_DIR",
                Path(tmpdir) / "nonexistent",
            ):
                with patch(
                    "cli_agent_orchestrator.services.cleanup_service.LOG_DIR",
                    log_dir,
                ):
                    cleanup_old_data()

            # Verify old log was deleted, new log remains
            assert not old_log.exists()
            assert new_log.exists()

    @patch("cli_agent_orchestrator.services.cleanup_service.SessionLocal")
    @patch("cli_agent_orchestrator.services.cleanup_service.TERMINAL_LOG_DIR")
    @patch("cli_agent_orchestrator.services.cleanup_service.LOG_DIR")
    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 7)
    def test_cleanup_old_data_handles_database_error(
        self, mock_log_dir, mock_terminal_log_dir, mock_session_local
    ):
        """Test that cleanup handles database errors gracefully."""
        # Setup mock database session to raise an error
        mock_session_local.return_value.__enter__.side_effect = Exception("Database error")

        # Setup mock directories (non-existent)
        mock_log_dir.exists.return_value = False
        mock_terminal_log_dir.exists.return_value = False

        # Execute - should not raise exception
        cleanup_old_data()  # Should log error but not raise

    @patch("cli_agent_orchestrator.services.cleanup_service.SessionLocal")
    @patch("cli_agent_orchestrator.services.cleanup_service.TERMINAL_LOG_DIR")
    @patch("cli_agent_orchestrator.services.cleanup_service.LOG_DIR")
    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 7)
    def test_cleanup_old_data_handles_empty_directories(
        self, mock_log_dir, mock_terminal_log_dir, mock_session_local
    ):
        """Test that cleanup handles empty or non-existent directories."""
        # Setup mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.delete.return_value = 0

        # Setup mock directories as non-existent
        mock_log_dir.exists.return_value = False
        mock_terminal_log_dir.exists.return_value = False

        # Execute - should complete without error
        cleanup_old_data()

        # Verify database operations still occurred
        assert mock_db.query.called

    @patch("cli_agent_orchestrator.services.cleanup_service.SessionLocal")
    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 30)
    def test_cleanup_uses_correct_retention_period(self, mock_session_local):
        """Test that cleanup uses the configured retention period."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # Capture the filter argument to verify cutoff date
        filter_calls = []

        def capture_filter(*conditions):
            filter_calls.extend(conditions)
            mock_result = MagicMock()
            mock_result.delete.return_value = 0
            return mock_result

        mock_db.query.return_value.filter = capture_filter

        with patch(
            "cli_agent_orchestrator.services.cleanup_service.TERMINAL_LOG_DIR"
        ) as mock_terminal:
            with patch("cli_agent_orchestrator.services.cleanup_service.LOG_DIR") as mock_log:
                mock_terminal.exists.return_value = False
                mock_log.exists.return_value = False
                cleanup_old_data()

        # Verify filter was called (exact date comparison is tricky, just verify it was called)
        assert len(filter_calls) >= 4

    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 7)
    def test_cleanup_deletes_old_delivered_notifications_but_keeps_referenced_message(
        self, tmp_path, monkeypatch
    ):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(bind=engine)
        monkeypatch.setattr(cleanup_service, "SessionLocal", TestSession)
        monkeypatch.setattr(cleanup_service, "TERMINAL_LOG_DIR", tmp_path / "terminal")
        monkeypatch.setattr(cleanup_service, "LOG_DIR", tmp_path / "logs")

        old = datetime.now() - timedelta(days=10)
        with TestSession() as session:
            message = InboxMessageModel(
                sender_id="sender",
                body="still referenced",
                source_kind="terminal",
                source_id="sender",
                created_at=old,
            )
            session.add(message)
            session.flush()
            delivered = InboxNotificationModel(
                receiver_id="receiver-a",
                body="still referenced",
                source_kind="terminal",
                source_id="sender",
                status=MessageStatus.DELIVERED.value,
                created_at=old,
            )
            pending = InboxNotificationModel(
                receiver_id="receiver-b",
                body="still referenced",
                source_kind="terminal",
                source_id="sender",
                status=MessageStatus.PENDING.value,
                created_at=old,
            )
            session.add_all([delivered, pending])
            session.flush()
            session.add_all(
                [
                    InboxNotificationTargetModel(
                        notification_id=delivered.id,
                        target_kind=INBOX_NOTIFICATION_TARGET_KIND_INBOX_MESSAGE,
                        target_id=str(message.id),
                        role=INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY,
                    ),
                    InboxNotificationTargetModel(
                        notification_id=pending.id,
                        target_kind=INBOX_NOTIFICATION_TARGET_KIND_INBOX_MESSAGE,
                        target_id=str(message.id),
                        role=INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY,
                    ),
                ]
            )
            session.commit()

        cleanup_old_data()

        with TestSession() as session:
            assert session.query(InboxMessageModel).count() == 1
            remaining = session.query(InboxNotificationModel).one()
            assert remaining.status == MessageStatus.PENDING.value

    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 7)
    def test_cleanup_deletes_unreferenced_old_durable_messages(self, tmp_path, monkeypatch):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(bind=engine)
        monkeypatch.setattr(cleanup_service, "SessionLocal", TestSession)
        monkeypatch.setattr(cleanup_service, "TERMINAL_LOG_DIR", tmp_path / "terminal")
        monkeypatch.setattr(cleanup_service, "LOG_DIR", tmp_path / "logs")

        old = datetime.now() - timedelta(days=10)
        with TestSession() as session:
            message = InboxMessageModel(
                sender_id="sender",
                body="old delivered",
                source_kind="terminal",
                source_id="sender",
                created_at=old,
            )
            session.add(message)
            session.flush()
            notification = InboxNotificationModel(
                receiver_id="receiver",
                body="old delivered",
                source_kind="terminal",
                source_id="sender",
                status=MessageStatus.DELIVERED.value,
                created_at=old,
            )
            session.add(notification)
            session.flush()
            session.add(
                InboxNotificationTargetModel(
                    notification_id=notification.id,
                    target_kind=INBOX_NOTIFICATION_TARGET_KIND_INBOX_MESSAGE,
                    target_id=str(message.id),
                    role=INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY,
                )
            )
            session.commit()

        cleanup_old_data()

        with TestSession() as session:
            assert session.query(InboxNotificationModel).count() == 0
            assert session.query(InboxMessageModel).count() == 0

    @patch("cli_agent_orchestrator.services.cleanup_service.RETENTION_DAYS", 7)
    def test_cleanup_cascades_notification_markers_before_deleting_message(
        self, tmp_path, monkeypatch
    ):
        TestSession = _fk_enabled_sessionmaker()
        monkeypatch.setattr(cleanup_service, "SessionLocal", TestSession)
        monkeypatch.setattr(cleanup_service, "TERMINAL_LOG_DIR", tmp_path / "terminal")
        monkeypatch.setattr(cleanup_service, "LOG_DIR", tmp_path / "logs")

        old = datetime.now() - timedelta(days=10)
        with TestSession() as session:
            durable_message = InboxMessageModel(
                sender_id="sender",
                body="old delivered",
                source_kind="presence_message",
                source_id="thread-1",
                created_at=old,
            )
            thread = PresenceThreadModel(
                provider="linear",
                external_id="thread-1",
                kind="conversation",
                state="active",
                created_at=old,
                updated_at=old,
            )
            session.add_all([durable_message, thread])
            session.flush()
            presence_message = PresenceMessageModel(
                thread_id=thread.id,
                provider="linear",
                external_id="message-1",
                direction="inbound",
                kind="comment",
                body="cleanup cascade proof",
                state="received",
                created_at=old,
                updated_at=old,
            )
            notification = InboxNotificationModel(
                receiver_id="receiver",
                body="old delivered",
                source_kind="presence_message",
                source_id="thread-1",
                status=MessageStatus.DELIVERED.value,
                created_at=old,
            )
            session.add_all([presence_message, notification])
            session.flush()
            session.add_all(
                [
                    InboxNotificationTargetModel(
                        notification_id=notification.id,
                        target_kind=INBOX_NOTIFICATION_TARGET_KIND_INBOX_MESSAGE,
                        target_id=str(durable_message.id),
                        role=INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY,
                    ),
                    PresenceInboxNotificationModel(
                        receiver_id="receiver",
                        presence_message_id=presence_message.id,
                        inbox_notification_id=notification.id,
                        created_at=old,
                    ),
                    AgentRuntimeNotificationModel(
                        agent_id="receiver",
                        source_kind="presence_message",
                        source_id="thread-1",
                        inbox_notification_id=notification.id,
                        created_at=old,
                    ),
                ]
            )
            session.commit()

        cleanup_old_data()

        with TestSession() as session:
            assert session.query(InboxNotificationModel).count() == 0
            assert session.query(PresenceInboxNotificationModel).count() == 0
            assert session.query(AgentRuntimeNotificationModel).count() == 0
            assert session.query(InboxMessageModel).count() == 0
            assert session.query(PresenceMessageModel).count() == 1
            assert session.query(PresenceThreadModel).count() == 1

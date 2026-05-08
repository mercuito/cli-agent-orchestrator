"""Cleanup service for old terminals, messages, and logs."""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import String, cast

from cli_agent_orchestrator.clients.database import (
    INBOX_NOTIFICATION_TARGET_KIND_MESSAGE,
    InboxMessageModel,
    InboxNotificationModel,
    InboxNotificationTargetModel,
    SessionLocal,
    TerminalModel,
)
from cli_agent_orchestrator.constants import LOG_DIR, RETENTION_DAYS, TERMINAL_LOG_DIR
from cli_agent_orchestrator.models.inbox import MessageStatus

logger = logging.getLogger(__name__)


def cleanup_old_data():
    """Clean up terminals, inbox messages, and log files older than RETENTION_DAYS."""
    try:
        cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)
        logger.info(
            f"Starting cleanup of data older than {RETENTION_DAYS} days (before {cutoff_date})"
        )

        # Clean up old terminals
        with SessionLocal() as db:
            deleted_terminals = (
                db.query(TerminalModel).filter(TerminalModel.last_active < cutoff_date).delete()
            )
            db.commit()
            logger.info(f"Deleted {deleted_terminals} old terminals from database")

        # Delivery notifications own retention state. Durable messages are
        # deleted only after no notification rows still reference them.
        with SessionLocal() as db:
            deleted_notifications = (
                db.query(InboxNotificationModel)
                .filter(
                    InboxNotificationModel.created_at < cutoff_date,
                    InboxNotificationModel.status.in_(
                        [MessageStatus.DELIVERED.value, MessageStatus.FAILED.value]
                    ),
                )
                .delete(synchronize_session=False)
            )
            db.query(InboxNotificationTargetModel).filter(
                ~db.query(InboxNotificationModel.id)
                .filter(InboxNotificationModel.id == InboxNotificationTargetModel.notification_id)
                .exists()
            ).delete(synchronize_session=False)
            deleted_messages = (
                db.query(InboxMessageModel)
                .filter(
                    InboxMessageModel.created_at < cutoff_date,
                    ~db.query(InboxNotificationTargetModel.id)
                    .filter(
                        InboxNotificationTargetModel.target_kind
                        == INBOX_NOTIFICATION_TARGET_KIND_MESSAGE,
                        InboxNotificationTargetModel.target_id
                        == cast(InboxMessageModel.id, String),
                    )
                    .exists(),
                )
                .delete(synchronize_session=False)
            )
            db.commit()
            logger.info(
                "Deleted %s old inbox notifications and %s unreferenced messages from database",
                deleted_notifications,
                deleted_messages,
            )

        # Clean up old terminal log files
        terminal_logs_deleted = 0
        if TERMINAL_LOG_DIR.exists():
            for log_file in TERMINAL_LOG_DIR.glob("*.log"):
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
                    terminal_logs_deleted += 1
        logger.info(f"Deleted {terminal_logs_deleted} old terminal log files")

        # Clean up old server log files
        server_logs_deleted = 0
        if LOG_DIR.exists():
            for log_file in LOG_DIR.glob("*.log"):
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
                    server_logs_deleted += 1
        logger.info(f"Deleted {server_logs_deleted} old server log files")

        logger.info("Cleanup completed successfully")

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

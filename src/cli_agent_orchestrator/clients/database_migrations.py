"""CAO database schema migration decisions."""

from __future__ import annotations

import logging
from typing import Optional

from cli_agent_orchestrator import constants
from cli_agent_orchestrator.clients import sqlite_migrations
from cli_agent_orchestrator.clients.baton_store import BatonEventModel, BatonModel
from cli_agent_orchestrator.clients.inbox_store import (
    INBOX_NOTIFICATION_TARGET_KIND_INBOX_MESSAGE,
    INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY,
    InboxMessageModel,
    InboxNotificationModel,
    InboxNotificationTargetModel,
)
from cli_agent_orchestrator.clients.presence_store import (
    AgentRuntimeNotificationModel,
    PresenceInboxNotificationModel,
    PresenceMessageModel,
    PresenceThreadModel,
    PresenceWorkItemModel,
    ProcessedProviderEventModel,
)

logger = logging.getLogger(__name__)


def _database_module():
    from cli_agent_orchestrator.clients import database as db_module

    return db_module


def init_db() -> None:
    """Initialize database tables and apply schema migrations."""
    db_module = _database_module()
    db_module.Base.metadata.create_all(bind=db_module.engine)
    _migrate_ensure_semantic_inbox_tables()
    _migrate_ensure_baton_tables()
    _migrate_ensure_presence_tables()
    _migrate_ensure_agent_runtime_tables()
    _migrate_drop_legacy_inbox_notification_ids()
    _migrate_drop_legacy_inbox_table()
    _migrate_add_allowed_tools()
    _migrate_drop_monitoring_session_peers()


def _migrate_ensure_semantic_inbox_tables() -> None:
    """Create semantic inbox message/notification tables on existing databases."""
    try:
        engine = _database_module().engine
        InboxMessageModel.__table__.create(bind=engine, checkfirst=True)
        InboxNotificationModel.__table__.create(bind=engine, checkfirst=True)
        InboxNotificationTargetModel.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Migration check for semantic inbox tables failed: {e}")
        return

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            columns = sqlite_migrations.table_column_info(conn, "inbox_notifications")
            if not columns:
                return

            needs_rebuild = (
                "body" not in columns
                or "source_kind" not in columns
                or "source_id" not in columns
                or "metadata_json" not in columns
                or "message_id" in columns
            )
            if not needs_rebuild:
                return

            has_legacy_message_target = "message_id" in columns
            if has_legacy_message_target:
                _snapshot_inbox_notification_message_targets(conn)
            sqlite_migrations.rebuild_table(
                conn,
                table_name="inbox_notifications",
                create_sql=_inbox_notifications_create_sql(
                    include_legacy="legacy_inbox_id" in columns
                ),
                copy_sql=_inbox_notifications_copy_sql(
                    columns,
                    include_legacy="legacy_inbox_id" in columns,
                ),
            )
            if has_legacy_message_target:
                _copy_inbox_notification_message_targets(conn)
            logger.info("Migration: rebuilt inbox_notifications for notification contract")
    except Exception as e:
        logger.warning(f"Migration check for inbox notification contract failed: {e}")


def _inbox_notifications_create_sql(*, include_legacy: bool = False) -> str:
    legacy_column = "legacy_inbox_id INTEGER UNIQUE," if include_legacy else ""
    return f"""
        CREATE TABLE inbox_notifications (
            id INTEGER NOT NULL,
            receiver_id VARCHAR NOT NULL,
            body TEXT NOT NULL,
            source_kind VARCHAR NOT NULL,
            source_id VARCHAR NOT NULL,
            metadata_json TEXT,
            status VARCHAR NOT NULL,
            created_at DATETIME NOT NULL,
            delivered_at DATETIME,
            failed_at DATETIME,
            error_detail TEXT,
            {legacy_column}
            PRIMARY KEY (id)
        )
    """


def _column_or_expr(
    columns: dict[str, sqlite_migrations.ColumnInfo], name: str, fallback: str
) -> str:
    return f"old.{name}" if name in columns else fallback


def _inbox_notifications_copy_sql(
    columns: dict[str, sqlite_migrations.ColumnInfo], *, include_legacy: bool = False
) -> str:
    target_columns = [
        "id",
        "receiver_id",
        "body",
        "source_kind",
        "source_id",
        "metadata_json",
        "status",
        "created_at",
        "delivered_at",
        "failed_at",
        "error_detail",
    ]
    source_exprs = [
        "old.id",
        "old.receiver_id",
    ]
    message_body_fallback = "''"
    message_source_kind_fallback = "'system'"
    message_source_id_fallback = "'unknown'"
    if "message_id" in columns:
        message_body_fallback = (
            "COALESCE((SELECT inbox_messages.body FROM inbox_messages "
            "WHERE inbox_messages.id = old.message_id), '')"
        )
        message_source_kind_fallback = (
            "COALESCE((SELECT inbox_messages.source_kind FROM inbox_messages "
            "WHERE inbox_messages.id = old.message_id), 'system')"
        )
        message_source_id_fallback = (
            "COALESCE((SELECT inbox_messages.source_id FROM inbox_messages "
            "WHERE inbox_messages.id = old.message_id), 'unknown')"
        )
    body_expr = _column_or_expr(
        columns,
        "body",
        message_body_fallback,
    )
    source_kind_expr = _column_or_expr(
        columns,
        "source_kind",
        message_source_kind_fallback,
    )
    source_id_expr = _column_or_expr(
        columns,
        "source_id",
        message_source_id_fallback,
    )
    metadata_expr = _column_or_expr(columns, "metadata_json", "NULL")
    source_exprs.extend(
        [
            body_expr,
            source_kind_expr,
            source_id_expr,
            metadata_expr,
            "old.status",
            "old.created_at",
            "old.delivered_at",
            "old.failed_at",
            "old.error_detail",
        ]
    )
    if include_legacy:
        target_columns.append("legacy_inbox_id")
        source_exprs.append("old.legacy_inbox_id")
    target_sql = ",\n            ".join(target_columns)
    source_sql = ",\n            ".join(source_exprs)
    return f"""
        INSERT INTO inbox_notifications (
            {target_sql}
        )
        SELECT
            {source_sql}
        FROM {{old_table}} AS old
    """


def _snapshot_inbox_notification_message_targets(sqlite_conn) -> None:
    """Snapshot migration-only notification/message links before table rebuild."""

    sqlite_conn.execute("DROP TABLE IF EXISTS temp.inbox_notification_message_targets_migration")
    sqlite_conn.execute(f"""
        CREATE TEMP TABLE inbox_notification_message_targets_migration AS
        SELECT
            old.id AS notification_id,
            CAST(old.message_id AS TEXT) AS target_id
        FROM inbox_notifications AS old
        WHERE old.message_id IS NOT NULL
          AND old.message_id IN (SELECT id FROM inbox_messages)
    """)


def _copy_inbox_notification_message_targets(sqlite_conn) -> None:
    """Copy migration-only notification/message links into the target table."""

    sqlite_conn.execute(
        """
        INSERT OR IGNORE INTO inbox_notification_targets (
            notification_id,
            target_kind,
            target_id,
            role
        )
        SELECT
            notification_id,
            ?,
            target_id,
            ?
        FROM temp.inbox_notification_message_targets_migration
        """,
        (INBOX_NOTIFICATION_TARGET_KIND_INBOX_MESSAGE, INBOX_NOTIFICATION_TARGET_ROLE_PRIMARY),
    )
    sqlite_conn.execute("DROP TABLE IF EXISTS temp.inbox_notification_message_targets_migration")


def _notification_id_migration_expr(
    marker_columns: dict[str, sqlite_migrations.ColumnInfo],
    notification_columns: set[str],
) -> Optional[str]:
    """Build a migration-only expression for resolving notification ids."""

    notification_id_exprs = []
    if "inbox_notification_id" in marker_columns:
        notification_id_exprs.append("""
            (
                SELECT inbox_notifications.id
                FROM inbox_notifications
                WHERE inbox_notifications.id = old.inbox_notification_id
            )
            """)
    if "inbox_message_id" in marker_columns and "legacy_inbox_id" in notification_columns:
        notification_id_exprs.append("""
            (
                SELECT inbox_notifications.id
                FROM inbox_notifications
                WHERE inbox_notifications.legacy_inbox_id = old.inbox_message_id
            )
            """)

    if not notification_id_exprs:
        return None
    if len(notification_id_exprs) == 1:
        return notification_id_exprs[0]
    return f"COALESCE({', '.join(notification_id_exprs)})"


def _migrate_ensure_baton_tables() -> None:
    """Create baton tables on existing databases."""
    try:
        engine = _database_module().engine
        BatonModel.__table__.create(bind=engine, checkfirst=True)
        BatonEventModel.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Migration check for baton tables failed: {e}")


def _migrate_ensure_presence_tables() -> None:
    """Create provider-neutral presence tables on existing databases."""
    try:
        engine = _database_module().engine
        PresenceWorkItemModel.__table__.create(bind=engine, checkfirst=True)
        PresenceThreadModel.__table__.create(bind=engine, checkfirst=True)
        PresenceMessageModel.__table__.create(bind=engine, checkfirst=True)
        ProcessedProviderEventModel.__table__.create(bind=engine, checkfirst=True)
        PresenceInboxNotificationModel.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Migration check for presence tables failed: {e}")
        return

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            column_info = sqlite_migrations.table_column_info(conn, "presence_inbox_notifications")
            notification_columns = sqlite_migrations.table_columns(conn, "inbox_notifications")
            if not column_info:
                return

            needs_rebuild = (
                "inbox_message_id" in column_info
                or "inbox_notification_id" not in column_info
                or not bool(column_info["inbox_notification_id"][3])
            )
            if not needs_rebuild:
                return

            notification_id_expr = _notification_id_migration_expr(
                column_info, notification_columns
            )
            sqlite_migrations.rebuild_table(
                conn,
                table_name="presence_inbox_notifications",
                create_sql="""
                    CREATE TABLE presence_inbox_notifications (
                        id INTEGER NOT NULL,
                        receiver_id VARCHAR NOT NULL,
                        presence_message_id INTEGER NOT NULL,
                        inbox_notification_id INTEGER NOT NULL,
                        created_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        UNIQUE (receiver_id, presence_message_id),
                        FOREIGN KEY(presence_message_id)
                            REFERENCES presence_messages (id) ON DELETE CASCADE,
                        FOREIGN KEY(inbox_notification_id)
                            REFERENCES inbox_notifications (id) ON DELETE CASCADE
                    )
                """,
                copy_sql=(
                    f"""
                    INSERT INTO presence_inbox_notifications (
                        id,
                        receiver_id,
                        presence_message_id,
                        inbox_notification_id,
                        created_at
                    )
                    SELECT
                        old.id,
                        old.receiver_id,
                        old.presence_message_id,
                        {notification_id_expr},
                        old.created_at
                    FROM {{old_table}} AS old
                    WHERE {notification_id_expr} IS NOT NULL
                """
                    if notification_id_expr is not None
                    else None
                ),
            )
            logger.info("Migration: rebuilt presence_inbox_notifications with notification ids")
    except Exception as e:
        logger.warning(f"Migration check for presence notification ids failed: {e}")


def _migrate_ensure_agent_runtime_tables() -> None:
    """Create CAO agent runtime contract tables on existing databases."""
    try:
        AgentRuntimeNotificationModel.__table__.create(
            bind=_database_module().engine, checkfirst=True
        )
    except Exception as e:
        logger.warning(f"Migration check for agent runtime tables failed: {e}")
        return

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            column_info = sqlite_migrations.table_column_info(conn, "agent_runtime_notifications")
            notification_columns = sqlite_migrations.table_columns(conn, "inbox_notifications")
            if not column_info:
                return

            needs_rebuild = (
                "inbox_message_id" in column_info
                or "inbox_notification_id" not in column_info
                or not bool(column_info["inbox_notification_id"][3])
            )
            if not needs_rebuild:
                return

            notification_id_expr = _notification_id_migration_expr(
                column_info, notification_columns
            )
            sqlite_migrations.rebuild_table(
                conn,
                table_name="agent_runtime_notifications",
                create_sql="""
                    CREATE TABLE agent_runtime_notifications (
                        id INTEGER NOT NULL,
                        agent_id VARCHAR NOT NULL,
                        source_kind VARCHAR NOT NULL,
                        source_id VARCHAR NOT NULL,
                        inbox_notification_id INTEGER NOT NULL,
                        created_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        UNIQUE (agent_id, source_kind, source_id),
                        FOREIGN KEY(inbox_notification_id)
                            REFERENCES inbox_notifications (id) ON DELETE CASCADE
                    )
                """,
                copy_sql=(
                    f"""
                    INSERT INTO agent_runtime_notifications (
                        id,
                        agent_id,
                        source_kind,
                        source_id,
                        inbox_notification_id,
                        created_at
                    )
                    SELECT
                        old.id,
                        old.agent_id,
                        old.source_kind,
                        old.source_id,
                        {notification_id_expr},
                        old.created_at
                    FROM {{old_table}} AS old
                    WHERE {notification_id_expr} IS NOT NULL
                """
                    if notification_id_expr is not None
                    else None
                ),
            )
            logger.info("Migration: rebuilt agent_runtime_notifications with notification ids")
    except Exception as e:
        logger.warning(f"Migration check for agent runtime notification ids failed: {e}")


def _migrate_drop_legacy_inbox_notification_ids() -> None:
    """Drop migration-only legacy inbox id lookup after marker rows are translated."""

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            columns = sqlite_migrations.table_column_info(conn, "inbox_notifications")
            if "legacy_inbox_id" not in columns:
                return

            sqlite_migrations.rebuild_table(
                conn,
                table_name="inbox_notifications",
                create_sql=_inbox_notifications_create_sql(),
                copy_sql=_inbox_notifications_copy_sql(columns),
            )
            logger.info("Migration: rebuilt inbox_notifications without legacy inbox ids")
    except Exception as e:
        logger.warning(f"Migration check for legacy inbox notification ids failed: {e}")


def _migrate_drop_legacy_inbox_table() -> None:
    """Drop the old overloaded inbox table after semantic migrations are in place."""

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            dropped = sqlite_migrations.drop_tables_if_exist(conn, ["inbox"])
            if dropped:
                logger.info("Migration: dropped legacy overloaded inbox table")
    except Exception as e:
        logger.warning(f"Migration check for legacy inbox table failed: {e}")


def _migrate_drop_monitoring_session_peers() -> None:
    """Drop the obsolete ``monitoring_session_peers`` table."""

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            dropped = sqlite_migrations.drop_tables_if_exist(conn, ["monitoring_session_peers"])
            if dropped:
                logger.info("Migration: dropped obsolete monitoring_session_peers table")
    except Exception as e:
        logger.warning(f"Migration check for monitoring_session_peers failed: {e}")


def _migrate_add_allowed_tools() -> None:
    """Add allowed_tools column to terminals table if missing (schema migration)."""

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            if sqlite_migrations.add_column_if_missing(
                conn, "terminals", "allowed_tools", "allowed_tools TEXT"
            ):
                logger.info("Migration: added allowed_tools column to terminals table")
    except Exception as e:
        logger.warning(f"Migration check for allowed_tools failed: {e}")

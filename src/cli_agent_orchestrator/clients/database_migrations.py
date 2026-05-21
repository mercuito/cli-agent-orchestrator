"""CAO database schema migration decisions."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

from cli_agent_orchestrator import constants
from cli_agent_orchestrator.clients import sqlite_migrations
from cli_agent_orchestrator.clients.baton_store import BatonEventModel, BatonModel
from cli_agent_orchestrator.clients.cao_event_store import (
    CAO_EVENT_AGENT_PARTICIPANTS_AGENT_OCCURRED_INDEX,
    CaoEventAgentParticipantModel,
    CaoEventModel,
)
from cli_agent_orchestrator.clients.flow_store import FlowModel
from cli_agent_orchestrator.clients.runtime_notification_store import (
    AgentRuntimeNotificationModel,
    MonitoringSessionModel,
)
from cli_agent_orchestrator.inbox import ensure_notification_table
from cli_agent_orchestrator.clients.workspace_context_store import (
    ContextWorkspaceModel,
    WorkspaceContextModel,
    WorkspaceContextObjectMappingModel,
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
    _migrate_ensure_flow_tables()
    _migrate_ensure_agent_runtime_tables()
    _migrate_ensure_workspace_context_tables()
    _migrate_ensure_cao_event_tables()
    _migrate_drop_legacy_inbox_notification_ids()
    _migrate_ensure_agent_runtime_tables()
    _migrate_ensure_workspace_context_tables()
    _migrate_ensure_cao_event_tables()
    _migrate_drop_removed_linear_cao_events()
    _migrate_drop_legacy_inbox_table()
    _migrate_add_allowed_tools()
    _migrate_add_terminal_agent_id()
    _migrate_enforce_single_terminal_per_agent()
    _migrate_add_terminal_workspace_context_id()
    _migrate_backfill_terminal_workspace_context_id()
    _migrate_monitoring_sessions_agent_ids()
    _migrate_drop_monitoring_session_peers()
    _migrate_drop_linear_and_provider_conversation_tables()


def _migrate_ensure_semantic_inbox_tables() -> None:
    """Create and cut over the collapsed agent-to-agent inbox notification table."""
    try:
        engine = _database_module().engine
        ensure_notification_table(engine)
    except Exception as e:
        logger.warning(f"Migration check for inbox notification table failed: {e}")
        return

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            columns = sqlite_migrations.table_column_info(conn, "inbox_notifications")
            if not columns:
                return

            needs_rebuild = (
                "sender_agent_id" not in columns
                or "receiver_agent_id" not in columns
                or "receiver_id" in columns
                or "body" not in columns
                or "source_kind" in columns
                or "source_id" in columns
                or "metadata_json" in columns
                or "message_id" in columns
                or "legacy_inbox_id" in columns
            )
            if needs_rebuild:
                sqlite_migrations.rebuild_table(
                    conn,
                    table_name="inbox_notifications",
                    create_sql=_inbox_notifications_create_sql(),
                    copy_sql=_inbox_notifications_copy_sql(columns),
                )
                logger.info("Migration: collapsed inbox notifications into agent-owned rows")

            dropped = sqlite_migrations.drop_tables_if_exist(
                conn,
                (
                    "inbox_notification_targets",
                    "inbox_messages",
                ),
            )
            if dropped:
                logger.info("Migration: dropped %s legacy inbox side tables", dropped)
    except Exception as e:
        logger.warning(f"Migration check for inbox notification cutover failed: {e}")
        raise


def _inbox_notifications_create_sql() -> str:
    return """
        CREATE TABLE inbox_notifications (
            id INTEGER NOT NULL,
            sender_agent_id VARCHAR NOT NULL,
            receiver_agent_id VARCHAR NOT NULL,
            body TEXT NOT NULL,
            status VARCHAR NOT NULL,
            created_at DATETIME NOT NULL,
            delivered_at DATETIME,
            failed_at DATETIME,
            error_detail TEXT,
            PRIMARY KEY (id)
        )
    """


def _inbox_notifications_copy_sql(
    columns: dict[str, sqlite_migrations.ColumnInfo],
) -> str:
    target_columns = [
        "id",
        "sender_agent_id",
        "receiver_agent_id",
        "body",
        "status",
        "created_at",
        "delivered_at",
        "failed_at",
        "error_detail",
    ]
    source_exprs = [
        "old.id",
        _sender_agent_id_expr(columns),
        _receiver_agent_id_expr(columns),
        _body_expr(columns),
        "old.status",
        "old.created_at",
        "old.delivered_at",
        "old.failed_at",
        "old.error_detail",
    ]
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


def _sender_agent_id_expr(columns: dict[str, sqlite_migrations.ColumnInfo]) -> str:
    if "sender_agent_id" in columns:
        return _normalize_agent_id_expr("old.sender_agent_id", "'system'")
    if "source_id" in columns or "message_id" in columns:
        source_id_expr = _column_or_message_expr(columns, "source_id", "'system'")
        source_kind_expr = _column_or_message_expr(columns, "source_kind", "'system'")
        return f"""
            COALESCE(
                CASE
                    WHEN {source_kind_expr} IN ('terminal', 'plain') THEN (
                        SELECT terminals.agent_id
                        FROM terminals
                        WHERE terminals.id = {source_id_expr}
                          AND terminals.agent_id IS NOT NULL
                          AND TRIM(terminals.agent_id) != ''
                    )
                    ELSE NULL
                END,
                'system'
            )
            """
    if "sender_id" in columns:
        return _normalize_agent_id_expr("old.sender_id", "'system'")
    return "'system'"


def _receiver_agent_id_expr(columns: dict[str, sqlite_migrations.ColumnInfo]) -> str:
    if "receiver_agent_id" in columns:
        return _normalize_agent_id_expr("old.receiver_agent_id", "''")
    if "receiver_id" in columns:
        return f"""
            COALESCE(
                (
                    SELECT terminals.agent_id
                    FROM terminals
                    WHERE terminals.id = old.receiver_id
                      AND terminals.agent_id IS NOT NULL
                      AND TRIM(terminals.agent_id) != ''
                ),
                {_normalize_agent_alias_expr("old.receiver_id")},
                ''
            )
            """
    return "''"


def _normalize_agent_id_expr(value_expr: str, fallback_expr: str) -> str:
    alias_expr = _normalize_agent_alias_expr(value_expr)
    return f"COALESCE({alias_expr}, NULLIF(TRIM({value_expr}), ''), {fallback_expr})"


def _normalize_agent_alias_expr(value_expr: str) -> str:
    stripped = f"substr({value_expr}, 7)"
    return f"""
        CASE
            WHEN {value_expr} LIKE 'agent:%:%'
                THEN NULLIF(substr({stripped}, 1, instr({stripped}, ':') - 1), '')
            WHEN {value_expr} LIKE 'agent:%'
                THEN NULLIF({stripped}, '')
            ELSE NULL
        END
        """


def _body_expr(columns: dict[str, sqlite_migrations.ColumnInfo]) -> str:
    if "body" in columns:
        return "old.body"
    if "message_id" in columns:
        return """
            COALESCE(
                (
                    SELECT inbox_messages.body
                    FROM inbox_messages
                    WHERE inbox_messages.id = old.message_id
                ),
                ''
            )
            """
    return "''"


def _column_or_message_expr(
    columns: dict[str, sqlite_migrations.ColumnInfo], name: str, fallback: str
) -> str:
    if name in columns:
        return f"old.{name}"
    if "message_id" in columns:
        return f"""
            COALESCE(
                (
                    SELECT inbox_messages.{name}
                    FROM inbox_messages
                    WHERE inbox_messages.id = old.message_id
                ),
                {fallback}
            )
            """
    return fallback


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


def _migrate_ensure_flow_tables() -> None:
    """Create and backfill flow metadata columns on existing databases."""
    try:
        engine = _database_module().engine
        FlowModel.__table__.create(bind=engine, checkfirst=True)
        with engine.begin() as connection:
            columns = {
                str(row[1]) for row in connection.exec_driver_sql("PRAGMA table_info(flows)")
            }
            if "agent_id" not in columns:
                connection.exec_driver_sql("ALTER TABLE flows ADD COLUMN agent_id VARCHAR")
                connection.exec_driver_sql(
                    "UPDATE flows SET agent_id = 'code_supervisor' WHERE agent_id IS NULL"
                )
            if "provider" not in columns:
                connection.exec_driver_sql("ALTER TABLE flows ADD COLUMN provider VARCHAR")
                connection.exec_driver_sql(
                    "UPDATE flows SET provider = ? WHERE provider IS NULL",
                    (constants.DEFAULT_PROVIDER,),
                )
            if "script" not in columns:
                connection.exec_driver_sql("ALTER TABLE flows ADD COLUMN script VARCHAR")
                connection.exec_driver_sql("UPDATE flows SET script = '' WHERE script IS NULL")
    except Exception as e:
        logger.warning(f"Migration check for flow tables failed: {e}")


def _migrate_ensure_workspace_context_tables() -> None:
    """Create workspace context registry tables on existing databases."""
    try:
        engine = _database_module().engine
        WorkspaceContextModel.__table__.create(bind=engine, checkfirst=True)
        WorkspaceContextObjectMappingModel.__table__.create(bind=engine, checkfirst=True)
        ContextWorkspaceModel.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Migration check for workspace context tables failed: {e}")
        return

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            if not sqlite_migrations.table_exists(conn, "context_workspaces"):
                return
            columns = sqlite_migrations.table_columns(conn, "context_workspaces")
            old_agent_column = "agent_" + "identity_id"
            if "agent_id" in columns and old_agent_column not in columns:
                return
            if old_agent_column not in columns:
                return
            offenders = conn.execute(f"""
                SELECT id
                FROM context_workspaces
                WHERE {old_agent_column} IS NULL
                   OR TRIM({old_agent_column}) = ''
                """).fetchall()
            if offenders:
                ids = ", ".join(str(row[0]) for row in offenders)
                raise RuntimeError(
                    "Cannot migrate context_workspaces to agent_id while anonymous "
                    f"context workspace rows exist: {ids}"
                )
            active_terminal_expr = (
                "old.active_terminal_id" if "active_terminal_id" in columns else "NULL"
            )
            sqlite_migrations.rebuild_table(
                conn,
                table_name="context_workspaces",
                create_sql="""
                    CREATE TABLE context_workspaces (
                        id INTEGER NOT NULL,
                        agent_id VARCHAR NOT NULL,
                        workspace_context_id VARCHAR NOT NULL,
                        root_path VARCHAR NOT NULL,
                        active_terminal_id VARCHAR,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        CONSTRAINT uq_context_workspace_agent_context
                            UNIQUE (agent_id, workspace_context_id),
                        FOREIGN KEY(workspace_context_id)
                            REFERENCES workspace_contexts (id) ON DELETE CASCADE
                    )
                """,
                copy_sql=f"""
                    INSERT INTO context_workspaces (
                        id,
                        agent_id,
                        workspace_context_id,
                        root_path,
                        active_terminal_id,
                        created_at,
                        updated_at
                    )
                    SELECT
                        old.id,
                        TRIM(old.{old_agent_column}),
                        old.workspace_context_id,
                        old.root_path,
                        {active_terminal_expr},
                        old.created_at,
                        old.updated_at
                    FROM {{old_table}} AS old
                """,
            )
            logger.info("Migration: converted context_workspaces to agent_id-owned schema")
    except Exception as e:
        logger.warning(f"Migration check for context workspace agent_id failed: {e}")
        raise


def _migrate_ensure_cao_event_tables() -> None:
    """Create durable CAO event log tables on existing databases."""
    engine = _database_module().engine
    CaoEventModel.__table__.create(bind=engine, checkfirst=True)
    CaoEventAgentParticipantModel.__table__.create(bind=engine, checkfirst=True)
    event_table = CaoEventModel.__tablename__
    participant_table = CaoEventAgentParticipantModel.__tablename__
    event_id_column = CaoEventAgentParticipantModel.event_id.name
    agent_column = CaoEventAgentParticipantModel.agent_id.name
    occurred_at_column = CaoEventAgentParticipantModel.occurred_at.name
    kind_column = CaoEventModel.kind.name
    legacy_type_key_column = "event_type_key"
    with engine.begin() as connection:
        event_columns = {
            str(row[1]) for row in connection.exec_driver_sql(f"PRAGMA table_info({event_table})")
        }
        if kind_column not in event_columns:
            connection.exec_driver_sql(
                f"ALTER TABLE {event_table} ADD COLUMN {kind_column} VARCHAR"
            )
            event_columns.add(kind_column)
        if legacy_type_key_column in event_columns:
            legacy_kind_by_type_key = _cao_event_kind_by_legacy_type_key()
            for legacy_type_key, kind in legacy_kind_by_type_key.items():
                connection.exec_driver_sql(
                    f"""
                    UPDATE {event_table}
                    SET {kind_column} = ?
                    WHERE {legacy_type_key_column} = ?
                    """,
                    (kind, legacy_type_key),
                )
            unresolved_rows = connection.exec_driver_sql(f"""
                SELECT {event_id_column}, {legacy_type_key_column}
                FROM {event_table}
                WHERE {kind_column} IS NULL OR {kind_column} = ''
            """).fetchall()
            if unresolved_rows:
                unresolved = ", ".join(f"{row[0]}={row[1]}" for row in unresolved_rows)
                raise ValueError(f"Unresolved legacy CAO event type keys: {unresolved}")
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_cao_events_event_type_key")
            connection.exec_driver_sql(
                f"ALTER TABLE {event_table} DROP COLUMN {legacy_type_key_column}"
            )
        connection.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_cao_events_{kind_column} "
            f"ON {event_table} ({kind_column})"
        )

        participant_columns = {
            str(row[1])
            for row in connection.exec_driver_sql(f"PRAGMA table_info({participant_table})")
        }
        old_agent_column = "agent_" + "identity_id"
        if agent_column not in participant_columns and old_agent_column in participant_columns:
            connection.exec_driver_sql(
                f"DROP INDEX IF EXISTS {CAO_EVENT_AGENT_PARTICIPANTS_AGENT_OCCURRED_INDEX}"
            )
            connection.exec_driver_sql(
                f"ALTER TABLE {participant_table} "
                f"RENAME COLUMN {old_agent_column} TO {agent_column}"
            )
            participant_columns.remove(old_agent_column)
            participant_columns.add(agent_column)
        if occurred_at_column not in participant_columns:
            connection.exec_driver_sql(
                f"ALTER TABLE {participant_table} ADD COLUMN {occurred_at_column} DATETIME"
            )
            connection.exec_driver_sql(f"""
                UPDATE {participant_table}
                SET {occurred_at_column} = (
                    SELECT {event_table}.{occurred_at_column}
                    FROM {event_table}
                    WHERE {event_table}.{event_id_column} = {participant_table}.{event_id_column}
                )
            """)
        connection.exec_driver_sql(
            f"DROP INDEX IF EXISTS {CAO_EVENT_AGENT_PARTICIPANTS_AGENT_OCCURRED_INDEX}"
        )
        connection.exec_driver_sql(f"""
            CREATE INDEX IF NOT EXISTS {CAO_EVENT_AGENT_PARTICIPANTS_AGENT_OCCURRED_INDEX}
            ON {participant_table} ({agent_column}, {occurred_at_column}, {event_id_column})
        """)


def _migrate_drop_removed_linear_cao_events() -> None:
    """Remove durable Linear CAO event rows whose event classes no longer exist."""
    engine = _database_module().engine
    event_table = CaoEventModel.__tablename__
    participant_table = CaoEventAgentParticipantModel.__tablename__
    event_id_column = CaoEventModel.event_id.name
    participant_event_id_column = CaoEventAgentParticipantModel.event_id.name
    kind_column = CaoEventModel.kind.name
    event_name_column = CaoEventModel.event_name.name
    with engine.begin() as connection:
        table_names = {
            str(row[0])
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if event_table not in table_names:
            return
        event_columns = {
            str(row[1]) for row in connection.exec_driver_sql(f"PRAGMA table_info({event_table})")
        }
        if kind_column not in event_columns:
            return
        removed_event_ids = [
            str(row[0])
            for row in connection.exec_driver_sql(
                f"""
                SELECT {event_id_column}
                FROM {event_table}
                WHERE {kind_column} LIKE 'linear.%'
                   OR {event_name_column} LIKE 'linear.%'
                """
            ).fetchall()
        ]
        if not removed_event_ids:
            return
        for event_id in removed_event_ids:
            if participant_table in table_names:
                connection.exec_driver_sql(
                    f"DELETE FROM {participant_table} WHERE {participant_event_id_column} = ?",
                    (event_id,),
                )
            connection.exec_driver_sql(
                f"DELETE FROM {event_table} WHERE {event_id_column} = ?",
                (event_id,),
            )
        logger.info("Migration: dropped %s removed Linear CAO event rows", len(removed_event_ids))


def _cao_event_kind_by_legacy_type_key() -> dict[str, str]:
    from cli_agent_orchestrator.events.serialization import cao_event_kind
    from cli_agent_orchestrator.runtime.events import RUNTIME_CAO_EVENTS

    return {
        f"{event_type.__module__}.{event_type.__qualname__}": cao_event_kind(event_type)
        for event_type in RUNTIME_CAO_EVENTS
    }


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

            notification_fk_is_current = sqlite_migrations.foreign_key_references_table(
                conn,
                "agent_runtime_notifications",
                "inbox_notification_id",
                "inbox_notifications",
            )
            needs_rebuild = (
                "inbox_message_id" in column_info
                or "inbox_notification_id" not in column_info
                or "idempotency_key" not in column_info
                or "source_kind" in column_info
                or "source_id" in column_info
                or not bool(column_info["inbox_notification_id"][3])
                or not notification_fk_is_current
            )
            if not needs_rebuild:
                return

            notification_id_expr = _notification_id_migration_expr(
                column_info, notification_columns
            )
            idempotency_key_expr = _agent_runtime_idempotency_key_expr(column_info)
            sqlite_migrations.rebuild_table(
                conn,
                table_name="agent_runtime_notifications",
                create_sql="""
                    CREATE TABLE agent_runtime_notifications (
                        id INTEGER NOT NULL,
                        agent_id VARCHAR NOT NULL,
                        idempotency_key VARCHAR NOT NULL,
                        inbox_notification_id INTEGER NOT NULL,
                        created_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        UNIQUE (agent_id, idempotency_key),
                        FOREIGN KEY(inbox_notification_id)
                            REFERENCES inbox_notifications (id) ON DELETE CASCADE
                    )
                """,
                copy_sql=(
                    f"""
                    INSERT INTO agent_runtime_notifications (
                        id,
                        agent_id,
                        idempotency_key,
                        inbox_notification_id,
                        created_at
                    )
                    SELECT
                        old.id,
                        old.agent_id,
                        {idempotency_key_expr},
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


def _agent_runtime_idempotency_key_expr(
    columns: dict[str, sqlite_migrations.ColumnInfo],
) -> str:
    if "idempotency_key" in columns:
        return "old.idempotency_key"
    if "source_kind" in columns and "source_id" in columns:
        return "old.source_kind || ':' || old.source_id"
    if "sender_kind" in columns and "sender_id" in columns:
        return "old.sender_kind || ':' || old.sender_id"
    return "'legacy:' || old.id"


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


def _migrate_monitoring_sessions_agent_ids() -> None:
    """Rebuild monitoring sessions to be keyed by durable CAO agent ids."""

    try:
        engine = _database_module().engine
        MonitoringSessionModel.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Migration check for monitoring_sessions table failed: {e}")
        return

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            columns = sqlite_migrations.table_column_info(conn, "monitoring_sessions")
            if not columns or "agent_id" in columns and "terminal_id" not in columns:
                return

            if "terminal_id" in columns:
                agent_id_expr = """
                    (
                        SELECT terminals.agent_id
                        FROM terminals
                        WHERE terminals.id = old.terminal_id
                          AND terminals.agent_id IS NOT NULL
                          AND TRIM(terminals.agent_id) != ''
                    )
                """
                where_clause = f"WHERE {agent_id_expr} IS NOT NULL"
            else:
                agent_id_expr = "NULLIF(TRIM(old.agent_id), '')"
                where_clause = f"WHERE {agent_id_expr} IS NOT NULL"

            sqlite_migrations.rebuild_table(
                conn,
                table_name="monitoring_sessions",
                create_sql="""
                    CREATE TABLE monitoring_sessions (
                        id VARCHAR NOT NULL,
                        agent_id VARCHAR NOT NULL,
                        label VARCHAR,
                        started_at DATETIME NOT NULL,
                        ended_at DATETIME,
                        PRIMARY KEY (id)
                    )
                """,
                copy_sql=f"""
                    INSERT INTO monitoring_sessions (
                        id,
                        agent_id,
                        label,
                        started_at,
                        ended_at
                    )
                    SELECT
                        old.id,
                        {agent_id_expr},
                        old.label,
                        old.started_at,
                        old.ended_at
                    FROM {{old_table}} AS old
                    {where_clause}
                """,
            )
            logger.info("Migration: rebuilt monitoring_sessions with agent ids")
    except Exception as e:
        logger.warning(f"Migration check for monitoring session agent ids failed: {e}")


def _migrate_drop_monitoring_session_peers() -> None:
    """Drop the obsolete ``monitoring_session_peers`` table."""

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            dropped = sqlite_migrations.drop_tables_if_exist(conn, ["monitoring_session_peers"])
            if dropped:
                logger.info("Migration: dropped obsolete monitoring_session_peers table")
    except Exception as e:
        logger.warning(f"Migration check for monitoring_session_peers failed: {e}")


def _migrate_drop_linear_and_provider_conversation_tables() -> None:
    """Drop tables owned by the removed Linear provider and conversation cache."""

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            dropped = sqlite_migrations.drop_tables_if_exist(
                conn,
                (
                    "provider_conversation_inbox_notifications",
                    "provider_conversation_messages",
                    "provider_conversation_threads",
                    "processed_provider_events",
                    "provider_work_items",
                    "linear_monitor_watermarks",
                ),
            )
            if dropped:
                logger.info("Migration: dropped %s Linear/provider conversation tables", dropped)
    except Exception as e:
        logger.warning(f"Migration check for Linear/provider conversation table drop failed: {e}")


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


def _migrate_add_terminal_agent_id() -> None:
    """Convert terminals to the hard-cutover agent-owned schema."""

    old_agent_column = "agent_" + "identity_id"
    old_profile_column = "agent_" + "profile"
    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            if not sqlite_migrations.table_exists(conn, "terminals"):
                return
            columns = sqlite_migrations.table_columns(conn, "terminals")
            if "agent_id" not in columns and old_agent_column not in columns:
                return
            source_agent_column = "agent_id" if "agent_id" in columns else old_agent_column
            offenders = conn.execute(f"""
                SELECT id
                FROM terminals
                WHERE {source_agent_column} IS NULL
                   OR TRIM({source_agent_column}) = ''
                """).fetchall()
            if offenders:
                ids = ", ".join(str(row[0]) for row in offenders)
                raise RuntimeError(
                    "Cannot migrate terminals to agent_id NOT NULL while anonymous "
                    f"terminal rows exist: {ids}"
                )

            has_workspace = "workspace_context_id" in columns
            allowed_tools_expr = "allowed_tools" if "allowed_tools" in columns else "NULL"
            if (
                source_agent_column == "agent_id"
                and has_workspace
                and old_profile_column not in columns
                and old_agent_column not in columns
            ):
                return

            rows = conn.execute(f"""
                SELECT
                    id,
                    tmux_session,
                    tmux_window,
                    provider,
                    TRIM({source_agent_column}) AS agent_id,
                    {"workspace_context_id" if has_workspace else "NULL"} AS workspace_context_id,
                    {allowed_tools_expr} AS allowed_tools,
                    last_active
                FROM terminals
                """).fetchall()
            conn.execute("ALTER TABLE terminals RENAME TO terminals_old")
            conn.execute("""
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
            conn.executemany(
                """
                INSERT INTO terminals (
                    id,
                    tmux_session,
                    tmux_window,
                    provider,
                    agent_id,
                    workspace_context_id,
                    allowed_tools,
                    last_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row[0],
                        row[1],
                        row[2],
                        row[3],
                        row[4],
                        _nonempty_text(row[5]) or _default_agent_workspace_context_id(str(row[4])),
                        row[6],
                        row[7],
                    )
                    for row in rows
                ],
            )
            conn.execute("DROP TABLE terminals_old")
            logger.info("Migration: converted terminals to agent_id-owned schema")
    except Exception as e:
        logger.warning(f"Migration check for terminal agent_id failed: {e}")
        raise


def _migrate_enforce_single_terminal_per_agent() -> None:
    """Add the durable DB claim that limits each agent to one live terminal."""

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            if not sqlite_migrations.table_exists(conn, "terminals"):
                return
            columns = sqlite_migrations.table_columns(conn, "terminals")
            if "agent_id" not in columns:
                return
            duplicate_rows = conn.execute("""
                SELECT agent_id, GROUP_CONCAT(id, ', ')
                FROM terminals
                GROUP BY agent_id
                HAVING COUNT(*) > 1
            """).fetchall()
            if duplicate_rows:
                details = "; ".join(f"{row[0]}: {row[1]}" for row in duplicate_rows)
                raise RuntimeError(
                    "Cannot enforce one live terminal per agent while duplicate "
                    f"terminal rows exist: {details}"
                )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS " "uq_terminals_agent_id ON terminals(agent_id)"
            )
    except Exception as e:
        logger.warning(f"Migration check for terminal agent uniqueness failed: {e}")
        raise


def _migrate_add_terminal_workspace_context_id() -> None:
    """Add workspace_context_id column to terminals table if missing."""

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            if sqlite_migrations.add_column_if_missing(
                conn, "terminals", "workspace_context_id", "workspace_context_id TEXT"
            ):
                logger.info("Migration: added workspace_context_id column to terminals table")
    except Exception as e:
        logger.warning(f"Migration check for terminal workspace_context_id failed: {e}")


def _migrate_backfill_terminal_workspace_context_id() -> None:
    """Bind agent-managed terminal rows to their default context."""

    try:
        with sqlite_migrations.migration_connection(constants.DATABASE_FILE) as conn:
            if not sqlite_migrations.table_exists(conn, "terminals"):
                return
            terminal_columns = sqlite_migrations.table_columns(conn, "terminals")
            if not {"agent_id", "workspace_context_id"}.issubset(terminal_columns):
                return

            rows = conn.execute("""
                SELECT id, agent_id, workspace_context_id
                FROM terminals
                WHERE agent_id IS NOT NULL
                  AND TRIM(agent_id) != ''
            """).fetchall()
            if not rows:
                return

            now = datetime.now()
            backfilled_count = 0
            for _terminal_id, agent_id, workspace_context_id in rows:
                context_id = _default_agent_workspace_context_id(str(agent_id))
                existing_context_id = _nonempty_text(workspace_context_id)
                if existing_context_id is not None and existing_context_id != context_id:
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO workspace_contexts (
                        id,
                        resolver_id,
                        boundary_provider_id,
                        boundary_object_type,
                        boundary_object_id,
                        status,
                        metadata_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        context_id,
                        "default",
                        "cao",
                        "agent_default",
                        str(agent_id),
                        "active",
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO workspace_context_object_mappings (
                        workspace_context_id,
                        provider_id,
                        object_type,
                        object_id,
                        role,
                        metadata_json,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        context_id,
                        "cao",
                        "agent_default",
                        str(agent_id),
                        "boundary",
                        now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE terminals
                    SET workspace_context_id = ?
                    WHERE id = ?
                    """,
                    (context_id, _terminal_id),
                )
                backfilled_count += 1
            logger.info(
                "Migration: backfilled workspace_context_id for %s agent-managed terminals",
                backfilled_count,
            )
    except Exception as e:
        logger.warning(f"Migration check for terminal workspace_context_id backfill failed: {e}")


def _nonempty_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _default_agent_workspace_context_id(agent_id: str) -> str:
    material = "\n".join(
        [
            "cao",
            "agent_default",
            agent_id,
        ]
    )
    return "wctx_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]

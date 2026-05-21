# Task 05 — SQLite Migration: Drop Tables and Inbox Columns

## Goal

Write the SQLite migration that brings live databases in line with the
post-collapse model. Drops the provider_conversation_* tables, the
`linear_monitor_watermarks` table, and the three obsolete columns on
`inbox_notifications`. After this migration runs, the schema matches the
models defined in Task 04.

## Preconditions

- Tasks 01–04 complete: the production model file already reflects the new
  shape, but a SQLite database from before this work still has the old
  schema.
- `clients/database_migrations.py` no longer creates the obsolete tables
  (Task 01 removed those creation paths). This task adds a *drop* migration
  to clean up existing databases.

## Scope

1. Add a new migration function to
   `src/cli_agent_orchestrator/clients/database_migrations.py`:

   ```python
   def _migrate_drop_linear_and_provider_conversation_tables() -> None:
       """Drop obsolete Linear and provider-conversation cache tables."""
   ```

   The function uses `engine.begin()` and `text()` to issue, idempotently:

   - `DROP TABLE IF EXISTS provider_conversation_messages`
   - `DROP TABLE IF EXISTS provider_conversation_threads`
   - `DROP TABLE IF EXISTS provider_work_items`
   - `DROP TABLE IF EXISTS linear_monitor_watermarks`
   - `DROP TABLE IF EXISTS provider_conversation_inbox_notifications` (the
     transitional marker table referenced in older migrations)

2. Add a second migration function:

   ```python
   def _migrate_collapse_inbox_notification_columns() -> None:
       """Drop source_kind, source_id, metadata_json from inbox_notifications.

       Also rename receiver_agent_id semantics if needed and add sender_agent_id
       if it does not already exist.
       """
   ```

   Steps inside (SQLite, so use the table-rebuild idiom):

   1. Check whether the `inbox_notifications` table has the obsolete columns.
      If not, no-op (idempotent).
   2. If it does:
      - Create `inbox_notifications_new` with the target schema (see
        Task 04 `inbox/store.py:InboxNotificationModel`).
      - Copy rows from the old table:
        - `sender_agent_id` <- `source_id` (since every row had
          `source_kind="plain"` or `"terminal"` and `source_id` was the
          sender's id or terminal id). For `source_kind="terminal"`, look
          up the terminal's `agent_id` if possible; if not resolvable,
          accept the raw value — rows are observability and the worst case
          is a stale-but-valid sender label.
        - `receiver_agent_id` keeps its value.
        - `body`, `status`, `created_at`, `delivered_at`, `failed_at`,
          `error_detail` carry over unchanged.
      - **Rebuild dependent objects.** Per
        `docs/criteria/implementation/migration-discipline.md`, any
        foreign keys, indexes, or triggers referencing
        `inbox_notifications` must be rebuilt to reference the final
        table, not the transitional `inbox_notifications_old`. Check
        with `sqlite_master` and reissue any `CREATE INDEX` or trigger
        statements after the rename.
      - `DROP TABLE inbox_notifications`
      - `ALTER TABLE inbox_notifications_new RENAME TO inbox_notifications`

3. Wire both migrations into the migration runner so they execute on
   startup:

   ```python
   def run_migrations() -> None:
       # ... existing migrations ...
       _migrate_drop_linear_and_provider_conversation_tables()
       _migrate_collapse_inbox_notification_columns()
   ```

   Place them after any migration that previously populated those tables
   (so the destroy step runs once, last).

4. Audit `clients/database_migrations.py` for stale code paths that
   compute against `provider_conversation_inbox_notifications` (line 319
   in pre-Task-01 state). Those branches can be deleted after this
   migration runs because the marker table is gone. Trim them.

## Out of Scope

- The model file (`inbox/store.py`) has already been updated in Task 04
  to the target shape. This task only handles the live database.
- No production code changes here beyond the migration runner.

## Acceptance Criteria

1. Running the test suite against a clean DB succeeds:
   `rm -f ~/.cli-agent-orchestrator/cao.db && uv run pytest -q`.
2. Running the migration against a *pre-collapse* DB succeeds. Construct
   the regression test:
   - Build a SQLite file with the old schema (copy the schema from
     `git show <pre-task-04>:src/cli_agent_orchestrator/clients/database.py`
     or stash a sample).
   - Insert a few rows.
   - Run the migration.
   - Assert the obsolete tables are gone and `inbox_notifications` has the
     new columns + the row data was preserved.

   This regression test should land in
   `test/clients/test_database_migrations.py` (create if needed).
3. `grep -n "provider_conversation\|linear_monitor" src/cli_agent_orchestrator/clients/database_migrations.py` returns matches only inside the new drop-migration function.
4. Schema introspection on a migrated DB confirms `source_kind`,
   `source_id`, and `metadata_json` are no longer columns of
   `inbox_notifications`.

## Criteria to Consult

- `migration-discipline` — Read the SQLite section carefully. Dependent
  foreign keys and indexes must be rebuilt against the final table name.
- `do-not-assume-backwards-compatibility` — No fallback path that keeps
  the obsolete columns "just in case." Drop them.
- `readable-and-explicit` — Migration function names must say what they do
  (drop, not "ensure"). Comments capture *why* the rebuild idiom is needed
  in SQLite (no `ALTER TABLE ... DROP COLUMN` until SQLite 3.35+, and we
  rebuild to also rename semantics safely).
- `test-validity-preserved` — The migration regression test must validate
  the actual data preservation, not just that the migration ran without
  raising.

## Notes for the Implementing Agent

- SQLite added `ALTER TABLE ... DROP COLUMN` in 3.35. If your sqlite is
  recent enough, you can use it for the column drops, but the table
  rebuild idiom is safer for schema renames (column-name semantics shifts
  from `source_id` carrying both sender-and-receiver-flavored data to a
  cleanly named `sender_agent_id`). Prefer the rebuild idiom for the inbox
  columns specifically.
- The plain `DROP TABLE IF EXISTS` is fine for the four obsolete tables
  since nothing references them after Task 01.
- Don't forget triggers. Check `sqlite_master.type='trigger'` for any
  attached to `inbox_notifications`.
- This is the only task in this plan where data loss is on the line. The
  user has explicitly OK'd dropping the four obsolete tables (the data
  there was Linear-cache anyway and has no value after Linear is gone).
  The inbox notification rows are preserved through the column-collapse.

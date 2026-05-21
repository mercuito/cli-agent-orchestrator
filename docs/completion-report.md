# Completion report

Per-task ledger of review-loop findings. Each task that goes through the Review Gate (see any `docs/issues/NNNN-*.md`) appends a section here with its findings and resolutions.

Entries are appended; never edit prior entries.

## Template

```markdown
## NNNN — short slug

### Review round 1 — <date>

- **Finding:** what the reviewer reported
- **Accepted as valid because:** brief reasoning
- **Fix:** what changed and where
- **Evidence:** test name, log excerpt, or commit hash

### Review round N — <date>

(Repeat for each round.)

### Clean passes

- Pass 1: <date>, reviewer note
- Pass 2: <date>, reviewer note
```

A task is complete only after **two** successive clean review passes are recorded.

---

## 0004 — inbox schema cutover

### Review round 1 — 2026-05-21

- **Finding:** A migration-only helper for provider conversation marker ids remained after the `provider_conversation_inbox_notifications` table was removed.
- **Accepted as valid because:** The task requires no dead references to dropped-table compatibility paths, and the helper no longer had any caller after the cutover.
- **Fix:** Removed `_provider_message_id_migration_expr` from `src/cli_agent_orchestrator/clients/database_migrations.py`.
- **Evidence:** `uv run pytest test/clients/test_database.py test/provider_conversations/test_persistence.py test/api/test_linear_app_routes.py -q` passed.

### Clean passes

- Pass 1: 2026-05-21, criteria review found the schema/caller cutover aligned with the issue checklist after the unused helper removal.
- Pass 2: 2026-05-21, legacy-reference sweep found no deleted ORM models/helpers, no new `inbox/` package, and no prompt/protocol production diff.

## 0005 — inbox plain send

### Review round 1 — 2026-05-21

- **Finding:** Plain-source notifications persisted `source_id` correctly, but the legacy read-shaped `InboxMessageRecord.sender_id` was synthesized as `"plain"` instead of the sender agent id.
- **Accepted as valid because:** `PlainSource(sender_agent_id)` is the public send contract for this slice, and downstream read/status views should not lose the sender identity for plain agent messages.
- **Fix:** Updated `src/cli_agent_orchestrator/inbox/store.py` so plain notifications synthesize `sender_id` from `source_id`, matching terminal-backed notifications.
- **Evidence:** `uv run pytest test/clients/test_database.py::TestInboxOperations::test_plain_notification_read_shape_reports_sender_agent -q` failed before the fix and passed after it.

### Clean passes

- Pass 1: 2026-05-21, acceptance checklist review found the new `inbox/` public API, agent-addressed POST route, MCP parameter rename, moved readiness handler, and tracer test aligned after the sender-id fix.
- Pass 2: 2026-05-21, criteria sweep found no test-only inbox production seams, no backend terminal POST route, and no remaining production imports of `services.inbox_service`.

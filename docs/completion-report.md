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

## 0006 — inbox read

### Review round 1 — 2026-05-21

- **Finding:** The new read result kept internal `replyable` compatibility names while the issue defines `ReadResult.can_reply`.
- **Accepted as valid because:** `do-not-assume-backwards-compatibility` and `migration-discipline` forbid preserving old names unless the plan explicitly requires them. The MCP response is allowed to keep the issue-required `"replyable"` JSON key, but internal read surfaces must use the new `can_reply` vocabulary.
- **Fix:** Removed the `ReadResult.replyable` alias and renamed the Linear read helper field to `can_reply`; the MCP mapper now translates `can_reply` to the response key.
- **Evidence:** Static search found no internal `.replyable`, `replyable: bool`, or `def replyable` matches under `src/` or `test/`.

### Review round 2 — 2026-05-21

- **Finding:** MCP read retried `inbox.read` with the caller terminal id after an agent-id authorization failure, preserving terminal-addressed receiver compatibility.
- **Accepted as valid because:** The task defines `inbox.read(notification_id, caller_agent_id)` as the new shape, and the plan does not authorize a compatibility period for terminal-addressed reads.
- **Fix:** Removed the terminal-id retry and migrated affected MCP tests to agent-addressed receiver notifications.
- **Evidence:** `rg` found no `_read_inbox_notification_for_mcp_caller` or `caller_agent_id=caller_terminal_id` matches under `src/` or `test/`.

### Review round 3 — 2026-05-21

- **Finding:** MCP read still fell back to using the caller terminal id when terminal metadata could not resolve an agent id.
- **Accepted as valid because:** That was another silent bridge from terminal identity to the new agent-id caller contract.
- **Fix:** MCP read now requires `_agent_id_for_terminal(caller_terminal_id)` to resolve successfully before calling `inbox.read`; the sender fallback test now uses an agent-addressed receiver.
- **Evidence:** `uv run pytest test/services/test_inbox_read.py test/services/test_inbox_service.py test/api/test_inbox_messages.py test/provider_conversations test/mcp_server/test_inbox_tools.py -q` passed with 92 tests.

### Clean passes

- Pass 1: 2026-05-21, criteria-focused review found no valid findings after both terminal-id fallbacks were removed; verification included legacy read surface searches, `test/services/test_inbox_read.py test/mcp_server/test_inbox_tools.py`, provider conversation bridge/reply tests, and compileall.
- Pass 2: 2026-05-21, independent review found no valid findings; verification included criteria catalog, `git diff --check`, static searches for terminal-id caller fallbacks, deleted `provider_conversations.inbox_access` imports, legacy provider read helpers, internal `replyable` aliases, and `uv run pytest test/services/test_inbox_read.py test/mcp_server/test_inbox_tools.py`.

## 0007 — inbox source registry reply

### Review round 1 — 2026-05-21

- **Finding:** Terminal-addressed provider notifications could not be replied to through MCP because the new `inbox.reply` authorization only recognized agent-addressed receiver ids.
- **Accepted as valid because:** Existing provider notifications may be addressed to the caller's terminal while still belonging to the caller agent, and the registry dispatch must preserve the provider reply path through MCP.
- **Fix:** Updated `src/cli_agent_orchestrator/inbox/__init__.py` to accept terminal receiver ids whose terminal metadata belongs to the caller agent, and added MCP coverage for terminal-addressed provider replies.
- **Evidence:** `uv run pytest test/mcp_server/test_inbox_tools.py::test_reply_to_terminal_addressed_provider_notification_routes_through_inbox_reply -q` passed as part of the focused suite.

- **Finding:** Empty reply bodies raised a bare `ValueError`, causing MCP to classify the failure as an unexpected error rather than a normal inbox reply validation error.
- **Accepted as valid because:** The public `inbox.reply` surface owns body validation for all source kinds, and MCP should return a clear, expected error payload for invalid user input.
- **Fix:** Added `InboxReplyError` for reply validation failures and taught MCP `reply_to_inbox_message` to return it as a normal error payload.
- **Evidence:** `uv run pytest test/mcp_server/test_inbox_tools.py::test_reply_to_inbox_message_returns_normal_error_payload_for_empty_body -q` passed as part of the focused suite.

### Clean passes

- Pass 1: 2026-05-21, fresh review found no actionable issues after the terminal ownership and empty-body fixes; residual risk was limited to interactions outside the touched inbox/MCP/provider-conversation surfaces.
- Pass 2: 2026-05-21, independent review found no actionable issues; residual risk noted only the absence of a literal `source_kind="unknown"` test, with baton/runtime unregistered-source coverage exercising the generic `NotReplyable` path.

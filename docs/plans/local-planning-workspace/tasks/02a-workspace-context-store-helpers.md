# Task 02a: Workspace context store helpers

Part of: [../plan.md](../plan.md) — Workspace Context Store Surface.

## Goal

Add the public workspace-context store APIs required by local planning:
lookup by context id, boundary lookup, resolver-filtered listing,
agent-scoped context-workspace metadata patch/clear, pending-switch metadata
lookup, and database module re-exports.

## Dependencies

- Task 02 (`WORKSPACE_CONTEXT_STATUS_COMPLETED`) should land first or
  alongside this task.

## Files Touched

- `src/cli_agent_orchestrator/clients/workspace_context_store.py`
- `src/cli_agent_orchestrator/clients/database_migrations.py`
- `src/cli_agent_orchestrator/clients/database.py`
- `test/clients/test_workspace_context_store.py`

## What to do

1. Add `get_workspace_context(context_id) -> WorkspaceContextRecord | None`.
2. Add `get_workspace_context_for_boundary(resolver_id, provider_id,
   object_type, object_id) -> WorkspaceContextRecord | None` (or an
   equivalent public helper) so plan tools can resolve
   `object_id=<workdir_scope>:<slug>` without scanning every context.
3. Add `list_workspace_contexts(resolver_id=None,
   boundary_object_type=None, status=None) -> list[WorkspaceContextRecord]`.
4. Add `metadata_json` to `ContextWorkspaceModel` and include it on
   `ContextWorkspaceRecord`.
   - Update `clients/database_migrations.py` so existing databases add or
     rebuild the `context_workspaces.metadata_json` column during migration.
   - Backfill existing rows to the store's chosen empty metadata
     representation (`NULL` or `{}`) consistently.
5. Add `patch_context_workspace_metadata(agent_id, workspace_context_id,
   set_values=None, clear_keys=None) -> ContextWorkspaceRecord`.
   - Merge `set_values` into existing metadata for this agent/context row.
   - Remove keys listed in `clear_keys`.
   - Store `NULL` or `{}` consistently with the existing store style when
     no metadata remains.
   - Update `updated_at` on mutation.
6. Add `list_context_workspaces_pending_for_agent(agent_id)` (or a generic
   metadata lookup helper plus this wrapper) for context-workspace rows whose
   `metadata_json.pending_for_agent_id == agent_id`.
7. Ensure `mark_workspace_context_completed(context_id)` exists from
   Task 02 and returns/updates consistently with the new helpers.
8. Re-export the new helpers through `clients/database.py`, matching the
   existing workspace-context store re-export pattern.

## Definition of Done

1. By-id lookup returns the inserted context and returns `None` for missing
   context ids.
2. Boundary lookup returns the inserted scoped plan context by
   `(resolver_id, provider_id, object_type, object_id)` and returns `None`
   for a same-slug plan in a different workdir scope.
3. Resolver/object/status listing filters correctly and is deterministic
   enough for tests.
4. `ContextWorkspaceModel` has metadata persistence and existing rows remain
   readable after migration/backfill.
5. Agent-scoped metadata patch can add keys, update keys, clear one key,
   clear multiple keys, and preserve unrelated keys.
6. Pending lookup returns only context-workspace rows armed for the requested
   agent and does not return another agent's arm for the same workspace
   context.
7. Completed-status helper updates status and `updated_at`.
8. `clients/database.py` exports every new helper used by runtime,
   resolver, promote, and plan-tool tasks.
9. Tests cover all helpers in `test/clients/test_workspace_context_store.py`.
10. Migration coverage starts from an old `context_workspaces` schema without
   `metadata_json`, runs migrations, and proves metadata patch/list helpers
   work against the migrated rows.

## Review Gate

After implementing this task, run a review loop. The reviewer compares
the landed implementation against each item in Definition of Done above
plus all applicable entries in the `docs/criteria` catalog (run
`uv run python scripts/catalog_criteria.py` and load any criterion whose
`when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the
review loop restarts with a fresh reviewer. For every review finding that
requires an implementation change, the implementer updates
[../completion-report.md](../completion-report.md) under this task's
heading, recording what the reviewer found, why it was accepted as valid,
how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero
valid findings for this task, and those two clean review passes are
recorded in the completion report.

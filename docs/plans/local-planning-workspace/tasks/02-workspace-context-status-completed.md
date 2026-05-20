# Task 02: WORKSPACE_CONTEXT_STATUS_COMPLETED constant

Part of: [../plan.md](../plan.md) — Target Shape → `WORKSPACE_CONTEXT_STATUS_COMPLETED`.

## Goal

Today `clients/workspace_context_store.py:17` defines only
`WORKSPACE_CONTEXT_STATUS_ACTIVE`. The plan's `complete_plan` tool needs a
durable "completed" status. Add the constant and the small helper that
flips a row to it.

## Dependencies

None. Foundational.

## Files Touched

- `src/cli_agent_orchestrator/clients/workspace_context_store.py`.
- `src/cli_agent_orchestrator/clients/database.py` — re-export if the
  module-level re-export pattern is what the rest of the codebase uses
  (`database.py:170-220` already re-exports many context-store names).
- `test/clients/test_workspace_context_store.py` (or wherever the existing
  workspace context store tests live).

## What to do

1. Add `WORKSPACE_CONTEXT_STATUS_COMPLETED = "completed"` alongside
   `WORKSPACE_CONTEXT_STATUS_ACTIVE`.
2. Add `mark_workspace_context_completed(context_id: str) -> bool` that
   updates the `status` column and `updated_at` on `WorkspaceContextModel`.
   Return `True` on success, `False` if the row didn't exist. Raise on a
   conflicting (already-completed?) row or just be idempotent — pick the
   simpler "idempotent" semantic and document it.
3. Add the symbol to the `__all__` / re-export list in `database.py` if
   that's how the rest of the consumers reach context-store helpers.

## Out of scope

- `complete_plan` itself (Task 08).
- Any UI surface for completed contexts.

## Definition of Done

1. `WORKSPACE_CONTEXT_STATUS_COMPLETED == "completed"` defined in
   `workspace_context_store.py`.
2. `mark_workspace_context_completed(context_id)` flips the row's
   `status` column and updates `updated_at`.
3. Calling it on an already-completed row is idempotent (no error,
   returns `True`).
4. Calling it on a missing context id has clear, documented behavior
   (returns `False` or raises) consistent with the rest of the store's
   surface.
5. Symbol re-exported through `clients/database.py` if the existing
   re-export pattern is in use for similar names.
6. Round-trip test: create context, mark completed, read back, status
   `== "completed"`.
7. Idempotence test: mark twice, second call doesn't error.
8. Missing id test: behavior asserted matches the choice in item 4.

## Review Gate

After implementing this task, run a review loop. The reviewer compares
the landed implementation against each item in Definition of Done above
plus all applicable entries in the `docs/criteria` catalog (run
`uv run python scripts/catalog_criteria.py` and load any criterion whose
`when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the
review loop restarts with a fresh reviewer. For every review finding
that requires an implementation change, the implementer updates
[../completion-report.md](../completion-report.md) under this task's
heading, recording what the reviewer found, why it was accepted as
valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero
valid findings for this task, and those two clean review passes are
recorded in the completion report.

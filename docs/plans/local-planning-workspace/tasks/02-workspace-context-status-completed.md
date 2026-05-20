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

## Acceptance

- `WORKSPACE_CONTEXT_STATUS_COMPLETED == "completed"`.
- `mark_workspace_context_completed(id)` flips the row's status.
- Calling it on an already-completed row is idempotent (no error, returns
  `True`).
- Calling it on a missing context id returns `False` or raises — pick one
  and stay consistent with the rest of the store's surface.

## Tests

- Round trip: create context, mark completed, read back, status == completed.
- Idempotence: mark twice, second call doesn't error.
- Missing id: clear behavior asserted.

## Out of scope

- `complete_plan` itself (Task 08).
- Any UI surface for completed contexts.

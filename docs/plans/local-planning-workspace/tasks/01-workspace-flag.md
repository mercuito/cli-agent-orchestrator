# Task 01: Workspace require_active_workspace_context flag

Part of: [../plan.md](../plan.md) — Target Shape → `Workspace.require_active_workspace_context` Flag.

## Goal

Add a new boolean field on `Workspace` that signals whether the workspace
requires its agents to be on a non-sentinel context before performing
outbound collaboration actions. Default `False` so `linear_delivery` is
unchanged; `local_planning` will declare `True` once its workspace
registration lands.

## Dependencies

None. Foundational.

## Files Touched

- `src/cli_agent_orchestrator/workspaces/manager.py` — `Workspace`
  dataclass (`__post_init__` validation).
- `test/workspaces/` — new tests.

## What to do

1. Add `require_active_workspace_context: bool = False` to the `Workspace`
   dataclass.
2. In `__post_init__`, validate that the value is a bool. Raise
   `WorkspaceConfigError` otherwise. Use `_required_token`-style guard
   helpers consistent with the existing fields.
3. Leave the existing default `linear_delivery` registration alone (it
   will inherit the default `False`).

## Out of scope

- No call sites read this flag yet. Task 04 introduces the consumer
  (`apply_outbound_resolution`).

## Definition of Done

1. `Workspace(id="x", display_name="X", providers=("p",),
   resolver=lambda e: None)` constructs with
   `require_active_workspace_context == False`.
2. `Workspace(..., require_active_workspace_context=True)` constructs
   cleanly.
3. `Workspace(..., require_active_workspace_context="yes")` raises
   `WorkspaceConfigError`.
4. Existing `linear_delivery` workspace still loads and tests pass with no
   changes.
5. Parametrized constructor tests cover `True`, `False`, default, and one
   non-bool rejection case.
6. Round-trip test via `WorkspaceRegistry.register` + `.get` confirms the
   field is preserved.

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

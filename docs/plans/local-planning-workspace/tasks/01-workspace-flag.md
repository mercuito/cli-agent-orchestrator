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

## Acceptance

- `Workspace(id="x", display_name="X", providers=("p",),
  resolver=lambda e: None)` constructs with
  `require_active_workspace_context == False`.
- `Workspace(..., require_active_workspace_context=True)` constructs
  cleanly.
- `Workspace(..., require_active_workspace_context="yes")` raises
  `WorkspaceConfigError`.
- Existing `linear_delivery` workspace still loads and tests pass with no
  changes.

## Tests

- Parametrized constructor tests for `True`, `False`, default, and one
  non-bool rejection case.
- Round-trip via `WorkspaceRegistry.register` + `.get` confirms the field
  is preserved.

## Out of scope

- No call sites read this flag yet. Task 04 introduces the consumer
  (`apply_outbound_resolution`).

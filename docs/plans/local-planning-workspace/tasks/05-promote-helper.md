# Task 05: Promote-path helper

Part of: [../plan.md](../plan.md) — Target Shape → Promote Helper.

## Goal

Implement the data-driven promote step that copies provider runtime state
from a source context's data dir into a target context's data dir before
the standard terminal-start flow loads runtime state. Triggered by the
`promote_from_context_id` metadata field on the target
`WorkspaceContextModel.metadata_json`.

Runtime-side; workspace-agnostic. Does not import `local_planning`.

## Dependencies

- None (works against existing runtime state capability and workspace
  context store).

## Files Touched

- `src/cli_agent_orchestrator/services/terminal_service.py` — insert the
  promote hook in `_create_terminal_core` (around the existing
  `runtime_state_capability.load_runtime_state(...)` call at lines
  268-277).
- `src/cli_agent_orchestrator/clients/workspace_context_store.py` — helper
  to read + clear the `promote_from_context_id` metadata field if not
  already trivially supported by existing accessors.
- New file: `src/cli_agent_orchestrator/runtime/promote.py` (or a function
  in `runtime/agent.py`; pick one and stay consistent with the rest of
  runtime layout). Holds `apply_promote_if_armed(agent, target_context_id)
  -> bool`.
- `test/runtime/test_promote.py` (new).

## What to do

1. Add `apply_promote_if_armed(agent, target_context_id) -> bool`:
   - Read the target workspace context's `metadata_json`.
   - If `promote_from_context_id` is absent: return `False`.
   - Resolve source dir via `workspace_context_provider_data_dir(agent,
     source_ctx_id, agent.cli_provider)` (see `agent.py:330-346`).
   - Resolve target dir similarly.
   - If `runtime_state_capability(agent.cli_provider)` is `None`: clear
     the metadata field and return `False` (cold restart is expected for
     these providers).
   - If target dir already has provider state files: clear the metadata
     field and return `False` (don't overwrite a populated dir).
   - If source dir has no state: clear the metadata field and return
     `False`.
   - Otherwise: copy source dir contents to target dir, clear the
     `promote_from_context_id` field on the workspace context, return
     `True`.

2. In `terminal_service._create_terminal_core`, call
   `apply_promote_if_armed(agent_launch.agent,
   agent_launch.workspace_context_id)` immediately before the existing
   `runtime_state_capability.load_runtime_state(...)` block (around line
   268). The existing load picks up the copied state.

3. The helper must be idempotent — re-running after a successful copy is
   a no-op because the metadata field is cleared.

## Out of scope

- The arming itself — Tasks 08 (`create_plan` / `activate_plan` set the
  metadata field).
- The deferred-switch trigger — Task 06.

## Definition of Done

1. `apply_promote_if_armed(agent, target_context_id) -> bool` helper
   exists and is invoked from
   `terminal_service._create_terminal_core` immediately before the
   existing runtime-state load at lines 268-277.
2. Claude Code / Codex agents with armed metadata: copy happens, target
   dir contains source's state files, metadata cleared after copy.
3. Kiro / Q / Copilot / Gemini / Kimi agents with armed metadata: no
   copy (no capability), metadata cleared, function returns `False`
   without raising.
4. Armed metadata but target dir already populated: no overwrite,
   metadata cleared, returns `False`.
5. Armed metadata but source dir empty: no copy, metadata cleared,
   returns `False`.
6. No armed metadata: returns `False` quickly with no I/O.
7. Second invocation after a successful copy: returns `False` (one-shot
   semantics — no double-promote).
8. Parametrized tests cover all six branches above using temp dirs and
   existing `workspace_context_store` fixtures.
9. Test asserts `terminal_service._create_terminal_core` invokes the
   helper before the existing runtime-state load (via mock or behavior
   assertion).

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

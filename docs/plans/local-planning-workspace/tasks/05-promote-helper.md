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

## Acceptance

- For Claude Code/Codex agents with armed metadata: copy happens, target
  dir contains source's state files, metadata cleared.
- For Kiro/Q/Copilot/Gemini/Kimi agents with armed metadata: no copy
  (no capability), metadata cleared, function returns False without
  error.
- Armed metadata but target dir already populated: no overwrite, metadata
  cleared, returns False.
- Armed metadata but source dir empty: no copy, metadata cleared, returns
  False.
- No armed metadata: returns False quickly, no I/O.
- Second invocation after success: returns False (no double-promote).

## Tests

- Parametrized over the cases above using temp dirs + the existing
  `workspace_context_store` fixtures.
- Test that `terminal_service._create_terminal_core` calls the helper
  before runtime state load (via mock or behavior assertion).

## Out of scope

- The arming itself — Tasks 08 (`create_plan` / `activate_plan` set the
  metadata field).
- The deferred-switch trigger — Task 06.

# Task 06: Deferred-switch firing via watchdog two-phase emission

Part of: [../plan.md](../plan.md) — Implementation Tasks → "Event-driven
deferred-switch firing".

## Goal

When `create_plan` / `activate_plan` arm a workspace context with
`pending_for_agent_id`, this task wires the trigger that fires the
deferred switch when the agent next becomes idle.

Three sub-pieces:

1. The workspace-neutral helper
   `apply_pending_workspace_context_switches(agent_id, new_status)` that
   queries armed contexts and drives the switch via the runtime handle.
2. Two-phase emission inside `LogFileHandler._handle_log_change`:
   detect status transition, run the helper inline (applying any armed
   switches), then publish `AgentTerminalStatusChangeEvent` with settled
   state.
3. Per-terminal previous-status cache in the watchdog (in-memory is
   sufficient; the event is best-effort).

## Dependencies

- Task 03 (`AgentTerminalStatusChangeEvent` registered).
- Task 04 (`apply_outbound_resolution` exists, though this task uses
  `resolve_event_context` directly for the simpler "is anything armed"
  check, no flag enforcement at this layer).
- Task 05 (promote helper exists; the deferred switch path triggers
  terminal start which calls promote inline).

## Files Touched

- `src/cli_agent_orchestrator/runtime/agent.py` — add
  `apply_pending_workspace_context_switches`. Could also live in a
  sibling file; pick what fits the existing layout.
- `src/cli_agent_orchestrator/clients/workspace_context_store.py` — query
  helper for contexts where `metadata_json.pending_for_agent_id ==
  agent_id`. Add `list_workspace_contexts_pending_for_agent(agent_id)`.
- `src/cli_agent_orchestrator/services/inbox_service.py` —
  `LogFileHandler._handle_log_change` two-phase implementation.
- `test/runtime/test_apply_pending_switches.py` (new).
- `test/services/test_inbox_service.py` — extend with two-phase emission
  tests.

## What to do

1. Add `list_workspace_contexts_pending_for_agent(agent_id) ->
   list[WorkspaceContextRecord]` to the workspace context store. JSON
   path query into `metadata_json` is acceptable in SQLite (`json_extract`
   on the column).
2. Add `apply_pending_workspace_context_switches(agent_id, new_status)`:
   - If `new_status` is not in `{IDLE, COMPLETED}`: return immediately
     (no work to do until agent is ready).
   - Otherwise list armed contexts for the agent.
   - For each context, construct `AgentRuntimeHandle(agent,
     workspace_context_id=ctx.id)` and call `ensure_fresh_started()`.
   - On success, clear `pending_for_agent_id` (and any related
     `promote_from_context_id` if not already cleared by promote helper)
     from the context metadata.
   - Stop after the first successful switch (terminal manifestation
     invariant — one terminal per agent).
3. Extend `LogFileHandler._handle_log_change` per the plan's pseudo-code
   in "Event-driven deferred-switch firing":
   - Add a per-handler dict `_previous_status: dict[terminal_id, status]`.
   - After the existing fast-path skip, call `provider.get_status()`.
   - Compare against `_previous_status[terminal_id]` (default: unknown).
   - If transition detected: look up agent_id from terminal metadata,
     call `apply_pending_workspace_context_switches(agent_id, new_status)`,
     then publish `AgentTerminalStatusChangeEvent(...)`.
   - Update `_previous_status[terminal_id]` to the new status.
   - Then proceed with existing
     `check_and_send_pending_messages(terminal_id)`.

## Out of scope

- The arming itself (Task 08).
- Subscribers of `AgentTerminalStatusChangeEvent` (not in scope for v1;
  this task just publishes it).

## Definition of Done

1. `list_workspace_contexts_pending_for_agent(agent_id)` exists in
   `workspace_context_store.py` and returns contexts where
   `metadata_json.pending_for_agent_id == agent_id`.
2. `apply_pending_workspace_context_switches(agent_id, new_status)`
   exists, returns early when `new_status` is not in `{IDLE, COMPLETED}`,
   and otherwise drives `ensure_fresh_started` on each armed context for
   the agent.
3. On successful switch, `pending_for_agent_id` is cleared from the
   workspace context metadata. (`promote_from_context_id` clearing is
   handled by the promote helper in Task 05.)
4. `LogFileHandler._handle_log_change` is extended to: detect status
   transition via a per-terminal `_previous_status` cache, call
   `apply_pending_workspace_context_switches` inline before publishing,
   then publish `AgentTerminalStatusChangeEvent` with settled state.
5. The existing `check_and_send_pending_messages(terminal_id)` call
   continues to run after the new logic (against the current
   terminal_id, which may have changed if a switch landed).
6. Agent with `pending_for_agent_id` set on context P: when the agent's
   terminal transitions to IDLE, the helper finds P, terminal restarts
   in P (with promote from Task 05 applied if armed), metadata cleared.
7. Agent without armed contexts: helper returns immediately with no
   switch attempted.
8. Agent with two armed contexts (unexpected): only one switch lands per
   idle cycle; second armed context remains armed until next idle.
9. `AgentTerminalStatusChangeEvent` published only on actual
   transitions, not on every log change.
10. Subscribers see post-switch state (`terminal_id` field reflects the
    *current* terminal after any switch).
11. Mocked watchdog test: arm a context, simulate IDLE transition,
    assert `ensure_fresh_started` is called and metadata cleared.
12. Multiple armings test: assert one-switch-per-cycle behavior.
13. Status not IDLE test: helper exits without DB query.
14. `previous_status == new_status` test: no event published, no switch
    attempt.
15. Linear coexistence test: with Linear's monitor also running, no
    duplicate switches and no errors from
    `_deactivate_other_context_terminal_for_switch` serialization.

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

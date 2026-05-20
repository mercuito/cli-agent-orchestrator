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

## Acceptance

- Agent on context A with `pending_for_agent_id` set on context P: when
  the agent's terminal transitions to IDLE, the helper finds P, fires
  `ensure_fresh_started`, terminal restarts in P (with promote applied if
  armed), metadata cleared.
- Same agent without armed contexts: helper queries DB once, returns
  immediately, no switch attempted.
- Agent with two armed contexts (unexpected): only one switch lands per
  idle cycle. Second armed context remains until next idle.
- `AgentTerminalStatusChangeEvent` published only on actual transitions
  (not on every log change).
- Subscribers of the status change event see post-switch state
  (terminal_id field reflects the *current* terminal after any switch).

## Tests

- Mocked watchdog flow: arm a context, simulate IDLE transition, assert
  `ensure_fresh_started` is called and metadata cleared.
- Multiple armings: assert one-switch-per-cycle behavior.
- Status not IDLE: helper exits without DB query (assert no calls).
- `previous_status == new_status`: no event published, no switch attempt.
- Linear coexistence: with Linear's monitor also running, no duplicate
  switches (the runtime handle's existing `_deactivate_other_context_terminal_for_switch`
  serialization handles this; assert no errors).

## Out of scope

- The arming itself (Task 08).
- Subscribers of `AgentTerminalStatusChangeEvent` (not in scope for v1;
  this task just publishes it).

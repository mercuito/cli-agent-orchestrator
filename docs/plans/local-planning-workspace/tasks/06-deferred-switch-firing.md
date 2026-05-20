# Task 06: Deferred-switch firing via watchdog two-phase emission

Part of: [../plan.md](../plan.md) — Implementation Tasks → "Event-driven
deferred-switch firing".

## Goal

When `create_plan` / `activate_plan` arm a workspace context with
agent-scoped `pending_for_agent_id` metadata, or when cross-plan
send_message / baton delivery creates pending `agent:<id>:context:<ctx>`
notifications for a BUSY receiver, this task wires the trigger that fires
the deferred switch when the agent next becomes idle.

Three sub-pieces:

1. The workspace-neutral helper
   `apply_pending_workspace_context_switches(agent_id, new_status)` that
   queries armed contexts plus pending context-keyed inbox receiver ids and
   drives the switch via the runtime handle.
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
- Task 02a (pending context-workspace metadata lookup exists).

## Files Touched

- `src/cli_agent_orchestrator/runtime/agent.py` — add
  `apply_pending_workspace_context_switches`. Could also live in a
  sibling file; pick what fits the existing layout.
- `src/cli_agent_orchestrator/clients/inbox_store.py` — use existing
  `list_pending_agent_inbox_receiver_ids(agent_id)` from the helper.
- `src/cli_agent_orchestrator/services/inbox_service.py` —
  `LogFileHandler._handle_log_change` two-phase implementation.
- `test/runtime/test_apply_pending_switches.py` (new).
- `test/services/test_inbox_service.py` — extend with two-phase emission
  tests.

## What to do

1. Use the Task 02a
   `list_context_workspaces_pending_for_agent(agent_id)` helper and the
   existing inbox-store `list_pending_agent_inbox_receiver_ids(agent_id)`
   helper.
2. Add `apply_pending_workspace_context_switches(agent_id, new_status)`:
   - If `new_status` is not in `{IDLE, COMPLETED}`: return immediately
     (no work to do until agent is ready).
   - Otherwise list armed contexts for the agent and pending
     context-keyed receiver ids shaped `agent:<id>:context:<ctx>`.
   - Parse context ids from the receiver ids, union them with armed
     context-workspace ids, and process each context once.
   - For each context id, construct `AgentRuntimeHandle(agent,
     workspace_context_id=context_id)` and call
     `try_deliver_pending(causing_event=...)`.
   - That path first ensures freshness, then moves pending
     `agent:<id>:context:<ctx>` notifications to the live terminal and
     delivers them when the terminal is ready.
   - On ready/delivered success, clear `pending_for_agent_id` (and any
     related `promote_from_context_id` if not already cleared by promote
     helper) from that agent/context metadata when such metadata exists.
     Contexts discovered only through pending inbox receiver ids may have no
     arming metadata to clear.
   - Stop after the first successful switch (terminal manifestation
     invariant — one terminal per agent).
3. Extend `LogFileHandler._handle_log_change` per the plan's pseudo-code
   in "Event-driven deferred-switch firing":
   - Add a per-handler dict `_previous_status: dict[terminal_id, status]`.
   - Replace the existing fast-path skip with a combined check:
     continue when the current terminal has pending inbox work OR the agent
     has armed workspace-context switches OR the agent has pending
     context-keyed inbox receiver ids. Only return early when all three are
     absent.
   - Resolve the provider with `provider_manager.get_provider(terminal_id)`
     and call `provider.get_status()` with no terminal-id argument.
   - Compare against `_previous_status[terminal_id]` (default: unknown).
   - If transition detected: look up agent_id from terminal metadata,
     call `apply_pending_workspace_context_switches(agent_id, new_status)`,
     then publish `AgentTerminalStatusChangeEvent(...)`.
   - Update `_previous_status[terminal_id]` to the new status.
   - Then attempt existing `check_and_send_pending_messages(...)` against
     the settled current terminal id only when that terminal has pending
     terminal-id inbox work.

## Out of scope

- The arming itself (Task 08).
- Subscribers of `AgentTerminalStatusChangeEvent` (not in scope for v1;
  this task just publishes it).

## Definition of Done

1. The Task 02a `list_context_workspaces_pending_for_agent(agent_id)`
   helper is used to find agent/context rows where
   `metadata_json.pending_for_agent_id == agent_id`, and
   `list_pending_agent_inbox_receiver_ids(agent_id)` is used to find
   context-keyed pending inbox notifications.
2. `apply_pending_workspace_context_switches(agent_id, new_status)`
   exists, returns early when `new_status` is not in `{IDLE, COMPLETED}`,
   and otherwise drives `try_deliver_pending` on each armed or
   context-inbox-discovered context for the agent.
3. On successful switch, `pending_for_agent_id` is cleared from that
   agent/context metadata. (`promote_from_context_id` clearing is handled by
   the promote helper in Task 05.)
4. `LogFileHandler._handle_log_change` is extended to: detect status
   transition via a per-terminal `_previous_status` cache, check for armed
   switches and context-keyed pending inbox work before returning on no
   terminal-id inbox work, call
   `apply_pending_workspace_context_switches` inline before publishing,
   then publish `AgentTerminalStatusChangeEvent` with settled state.
5. The existing `check_and_send_pending_messages(terminal_id)` call
   continues to run after the new logic (against the current
   terminal_id, which may have changed if a switch landed).
6. Agent with `pending_for_agent_id` set on its context-workspace row for
   context P: when the agent's terminal transitions to IDLE, the helper
   finds P, terminal restarts
   in P (with promote from Task 05 applied if armed), metadata cleared.
6a. Two agents sharing context P: firing agent A's pending switch does not
    consume or clear agent B's pending metadata.
7. Agent without armed contexts or context-keyed pending inbox work: helper
   returns immediately with no switch attempted and no
   `AgentTerminalStatusChangeEvent` published from this local-planning
   pending-work path.
8. Agent with two discovered contexts (unexpected, from metadata and/or
   context-keyed inbox ids): only one switch lands per idle cycle; remaining
   work stays pending until next idle.
9. `AgentTerminalStatusChangeEvent` published only on actual
   transitions, not on every log change.
10. Subscribers see post-switch state (`terminal_id` field reflects the
    *current* terminal after any switch).
11. Mocked watchdog test: arm a context, simulate IDLE transition with no
    pending terminal-id inbox work, assert `try_deliver_pending` is called
    and metadata cleared.
12. Context-keyed inbox test: create a pending
    `agent:<id>:context:<ctx>` notification without `pending_for_agent_id`,
    simulate IDLE transition with no terminal-id inbox work, assert
    `try_deliver_pending` is called for `<ctx>` and the notification is
    moved/delivered when ready.
13. Multiple armings / context inbox ids test: assert one-switch-per-cycle
    behavior and no duplicate processing when a context is discovered by
    both metadata and inbox receiver id.
14. Status not IDLE test: helper exits without DB query.
15. `previous_status == new_status` test: no event published, no switch
    attempt.
16. Linear coexistence test: with Linear's monitor also running, no
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

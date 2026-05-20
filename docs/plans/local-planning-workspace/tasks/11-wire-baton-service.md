# Task 11: Wire baton_service with sent/received events per transition

Part of: [../plan.md](../plan.md) — Event Emission and Resolver
Consultation in API Endpoints → site #3.

## Goal

Each of the five baton transition functions emits its sent event before
applying the transition, runs it through the resolver, applies the
resolved context to the receiver-side runtime handle, lands the
transition, then emits the matching received event.

## Dependencies

- Task 03 (all 10 baton events exist).
- Task 04 (`apply_outbound_resolution`).

## Files Touched

- `src/cli_agent_orchestrator/services/baton_service.py` — extend
  `create_baton`, `pass_baton`, `return_baton`, `complete_baton`,
  `block_baton`.
- `test/services/test_baton_service.py` (or wherever baton tests live).

## What to do

For each transition function, before applying the transition:

1. Identify the receiver agent_id (varies per transition):
   - `create_baton` → first holder.
   - `pass_baton` → next holder.
   - `return_baton` → previous holder (top of return stack, or originator
     if empty).
   - `complete_baton` → originator.
   - `block_baton` → originator.
2. Resolve sender (`actor_id` → terminal metadata → agent_id +
   workspace_context_id) and receiver agent.
3. Build the appropriate sent event:
   - `BatonCreatedEvent(sender_*=originator, holder_agent_id=...,
     baton_id, title, message)`.
   - `BatonPassedEvent(sender_*=current holder, from_holder_agent_id,
     to_holder_agent_id, baton_id, message)`.
   - `BatonReturnedEvent(sender_*=current holder, from_holder_agent_id,
     to_holder_agent_id (previous holder), baton_id, message)`.
   - `BatonCompletedEvent(sender_*=current holder,
     originator_agent_id, baton_id, message)`.
   - `BatonBlockedEvent(sender_*=current holder,
     originator_agent_id, baton_id, reason)`.
4. Publish the sent event.
5. Call `manager.apply_outbound_resolution(receiver_agent, event)`. If
   the workspace flag enforces and resolution is None, raise the same
   `WorkspaceConfigError` the manager raises; surface as an error to the
   MCP caller (same error surface as the existing
   `_require_workspace_team_terminal_collaboration` check).
6. Use the resolution to construct a runtime handle for the receiver
   (`AgentRuntimeHandle(receiver_agent,
   workspace_context_id=resolution.workspace_context_id)`) and call
   `handle.notify(message)` so the baton transition message lands in the
   correct context-keyed inbox (same pattern as send_message in Task 09).
7. Apply the transition in the database (existing logic).
8. Publish the matching received event with the same correlation_id as
   the sent event.

## Out of scope

- Refactoring the existing team-membership check.
- Baton timeline UI changes; observability via the new events is plumbing
  only.

## Definition of Done

1. Each of the five baton transition functions in `baton_service.py`
   builds its sent event (`BatonCreatedEvent`, `BatonPassedEvent`,
   `BatonReturnedEvent`, `BatonCompletedEvent`, `BatonBlockedEvent`)
   from sender + receiver info before applying the transition.
2. Each transition publishes its sent event and runs it through
   `manager.apply_outbound_resolution(receiver_agent, event)`.
3. Each transition applies the resolution to a receiver runtime handle
   and calls `handle.notify(message)` so the transition message lands
   in the correct context-keyed inbox (same machinery as send_message).
4. After the transition lands in the DB, each function publishes the
   matching received event
   (`BatonCreationReceivedEvent`, `BatonPassReceivedEvent`,
   `BatonReturnReceivedEvent`, `BatonCompletionReceivedEvent`,
   `BatonBlockReceivedEvent`) with `correlation_id` referencing the
   sent event's `event_id`.
5. Existing team-membership check
   (`_require_workspace_team_terminal_collaboration`) continues to
   apply alongside the new flag check (manager.apply_outbound_resolution
   does the flag check; team check stays in place).
6. Sentinel originator on a `local_planning` team: blocked at the sent
   event layer — sent event still published, then `WorkspaceConfigError`
   surfaces to the MCP caller as an error result.
7. Linear coexistence: baton transitions still work for Linear teams
   (workspace flag defaults to `False`).
8. Per-transition tests assert sent + received events fire with
   matching `correlation_id`.
9. Each transition tested under both same-team-same-plan and
   same-team-cross-plan conditions; assert context switch where
   expected.
10. Sentinel originator on a `local_planning` team test: rejected, sent
    event still published.

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

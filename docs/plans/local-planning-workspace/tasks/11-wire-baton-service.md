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

## Acceptance

- All five transitions emit the right sent + received event pair.
- Cross-context baton transitions context-switch the receiver via
  `handle.notify` (same machinery as send_message).
- Existing team-membership checks
  (`_require_workspace_team_terminal_collaboration`) continue to apply
  alongside the new flag check (the new check runs through the manager;
  team check stays).
- Sentinel originator on `local_planning` team: blocked at the sent event
  layer (sent event published, then `WorkspaceConfigError`).
- Linear coexistence: baton transitions still work for Linear teams (flag
  defaults to False).

## Tests

- Each of the five transitions: assert sent + received events fire with
  matching correlation_id.
- Each transition under both same-team-same-plan and same-team-cross-plan
  conditions; assert context switch where expected.
- Sentinel originator on a `local_planning` team is rejected; sent event
  still published.

## Out of scope

- Refactoring the existing team-membership check.
- Baton timeline UI changes; observability via the new events is plumbing
  only.

# Task 11: Wire baton_service with sent/received events per transition

Part of: [../plan.md](../plan.md) — Event Emission and Resolver
Consultation in API Endpoints → site #3.

## Goal

Each of the five baton transition functions emits its sent event before
applying the transition, runs it through the resolver, applies the
resolved context to the receiver-side runtime handle, persists the
transition, then queues/delivers the receiver notification and emits the
matching received event.

## Dependencies

- Task 03 (all 10 baton events exist).
- Task 04 (`apply_outbound_resolution`).
- Task 10b (durable baton agent ownership exists).

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
   workspace_context_id) and receiver agent. Baton ownership checks and
   writes use agent ids; terminal ids are runtime/delivery/event metadata.
3. Build the appropriate sent event:
   - `BatonCreatedEvent(sender_*=originator, holder_agent_id=...,
     holder_terminal_id=None unless a current delivery terminal is already
     known, baton_id, title, message)`.
   - `BatonPassedEvent(sender_*=current holder, from_holder_agent_id,
     from_holder_terminal_id=actor_terminal_id, to_holder_agent_id,
     to_holder_terminal_id=None unless already known, baton_id, message)`.
   - `BatonReturnedEvent(sender_*=current holder, from_holder_agent_id,
     from_holder_terminal_id=actor_terminal_id, to_holder_agent_id
     (previous holder), to_holder_terminal_id=None unless already known,
     baton_id, message)`.
   - `BatonCompletedEvent(sender_*=current holder,
     originator_agent_id, originator_terminal_id=None unless already known,
     baton_id, message)`.
   - `BatonBlockedEvent(sender_*=current holder,
     originator_agent_id, originator_terminal_id=None unless already known,
     baton_id, reason)`.
   Receiver terminal fields on sent events are optional and are not used by
   the resolver; the authoritative receiver is the agent id.
4. Publish the sent event.
5. Call `manager.apply_outbound_resolution(receiver_agent, event)`. If
   the workspace flag enforces and resolution is None, raise the same
   `WorkspaceConfigError` the manager raises; surface as an error to the
   MCP caller (same error surface as the existing
   `_require_workspace_team_terminal_collaboration` check).
6. Use the resolution to construct a runtime handle for the receiver
   (`AgentRuntimeHandle(receiver_agent,
   workspace_context_id=resolution.workspace_context_id)`), but do not
   immediately deliver before the baton row is persisted.
7. Apply and commit the transition in the database (existing logic).
8. After commit, format the notification with the existing
   `_baton_message(...)` helper so action/title/body/expected next action,
   guidance, and artifact paths are preserved. Call
   `handle.notify(formatted_message, sender_id=actor_terminal_id,
   source_kind="baton_transition", source_id=<stable transition source id>,
   causing_event=sent_event, notification_metadata={...})` so the baton
   transition message lands in the correct context-keyed inbox while
   preserving actor identity. If the implementation needs to create the
   notification before commit, it must use
   `handle.notify(..., attempt_delivery=False)` and trigger delivery only
   after the DB transition commits.
9. If `handle.notify(...)` starts/reuses a different receiver terminal, treat
   the returned terminal id as delivery metadata only. The baton row's durable
   `current_holder_agent_id`/`originator_agent_id`/return-stack agent ids
   remain authoritative, so no terminal-reference remap is needed.
10. Publish the matching received event with the same correlation_id as
   the sent event only when `notify_result.delivery.delivered` is true and
   `notify_result.terminal_id` is present. Populate receiver terminal fields
   from that actual delivery terminal. If notify only durably queues the
   notification, do not publish a received event in this transition path.

## Out of scope

- Baton timeline UI changes; observability via the new events is plumbing
  only.

## Required refactor

The existing `_queue_baton_message` helper couples same-team validation,
message formatting, and pre-commit inbox creation. Split that path as part
of this task:

- Run the existing `require_terminal_same_team_collaboration` /
  `_require_workspace_team_terminal_collaboration` validation before
  outbound context routing.
- Reuse or extract the existing `_baton_message(...)` formatting so current
  guidance/body/artifact content stays identical.
- Do not write the inbox notification through the old pre-commit
  `_queue_baton_message` path. After the baton DB transition commits, call
  `handle.notify(...)` on the receiver runtime handle.

## Definition of Done

1. Each of the five baton transition functions in `baton_service.py`
   builds its sent event (`BatonCreatedEvent`, `BatonPassedEvent`,
   `BatonReturnedEvent`, `BatonCompletedEvent`, `BatonBlockedEvent`)
   from sender + receiver agent info before applying the transition. Sent
   events do not require receiver terminal ids before routing/notify.
2. Each transition publishes its sent event and runs it through
   `manager.apply_outbound_resolution(receiver_agent, event)`.
3. Each transition applies the resolution to a receiver runtime handle
   and queues/delivers the notification only after the baton DB transition
   is committed, so recipients cannot observe stale baton state.
4. Each transition calls `handle.notify(...)` after commit (or uses
   `attempt_delivery=False` before commit and triggers delivery after
   commit) with the existing `_baton_message(...)` output,
   `sender_id=actor_terminal_id`, and source/correlation metadata, so the
   transition message lands in the correct context-keyed inbox without
   losing current baton guidance or actor identity.
5. If notify starts/reuses a different receiver terminal, each transition
   preserves durable agent ownership. The new holder/originator can perform
   the next baton action from any terminal owned by that agent, and watchdog
   scans do not orphan the baton because an old terminal id disappeared.
6. After the transition lands in the DB and notification delivery succeeds,
   each function publishes the matching received event
   (`BatonCreationReceivedEvent`, `BatonPassReceivedEvent`,
   `BatonReturnReceivedEvent`, `BatonCompletionReceivedEvent`,
   `BatonBlockReceivedEvent`) with `correlation_id` referencing the
   sent event's `event_id` and with receiver terminal fields populated from
   the terminal that actually received delivery when available.
   If delivery is only queued, no received event is published by the
   transition call.
7. Existing team-membership check
   (`_require_workspace_team_terminal_collaboration`) continues to
   apply alongside the new flag check (manager.apply_outbound_resolution
   does the flag check; team check is split from the old pre-commit inbox
   write helper and runs before routing).
8. Sentinel originator on a `local_planning` team: blocked at the sent
   event layer — sent event still published, then `WorkspaceConfigError`
   surfaces to the MCP caller as an error result.
9. Linear coexistence: baton transitions still work for Linear teams
   (workspace flag defaults to `False`).
10. Per-transition tests assert sent events fire before routing and that,
    when notification delivery succeeds, received events fire with matching
    `correlation_id` and the actual delivery terminal id.
11. Each transition tested under both same-team-same-plan and
   same-team-cross-plan conditions; assert context switch where
   expected.
12. Sentinel originator on a `local_planning` team test: rejected, sent
    event still published.
13. Test proves an idle receiver is not notified before the baton row is
    committed to the new holder/status.
14. Tests assert queued baton inbox notifications preserve the existing
    formatted guidance/body/artifact content and sender terminal id.

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

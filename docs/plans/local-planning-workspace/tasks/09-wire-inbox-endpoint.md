# Task 09: Wire inbox endpoint with sent/received events and runtime-handle delivery

Part of: [../plan.md](../plan.md) — Event Emission and Resolver
Consultation in API Endpoints → site #1.

## Goal

Replace the existing terminal-id-keyed direct-write delivery path in the
inbox endpoint with the runtime-handle-driven path Linear already uses.
Emit `AgentMessageSentEvent` before delivery routing and
`AgentMessageReceivedEvent` after the receiver's terminal accepts the
message.

## Dependencies

- Task 03 (`AgentMessageSentEvent`, `AgentMessageReceivedEvent` exist).
- Task 04 (`apply_outbound_resolution` exists).

## Files Touched

- `src/cli_agent_orchestrator/api/main.py:2070` —
  `create_inbox_message_endpoint`.
- `src/cli_agent_orchestrator/services/inbox_service.py` — extend
  `check_and_send_pending_messages` to emit
  `AgentMessageReceivedEvent` on successful delivery.
- `test/api/` and `test/services/test_inbox_service.py` — extend.

## What to do

In `create_inbox_message_endpoint`:

1. Look up sender's terminal metadata from `sender_id` query param. If
   missing, reject with 400 + actionable error ("sender_id does not map
   to a known terminal").
2. Look up receiver's terminal metadata from path param. Resolve to a
   receiver `Agent` via `AgentManager.resolve_agent(receiver_metadata["agent_id"])`.
3. Build `AgentMessageSentEvent(...)`. Publish via
   `default_cao_event_dispatcher().publish(...)`.
4. Call `manager.apply_outbound_resolution(receiver_agent, event)` →
   resolution. If the workspace flag enforces and resolution is None,
   the manager raises; surface that as 400.
5. Construct `AgentRuntimeHandle(receiver_agent,
   workspace_context_id=resolution.workspace_context_id if resolution
   else receiver_metadata["workspace_context_id"])` (fall back to
   receiver's existing context when the workspace doesn't enforce and
   resolver returned None).
6. Call `handle.notify(message, sender_id=sender_id,
   source_kind="cao_inbox", source_id=...)`. This both creates the
   `agent:<id>:context:<resolved>` inbox notification AND triggers any
   needed context switch.
7. Return the notify result envelope (preserve existing response shape
   for backward compatibility with the MCP `send_message` caller).

In `inbox_service.check_and_send_pending_messages`:

8. On the existing successful delivery path (after `terminal_service.send_input`
   succeeds and notification status flips to DELIVERED), emit
   `AgentMessageReceivedEvent(receiver_agent_id, receiver_terminal_id,
   inbox_message_id)`. Use the correlation_id of the original sent event
   if available via the notification metadata; otherwise generate a fresh
   one. The pair-up convention is `correlation_id`-based.

## Out of scope

- The `mcp_server/server.py` MCP-side `_send_to_inbox` doesn't need
  changes for this task — the API receives sender_id from the query
  param the MCP already passes. The API does the lookup. (Task 10
  propagates the `trigger_action` discriminator for the *start* endpoint,
  not for inbox.)

## Definition of Done

1. send_message from sender on plan A to a receiver on plan A:
   delivery works, no context switch fires, `AgentMessageSentEvent` and
   `AgentMessageReceivedEvent` both published with matching
   `correlation_id`.
2. send_message from sender on plan A to a receiver on plan B:
   receiver context-switches to plan A via `handle.notify`. Inbox
   notification lives under `agent:<id>:context:plan_A`. After the switch
   lands and the message delivers, `AgentMessageReceivedEvent` fires
   from `inbox_service`.
3. send_message from sender on the sentinel context on a
   `local_planning` team: rejected via the manager flag check from Task
   04. Sent event still published before rejection (so the timeline
   shows the attempt).
4. send_message from sender on the sentinel context on a
   `linear_delivery` team: delivers as before (flag is `False`).
5. send_message with missing/invalid `sender_id` query param: 400 with
   actionable error text.
6. Receiver is BUSY at send time: notification queued in
   `agent:<id>:context:<resolved>` inbox; switch DEFERRED; Task 06
   watchdog mechanism eventually fires the switch and delivers.
7. Same-plan path test: assert no switch, both events fire.
8. Cross-plan path test: assert switch fires, receiver terminal
   metadata reflects new terminal, both events fire with matching
   `correlation_id`.
9. Sentinel sender + flag enforced test: 400 with sent event present.
10. Sentinel sender + flag not enforced test: delivery succeeds.
11. Bad `sender_id` test: 400.
12. BUSY receiver test: assert notification persists in new-context
    inbox; simulate idle transition (Task 06 path); assert delivery
    completes and received event fires.

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

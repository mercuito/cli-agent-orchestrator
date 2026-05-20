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

## Acceptance

- send_message from sender on plan A to a receiver on plan A: delivery
  works, no context switch fires, sent + received events both published
  with matching correlation_id.
- send_message from sender on plan A to a receiver on plan B: receiver
  context-switches to plan A (handle.notify drives it). Notification
  lives under `agent:<id>:context:A`. After switch lands and message
  delivers, `AgentMessageReceivedEvent` fires from inbox_service.
- send_message from sender on sentinel on a `local_planning` team: rejected
  via the manager flag. Sent event still published before rejection (so
  the timeline shows the attempt).
- send_message from sender on sentinel on a `linear_delivery` team:
  delivers as before (flag is False).
- send_message with missing/invalid `sender_id`: 400 with clear message.
- Receiver is BUSY: notification queued in
  `agent:<id>:context:<resolved>` inbox; switch DEFERRED; watchdog
  eventually drives the switch + delivery (Task 06 mechanism).

## Tests

- Same-plan path: assert no switch, both events fire.
- Cross-plan path: assert switch fires, receiver_id metadata reflects
  new terminal, both events fire with matching correlation_id.
- Sentinel sender + flag enforced: 400, sent event present.
- Sentinel sender + flag not enforced: delivery succeeds.
- Bad sender_id: 400.
- BUSY receiver: assert notification persists in new-context inbox;
  simulate idle transition (Task 06 path); assert delivery completes and
  received event fires.

## Out of scope

- The `mcp_server/server.py` MCP-side `_send_to_inbox` doesn't need
  changes for this task — the API receives sender_id from the query
  param the MCP already passes. The API does the lookup. (Task 13
  propagates the `trigger_action` discriminator for the *start* endpoint,
  not for inbox.)

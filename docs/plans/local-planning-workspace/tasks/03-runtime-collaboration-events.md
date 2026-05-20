# Task 03: Runtime agent collaboration + terminal status events

Part of: [../plan.md](../plan.md) — Target Shape → Event Types →
Agent collaboration events (runtime-owned) and Terminal state change event.

## Goal

Define 17 new CAO event types in `runtime/events.py`:

- 8 sent-side agent collaboration events (resolver consumes these).
- 8 received-side agent collaboration events (observability).
- `AgentTerminalStatusChangeEvent` (emitted by the watchdog after the
  two-phase pre-publish apply step).

Plus register helpers so the dispatcher knows about them at runtime
startup.

These are workspace-neutral runtime infrastructure — they live in
`runtime/events.py`, not in `local_planning/`.

## Dependencies

None at the framework level. Other tasks (04, 06, 09, 10, 11) consume
these events.

## Files Touched

- `src/cli_agent_orchestrator/runtime/events.py` (extend existing file).
- `test/runtime/test_events.py` (or equivalent — extend existing tests).

## What to do

1. Define the 16 collaboration events. Each must satisfy
   `_EVENT_TYPE_REQUIRED_FIELDS` from `events/__init__.py:120-126` (event_id,
   source, occurred_at, correlation_id, causation_id) and declare its own
   `event_name` class var. Each carries the standard envelope plus
   `sender_agent_id: str` and `sender_workspace_context_id: str` (or
   originator equivalents for baton). Per-event additional fields:

   Sent side (8):
   - `AgentMessageSentEvent` — `receiver_terminal_id: str`,
     `receiver_agent_id: str`, `inbox_message_id: int`.
   - `AgentHandoffInitiatedEvent` — `receiver_agent_id: str`,
     `message: str`.
   - `AgentAssignInitiatedEvent` — `receiver_agent_id: str`,
     `message: str`.
   - `BatonCreatedEvent` — `baton_id: str`, `holder_agent_id: str`,
     `title: str`, `message: str`.
   - `BatonPassedEvent` — `baton_id: str`,
     `from_holder_agent_id: str`, `to_holder_agent_id: str`,
     `message: str`.
   - `BatonReturnedEvent` — `baton_id: str`,
     `from_holder_agent_id: str`, `to_holder_agent_id: str` (the previous
     holder being returned to), `message: str`.
   - `BatonCompletedEvent` — `baton_id: str`,
     `originator_agent_id: str`, `message: str`.
   - `BatonBlockedEvent` — `baton_id: str`,
     `originator_agent_id: str`, `reason: str`.

   Received side (8):
   - `AgentMessageReceivedEvent` — `receiver_agent_id: str`,
     `receiver_terminal_id: str`, `inbox_message_id: int`. (Senders are
     known by correlation to the sent event.)
   - `AgentHandoffAcceptedEvent` — `receiver_agent_id: str`,
     `receiver_terminal_id: str`.
   - `AgentAssignAcceptedEvent` — `receiver_agent_id: str`,
     `receiver_terminal_id: str`.
   - `BatonCreationReceivedEvent` — `baton_id: str`,
     `holder_agent_id: str`.
   - `BatonPassReceivedEvent` — `baton_id: str`,
     `to_holder_agent_id: str`.
   - `BatonReturnReceivedEvent` — `baton_id: str`,
     `to_holder_agent_id: str`.
   - `BatonCompletionReceivedEvent` — `baton_id: str`,
     `originator_agent_id: str`.
   - `BatonBlockReceivedEvent` — `baton_id: str`,
     `originator_agent_id: str`.

2. Define `AgentTerminalStatusChangeEvent` with fields: `agent_id: str`,
   `terminal_id: str`, `previous_status: str`, `new_status: str`.

3. A small shared `@dataclass(frozen=True, kw_only=True)` mixin or base for
   the collaboration events is acceptable to cut down on field
   declarations, but not required. The existing
   `_AgentRuntimeEventMetadata` at `runtime/events.py:72-79` is precedent
   for this pattern.

4. Add `register_agent_collaboration_events(dispatcher)` and
   `register_agent_terminal_status_change_event(dispatcher)` helpers,
   mirroring the existing `register_runtime_cao_events()` at lines
   185-192.

5. Wire both helpers into runtime startup (wherever
   `register_runtime_cao_events()` is currently called from).

## Acceptance

- All 17 events registered and discoverable through
  `default_cao_event_dispatcher().published_events()`.
- Each event round-trips through
  `events.serialization.register_cao_event_serializers()` (this is called
  automatically by `register_events`).
- `event_involves_agent(event, agent_id)` returns `True` for events where
  the agent is sender or receiver, given that the events expose
  `agent_participants` via the existing facet (apply the
  `WithAgentParticipants` facet to the events for timeline integration).
- Existing runtime tests still pass.

## Tests

- Parametrized publish/round-trip test for each event type.
- `event_involves_agent` returns True for both sender and receiver
  identities on each collaboration event.
- Negative test: publishing an event before
  `register_agent_collaboration_events` runs raises
  `UnknownCaoEventError`.

## Out of scope

- Emitting these events from real call sites (Tasks 09, 10, 11).
- The resolver consuming them (Task 07).
- Wrappers like `apply_outbound_resolution` (Task 04).

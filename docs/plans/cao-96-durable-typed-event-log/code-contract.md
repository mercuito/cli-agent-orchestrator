# Feature Code Contract - CAO-96 Durable Typed Event Log

## Applicable Feature-Level Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [implementation-clause-verifiability](../../planning/methodology/criteria/feature-code-contract/implementation-clause-verifiability.md) | Every cross-task code obligation must name a concrete surface and verifiable compliance condition. |
| [stable-code-clause-ids](../../planning/methodology/criteria/feature-code-contract/stable-code-clause-ids.md) | Every feature-level code clause is sliced through `tasks.md`, handoffs, implementation plans, and defences by stable `F-CC-<n>` ID. |

## Architectural Commitments

- `F-CC-1`: Event persistence belongs to the shared CAO event publication
  path. Individual event publishers must not each write directly to the
  durable event log.
  - Illustration: a Linear webhook publisher and a runtime publisher both
    call the shared event dispatcher; neither imports the event-log store
    and saves its own event rows.
- `F-CC-2`: Typed reconstruction belongs to the CAO event serialization
  boundary. Consumer modules must not duplicate event reconstruction logic
  or manually rebuild CAO event objects from stored JSON or envelope
  fields.
  - Illustration: event-log query code delegates stored payload decoding
    to the CAO event serializer; a timeline feature does not manually call
    `LinearAgentMentionedEvent(...)` with values read from a row.
- `F-CC-3`: Durable event storage keeps canonical event bodies separate
  from agent participation lookup data. The event-log persistence layer
  owns one stored event body per event identifier and a separate
  participant index for `(event, agent identity, participant role)` rows.
  - Illustration: a broadcast mention stores one event body in the event
    table and two participant-index rows, not two copies of the full event
    body.
- `F-CC-4`: Durable event queries go through the event-log API boundary.
  Consumers must not read the event-log tables directly to query by event
  identifier, agent identity, event name, source, correlation identifier,
  or causation identifier.
  - Illustration: a timeline feature calls `list_cao_events_by_agent_identity`
    or another event-log query function; it does not build its own SQL
    against `cao_events` or `cao_event_agent_participants`.
- `F-CC-5`: Event-log schema changes use the repo's normal database
  initialization and migration path. The feature must not rely on manual
  setup steps or a one-off schema creation path.
  - Illustration: an existing workspace gains the event-log tables through
    `init_db()` and the repo migration helpers, not through a README step
    telling operators to run custom SQL.
- `F-CC-6`: Dispatcher persistence is an explicit dispatcher mode. The
  implementation must not hard-wire durable writes into every dispatcher
  instance or duplicate persistence setup inside individual publishers.
  - Illustration: production selects a dispatcher construction path that
    enables persistence; individual event publishers do not decide whether
    to persist by importing the event-log store themselves.

## Feature-Specific Code Obligations

- `F-CC-7`: Event identity idempotency is enforced inside the durable
  event-log write boundary. Individual event publishers, subscribers, and
  callers must not implement their own replay handling around stored event
  identity.
  - Illustration: a publisher does not check whether an event ID already
    exists before publishing. The event-log write path owns stored event
    identity handling.

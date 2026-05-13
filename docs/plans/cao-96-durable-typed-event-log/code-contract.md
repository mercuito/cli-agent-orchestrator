# Feature-Level Code Contract - CAO-96 Durable Typed Event Log

## Applicable Feature-Level Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [implementation-clause-verifiability](../../planning/methodology/criteria/feature-code-contract/implementation-clause-verifiability.md) | Every cross-task code obligation must name a concrete surface and verifiable compliance condition. |
| [stable-code-clause-ids](../../planning/methodology/criteria/feature-code-contract/stable-code-clause-ids.md) | Every feature-level code clause is sliced through `tasks.md`, handoffs, implementation plans, and defences by stable `F-CC-<n>` ID. |

## Architectural Commitments

- `F-CC-1`: Durable persistence attaches to the central CAO event
  publication path. Feature-complete compliance means production events
  published through that path can be recorded without individual event
  publishers writing directly to the durable event log.
- `F-CC-2`: Typed event reconstruction remains owned by the CAO event
  boundary. Feature-complete compliance means recorded events can be
  reconstructed as their registered concrete typed event types rather than
  envelope-only stand-ins.
- `F-CC-3`: Agent participant indexing remains part of the durable
  event-log boundary. Feature-complete compliance means the canonical
  event body is stored once per event identifier while each declared
  `(event, agent identity, participant role)` involvement is represented
  separately for identity-scoped lookup.
- `F-CC-4`: Event-log query operations are exposed from the durable
  event-log owner boundary. Feature-complete compliance means consumers
  query by event identifier, agent identity, event name, source,
  correlation identifier, and causation identifier through that boundary
  rather than reading internal persistence details.
- `F-CC-5`: Durable event-log readiness follows the repo's existing
  database migration discipline. Feature-complete compliance means an
  existing CAO database gains the event-log tables and participant index
  idempotently without bypassing the established initialization path.
- `F-CC-6`: Non-persistent dispatch remains available for isolated local
  publication paths. Feature-complete compliance means a dispatcher only
  writes to the shared durable event log when the persistent publication
  mode is explicitly selected.

## Feature-Specific Code Obligations

- `F-CC-7`: Event identifiers are treated as canonical at the durable
  event-log boundary. Feature-complete compliance means republication of
  an existing event identifier preserves the already-recorded canonical
  event and does not add participant entries from a conflicting replay.

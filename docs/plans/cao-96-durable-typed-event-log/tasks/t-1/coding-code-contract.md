# Coding Code Contract - t-1

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| F-CC-1 | Feature Code Contract | The task owns the retrofit of event persistence onto the shared CAO event publication path. |
| F-CC-2 | Feature Code Contract | The task owns typed reconstruction for durable event-log reads. |
| F-CC-3 | Feature Code Contract | The task owns durable event storage and participant-index shape. |
| F-CC-4 | Feature Code Contract | The task owns public event-log query operations and consumer boundaries. |
| F-CC-5 | Feature Code Contract | The task owns initialization and migration support for the event-log schema. |
| F-CC-6 | Feature Code Contract | The task owns dispatcher persistence mode and production publication wiring. |
| F-CC-7 | Feature Code Contract | The task owns idempotency at the durable event-log write boundary. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| full-verification-required | The task includes production and test code changes, and the handoff names an exact verification command. |
| red-green-refactor | The retrofit has testable persistence, reconstruction, query, migration, and idempotency behaviors. |
| boundary-and-failure-testing | Dispatcher publication, serializer reconstruction, event-log writes, query operations, and migrations accept runtime or stored input. |
| semantic-continuity | The durable path extends existing CAO event dispatch, Linear event, runtime event, and database initialization paths. |
| minimal-cohesive-changes | The retrofit must stay limited to CAO event persistence, serialization, dispatcher wiring, migration support, and direct proof. |
| no-unnecessary-duplication | Event envelope handling, participant extraction, serializer registration, and database setup already have owner surfaces to reuse. |
| no-test-only-production-seams | Dispatcher persistence mode and serializer registry behavior must serve production, not only tests. |
| respect-ownership-boundaries | The task crosses the event framework, event serialization, event-log persistence, database migration, Linear event, and runtime event owner surfaces. |
| centralized-vocabulary | The task introduces durable event-log table names, index names, and event-name vocabulary used across models and migrations. |
| prefer-public-surfaces | Production consumers must use dispatcher and event-log APIs rather than deep table reads or ad hoc reconstruction. |
| readable-and-explicit | The event-log write/query boundaries carry non-obvious idempotency, reconstruction, ordering, and participant-index behavior. |
| service-definition-surface | `cao_event_store` creates a shared event-log persistence service module. |
| service-export-discipline | `clients.database` exposes the event-log record and query operations required by existing database facade consumers. |
| well-defined-service | The durable event-log store is a new shared persistence service owned by `clients.cao_event_store`. |
| migration-discipline | Existing databases gain event-log tables and participant ordering support through the repo migration path. |

## Task-Specific Code Obligations

- `C-CC-1`: `CaoEventDispatcher` must keep non-persistent local dispatchers available by default while exposing an explicit persistent dispatcher mode for production publication.
- `C-CC-2`: Persistent dispatch must call one event-log write boundary before subscriber handlers run and must not require Linear, runtime, or other individual publishers to import the event store.
- `C-CC-3`: Event-log read operations must return `CaoEventRecord` values whose `event` field is reconstructed through `cli_agent_orchestrator.events.serialization.deserialize_cao_event`.
- `C-CC-4`: `cao_events` must store one canonical typed payload row per event identifier, while `cao_event_agent_participants` stores only participant lookup rows keyed by event identifier, agent identity, and participant role.
- `C-CC-5`: Same-identifier persistence must preserve the first canonical stored event and must not add participant-index rows from conflicting replays.
- `C-CC-6`: Query operations for event identifier, agent identity, event name, source, correlation identifier, and causation identifier must live on the event-log API boundary exposed through `clients.database`.
- `C-CC-7`: Database initialization and migration code must create the event-log tables and maintain the participant occurrence index without manual operator setup.

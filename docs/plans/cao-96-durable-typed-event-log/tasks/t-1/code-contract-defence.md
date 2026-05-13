# Code Contract Defence

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| claim-evidence-verifiability | Every feature-level and coding-level code claim needs direct code evidence. |

## Feature-Level Code Contract

### Clause: F-CC-1

**Claim:** Persistence is attached to the shared dispatcher publication path,
not individual Linear or runtime publishers.
**Evidence:** `CaoEventDispatcher.publish` calls `persist_cao_event` only when
dispatcher persistence is enabled (`src/cli_agent_orchestrator/events/__init__.py:234`);
Linear and runtime publishers register event families then call the dispatcher
(`src/cli_agent_orchestrator/linear/workspace_events.py:186`,
`src/cli_agent_orchestrator/runtime/events.py:170`).

### Clause: F-CC-2

**Claim:** Typed reconstruction is centralized at the serializer boundary.
**Evidence:** `CaoEventSerializerRegistry.deserialize` imports/registers event
types and decodes dataclass fields (`src/cli_agent_orchestrator/events/serialization.py:55`);
`_record_from_model` delegates stored payload decoding to `deserialize_cao_event`
(`src/cli_agent_orchestrator/clients/cao_event_store.py:198`).

### Clause: F-CC-3

**Claim:** Canonical typed payloads and participant lookup data are separated.
**Evidence:** `CaoEventModel` owns the canonical event payload row
(`src/cli_agent_orchestrator/clients/cao_event_store.py:19`);
`CaoEventAgentParticipantModel` owns `(event, agent, role)` lookup rows
(`src/cli_agent_orchestrator/clients/cao_event_store.py:41`).

### Clause: F-CC-4

**Claim:** Event-log queries go through event-log API operations exposed by the
database facade.
**Evidence:** `get_cao_event`, `list_cao_events_by_agent_identity`,
`list_cao_events_by_event_name`, `list_cao_events_by_source`,
`list_cao_events_by_correlation_id`, and `list_cao_events_by_causation_id`
are implemented in `clients.cao_event_store` and exported from
`clients.database` (`src/cli_agent_orchestrator/clients/database.py:21`,
`src/cli_agent_orchestrator/clients/database.py:195`).

### Clause: F-CC-5

**Claim:** Schema changes use the repo's initialization and migration path.
**Evidence:** `init_db()` calls `_migrate_ensure_cao_event_tables`
(`src/cli_agent_orchestrator/clients/database_migrations.py:45`); the migration
creates event-log tables and participant occurrence indexes with normal
SQLAlchemy/SQLite migration helpers (`src/cli_agent_orchestrator/clients/database_migrations.py:318`).

### Clause: F-CC-6

**Claim:** Dispatcher persistence is an explicit dispatcher mode.
**Evidence:** `CaoEventDispatcher.__init__` defaults `persist_events=False`
and `CaoEventDispatcher.persistent()` opts into persistence
(`src/cli_agent_orchestrator/events/__init__.py:163`,
`src/cli_agent_orchestrator/events/__init__.py:186`).

### Clause: F-CC-7

**Claim:** Event identity idempotency is enforced inside the durable write
boundary.
**Evidence:** `persist_cao_event` uses `sqlite_insert(CaoEventModel)...
on_conflict_do_nothing(index_elements=["event_id"])` and only inserts
participants on the canonical insert path
(`src/cli_agent_orchestrator/clients/cao_event_store.py:82`).

## Coding Code Contract Criteria

### Criterion: full-verification-required

**Claim:** The exact handoff Verification Command was run successfully before
completion.
**Evidence:** `coding-completion-report.md` records
`uv run pytest test/events/test_cao_event_persistence.py test/events/test_core.py`
passing with 19 tests.

### Criterion: red-green-refactor

**Claim:** The production gap was exposed by proof first, then fixed at the
runtime event owner surface.
**Evidence:** The new participantless runtime proof initially failed with
`ImportError: cannot import name 'RuntimeWorkspaceEvent'`; the fix added
`RuntimeWorkspaceEvent` and `workspace_runtime_event` in
`src/cli_agent_orchestrator/runtime/events.py`.

### Criterion: boundary-and-failure-testing

**Claim:** Dispatcher, event-log, serializer, idempotency, query, and migration
boundaries have success and boundary/failure proof.
**Evidence:** `test/events/test_cao_event_persistence.py` covers unknown event
ids, empty envelope queries, local non-persistent dispatchers, conflicting
same-id replays, participantless events, and legacy migration repair.

### Criterion: semantic-continuity

**Claim:** The new runtime workspace event uses existing runtime event
registration and dispatcher publication patterns.
**Evidence:** `RuntimeWorkspaceEvent` is included in `RUNTIME_CAO_EVENTS`, and
`register_runtime_cao_events` registers the full tuple through the dispatcher
(`src/cli_agent_orchestrator/runtime/events.py:161`,
`src/cli_agent_orchestrator/runtime/events.py:170`).

### Criterion: minimal-cohesive-changes

**Claim:** Production edits stay inside the runtime event owner surface needed
for the assigned participantless runtime branch.
**Evidence:** Production changes are limited to `runtime/events.py` and
`runtime/__init__.py`; event-store, dispatcher, serializer, and migration code
retain the candidate architecture.

### Criterion: no-unnecessary-duplication

**Claim:** The implementation reuses existing dispatcher, serializer,
participant extraction, and migration surfaces.
**Evidence:** Persistent dispatch calls `persist_cao_event`; event-log
reconstruction calls `deserialize_cao_event`; participant rows use
`agent_participants_for`; runtime events share `_runtime_event_id` and
`_runtime_source_ref`.

### Criterion: no-test-only-production-seams

**Claim:** Added production surface serves the approved workspace-wide runtime
event behavior, not test harness convenience.
**Evidence:** `RuntimeWorkspaceEvent` is a runtime-owned CAO event registered
with other runtime event families in `RUNTIME_CAO_EVENTS`, not a test helper.

### Criterion: respect-ownership-boundaries

**Claim:** Event framework, serialization, event-log persistence, migrations,
and runtime event-family code remain in their owner modules.
**Evidence:** Dispatcher code stays in `events.__init__`; serialization in
`events.serialization`; storage in `clients.cao_event_store`; schema migration
in `clients.database_migrations`; runtime event declarations in
`runtime.events`.

### Criterion: centralized-vocabulary

**Claim:** Durable event-log table and participant occurrence index vocabulary
has one owner and migrations derive those names from that owner.
**Evidence:** `clients.cao_event_store` defines `CAO_EVENTS_TABLE`,
`CAO_EVENT_AGENT_PARTICIPANTS_TABLE`, and
`CAO_EVENT_AGENT_PARTICIPANTS_AGENT_OCCURRED_INDEX`; `_migrate_ensure_cao_event_tables`
uses `CaoEventModel.__tablename__`, `CaoEventAgentParticipantModel.__tablename__`,
model column names, and the shared index constant.

### Criterion: prefer-public-surfaces

**Claim:** Tests and consumers exercise dispatcher and database facade query
operations rather than direct query SQL for behavior proof.
**Evidence:** Event-log behavior tests call `CaoEventDispatcher.publish` and
`db_module.get_cao_event` / `db_module.list_cao_events_by_*`; direct model
inspection is limited to verifying storage row counts for canonicality.

### Criterion: readable-and-explicit

**Claim:** Non-obvious persistence mode, idempotency, participant indexing, and
runtime workspace semantics are visible in names and boundaries.
**Evidence:** `persist_events`, `persistent()`, `persist_cao_event`,
`CaoEventAgentParticipantModel`, and `RuntimeWorkspaceEvent` name the behavior
they own.

### Criterion: service-definition-surface

**Claim:** The event-log persistence service surface is easy to scan.
**Evidence:** `clients.cao_event_store` defines models, `CaoEventRecord`, write,
read, and list operations in one focused module.

### Criterion: service-export-discipline

**Claim:** Public database facade exports are limited to consumer-facing
event-log query operations and record type required by the contracts.
**Evidence:** `clients.database` exports `CaoEventRecord`, `get_cao_event`,
and `list_cao_events_by_*`; event-log models and `persist_cao_event` remain
owned by `clients.cao_event_store` rather than the facade.

### Criterion: well-defined-service

**Claim:** Durable event-log persistence has an explicit owner and public
boundary.
**Evidence:** `clients.cao_event_store` owns the durable event-log models and
API; `clients.database` preserves the repo's historical database facade.

### Criterion: migration-discipline

**Claim:** Migration work moves existing databases to the new schema shape
without a compatibility bridge or manual setup.
**Evidence:** `_migrate_ensure_cao_event_tables` creates missing tables, adds
legacy `occurred_at` participant columns, and recreates the participant
occurrence index.

## Coding Code Contract Obligations

### Clause: C-CC-1

**Claim:** Local dispatchers remain non-persistent by default, and persistent
mode is explicit.
**Evidence:** `CaoEventDispatcher.__init__(..., persist_events=False)` and
`CaoEventDispatcher.persistent()`; `test_local_dispatchers_remain_non_persistent_by_default`.

### Clause: C-CC-2

**Claim:** Persistent dispatch writes before subscribers and publishers do not
own direct persistence.
**Evidence:** `CaoEventDispatcher.publish` persists before iterating
subscriptions; Linear and runtime publishers only register and publish through
dispatchers.

### Clause: C-CC-3

**Claim:** Event-log reads reconstruct through `deserialize_cao_event`.
**Evidence:** `_record_from_model` calls `deserialize_cao_event` before
returning `CaoEventRecord`.

### Clause: C-CC-4

**Claim:** Storage keeps one canonical typed payload row and separate
participant rows.
**Evidence:** `CaoEventModel`, `CaoEventAgentParticipantModel`, and
`test_agent_participant_queries_support_broadcasts_without_duplicate_payload_rows`.

### Clause: C-CC-5

**Claim:** Same-identifier persistence preserves the first canonical event and
does not absorb conflicting replay participants.
**Evidence:** `persist_cao_event` only inserts participant rows when the
canonical event row insert succeeds; proven by
`test_duplicate_event_id_does_not_add_participants_from_conflicting_replay`.

### Clause: C-CC-6

**Claim:** Public event-log query APIs cover identifier, agent, name, source,
correlation, and causation lookups.
**Evidence:** `clients.cao_event_store` implements and `clients.database`
exports all listed query functions.

### Clause: C-CC-7

**Claim:** Initialization and migration create event-log tables and participant
occurrence indexes without manual setup.
**Evidence:** `_migrate_ensure_cao_event_tables`; migration tests for new and
legacy schemas.

## Committed Implementation Decisions

No committed implementation decisions are currently in force for CAO-96.

## Committed-Decision Promotion Draft

No promotion warranted: this task implemented and validated the approved
contracts but did not settle a new cross-task implementation decision beyond
those contracts.

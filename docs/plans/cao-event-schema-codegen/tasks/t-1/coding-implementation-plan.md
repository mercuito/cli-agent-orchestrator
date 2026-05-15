# Coding Implementation Plan — t-1

## Research Findings

Investigated the assigned backend surfaces:

- `runtime/events.py` and `linear/workspace_events.py` currently use stdlib dataclasses for all CAO event declarations. Linear subtype classes inherit most event fields from `LinearIssueContextEvent`; runtime agent events inherit from `_AgentRuntimeEventMetadata`; `RuntimeWorkspaceEvent` and `LinearIssueCreatedEvent` are standalone.
- `events/serialization.py` currently registers by `event_type_key(event_type)`, writes module-qualified class keys, and dynamically imports unknown keys during deserialization.
- `clients/cao_event_store.py` currently has `CaoEventModel.event_type_key` as a storage column and reconstructs by passing that stored value to the serializer. `CaoEventRecord.event_type_key` is consumed by `agent_identity_timeline.py` and API response construction as a public compatibility value.
- `database_migrations.py` owns `_migrate_ensure_cao_event_tables()`, already creates event tables and updates participant occurrence indexes for legacy databases.
- `test/events/test_cao_event_persistence.py` already proves persistence, participant indexing, ordering, duplicate replay, non-persistent dispatchers, and CAO event table migration. It does not yet prove all registered event classes, kind-only storage shape, dynamic-import removal, or legacy-row kind backfill/read-path reconstruction.

Risks and unknowns:

- SQLite legacy-column removal must work against existing test-created legacy tables and normal `Base.metadata.create_all()` tables.
- Pydantic dataclasses must preserve `dataclasses.fields`, `dataclasses.replace`, equality, and `NewType` values used by the assigned tests.
- The public `event_type_key` response field is not owned as a storage discriminator in this task, but storage reads must still expose a compatibility value so assigned API tests continue to pass.

## High-Level Architecture

**Surface shape.** Linear and runtime event modules will import `pydantic.dataclasses.dataclass` and `typing.Literal`, then add class-specific `kind` fields to the concrete CAO event classes. Shared base dataclasses remain dataclasses but do not introduce a generic `kind`, so each concrete class owns its discriminator literal.

**Serializer shape.** `CaoEventSerializerRegistry` will store `_event_types_by_kind`. A small internal helper will extract and validate the `kind` literal from registered classes and event instances. `serialize_cao_event()` will continue to return `(discriminator, event_data_json)`, but the discriminator will be `kind`. `deserialize_cao_event(kind, payload)` will require prior explicit registration and raise `UnknownCaoEventError` for unregistered values.

**Storage shape.** `CaoEventModel` will replace `event_type_key` with `kind`. `persist_cao_event()` will write `kind`. `_record_from_model()` will deserialize by `kind` and compute `CaoEventRecord.event_type_key` from the reconstructed event class for the existing timeline/API compatibility envelope.

**Migration shape.** `_migrate_ensure_cao_event_tables()` will keep table creation in the database migration owner. For legacy `cao_events` tables it will add/backfill `kind` from a mapping of known registered CAO event classes, reject unresolved legacy keys, then remove `event_type_key` with SQLite `ALTER TABLE DROP COLUMN` after dropping the legacy index if present. Participant occurrence index migration remains in the same helper.

**Reuse points.** The implementation will reuse `LINEAR_CAO_EVENTS`, `RUNTIME_CAO_EVENTS`, `register_linear_cao_events`, `register_runtime_cao_events`, existing dispatcher/store entry points, and existing test fixtures in `test/events/test_cao_event_persistence.py`.

## Sub-Task List

1. Add failing characterization/persistence tests for kinded storage and all-event round trips.
   - Clauses satisfied: F-TC-1, F-TC-2, F-TC-6, C-TC-1, C-TC-2, C-TC-5.
   - Done condition: Focused tests fail on the current legacy discriminator implementation for missing `kind`/all-event coverage without weakening existing assertions.
   - Dependency order: First.

2. Add failing migration/read-path tests for legacy rows and explicit serializer registration.
   - Clauses satisfied: F-TC-5, F-TC-6, C-TC-3, C-TC-4.
   - Done condition: Focused tests demonstrate current absence of legacy kind backfill/drop-column and current dynamic import fallback behavior.
   - Dependency order: After sub-task 1.

3. Convert Linear/runtime event declarations to Pydantic dataclasses with stable `kind` literals.
   - Clauses satisfied: F-CC-1, F-CC-2, F-CC-9, C-CC-1.
   - Done condition: Event factories and assigned runtime/API tests construct events without caller changes; dataclass equality still compares the original and reconstructed instances.
   - Dependency order: After failing tests exist.

4. Rework serializer registry from legacy type keys to registered kinds.
   - Clauses satisfied: F-CC-3, F-CC-7, F-CC-8, F-CC-9, C-CC-2, C-CC-6, C-TC-4.
   - Done condition: Serializer helper/dynamic import removal is complete, unknown kinds fail, explicit registration reconstructs events, and current serializer callers pass kind strings.
   - Dependency order: After sub-task 3.

5. Rework storage model, write/read paths, and migration helper to use `kind`.
   - Clauses satisfied: F-CC-6, F-CC-7, F-CC-8, C-CC-3, C-CC-4, C-CC-5, C-CC-6, C-TC-2, C-TC-3.
   - Done condition: New writes store only `kind`, legacy rows migrate/drop `event_type_key`, and production read paths reconstruct typed events while public timeline compatibility values remain available.
   - Dependency order: After sub-task 4.

6. Run caller discovery, focused tests, and the exact Verification Command.
   - Clauses satisfied: F-CC-8, F-TC-1, C-CC-6, all selected verification criteria.
   - Done condition: Discovery results are ready for the Code Contract Defence, focused tests pass, and `uv run pytest test/events/test_cao_event_persistence.py test/api/test_agent_identity_routes.py test/runtime/test_agent_runtime.py` succeeds.
   - Dependency order: Last.

## Revision Log

No revisions yet.

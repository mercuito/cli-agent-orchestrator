# Test Contract Defence — t-1

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Always applies; every claim below cites concrete tests, fixtures, or verification output. |

## Feature-Level Test Contract

### Clause: F-TC-1

**Claim:** The assigned backend persistence preservation baseline passes at the
Verification Command boundary.

**Evidence:** Exact command
`uv run pytest test/events/test_cao_event_persistence.py test/api/test_agent_identity_routes.py test/runtime/test_agent_runtime.py`
passed with 70 collected tests and 70 passed.

### Clause: F-TC-2

**Claim:** The kind round-trip seam is proven end to end for every registered
Linear/runtime CAO event class.

**Evidence:** `test_each_registered_cao_event_round_trips_through_kinded_storage`
constructs one instance for each member of `LINEAR_CAO_EVENTS +
RUNTIME_CAO_EVENTS`, persists through `CaoEventDispatcher(...,
persist_events=True)`, reads through `db_module.get_cao_event()`, and asserts
dataclass equality plus stored payload `kind`.

### Clause: F-TC-5

**Claim:** The legacy migration/read-path seam is proven over pre-existing rows.

**Evidence:** `test_cao_event_migration_backfills_kind_and_reconstructs_legacy_rows`
creates a pre-migration `cao_events` table with `event_type_key`, seeds a
legacy payload without `kind`, runs `_migrate_ensure_cao_event_tables()`, then
asserts reconstruction through `get_cao_event`,
`list_cao_events_by_agent_identity`, `list_cao_events_by_event_name`,
`list_cao_events_by_source`, `list_cao_events_by_correlation_id`,
`list_cao_events_by_causation_id`, and `AgentIdentityTimelineService`.
`test_cao_event_migration_updates_legacy_participant_occurrence_index` also
asserts legacy table migration backfills kind, drops `event_type_key`, and
preserves participant occurrence indexing.

### Clause: F-TC-6

**Claim:** Research-surfaced uncovered backend/storage behavior is
characterized before and after the refactor.

**Evidence:** New characterization covers all registered event classes, fresh
serializer registry behavior, kind-only storage table shape, and legacy
migration/read-path behavior. Existing participant, ordering, duplicate replay,
non-persistent dispatcher, API route, and runtime publication tests remain in
the baseline and pass.

## Coding Test Contract — Selected Criteria

### Criterion: test-validity-preserved

**Claim:** Existing tests keep validating their target behavior; discriminator
expectations were adapted only where the assigned refactor changed the
authorized backend storage/serializer target.

**Evidence:** The exact Verification Command passed. Existing API/runtime
assertions remain intact, including public `event_type_key` response assertions
in `test/api/test_agent_identity_routes.py` and runtime event publication
assertions in `test/runtime/test_agent_runtime.py`.

### Criterion: given-when-then-test-structure

**Claim:** Added multi-step tests expose setup, action, and assertion phases.

**Evidence:** New tests follow the existing file's pattern: fixture/control
events are built first, production dispatcher/migration/read operations happen
in the test body, and assertions inspect records, table columns, or timeline
reads afterward.

### Criterion: public-boundary-proof

**Claim:** Changed persistence and API-read boundaries are exercised directly.

**Evidence:** Tests use `CaoEventDispatcher`, `db_module.get_cao_event()`,
`db_module.list_cao_events_by_agent_identity()`,
`AgentIdentityTimelineService`, and API `client.get(...)` calls rather than
mocking the store or route outputs.

### Criterion: real-surface-proof-discipline

**Claim:** Integration risks are proven through real serializer, SQLite,
SQLAlchemy, migration, store, service, and route surfaces.

**Evidence:** `runtime_inbox_db_session` creates real SQLite-backed SQLAlchemy
tables for persistence tests; migration tests create real SQLite databases via
`create_engine`; API tests use the test client; no mock replaces the storage
surface under test.

### Criterion: inspectable-authored-inputs

**Claim:** Authored legacy schema and payload inputs remain visible where they
drive assertions.

**Evidence:** `test_cao_event_migration_updates_legacy_participant_occurrence_index`
and `test_cao_event_migration_backfills_kind_and_reconstructs_legacy_rows`
inline the pre-migration `CREATE TABLE` SQL, legacy `event_type_key` seed data,
and payload manipulation (`legacy_payload.pop("kind", None)`) that explain the
migration assertions.

### Criterion: setup-invariant-ownership

**Claim:** Reusable fixture setup owns event validity rather than repeating
fixture guards in leaf tests.

**Evidence:** `_linear_issue_context_kwargs()`, `_linear_mentioned_event()`,
`_linear_issue_context_event()`, `_linear_issue_created_event()`, and
`_all_registered_event_instances()` centralize valid event setup. Leaf tests
assert the behavior under test.

### Criterion: reusable-test-state

**Claim:** Repeated event setup is named and reused.

**Evidence:** The new all-event and migration tests reuse existing event
factories plus the new helpers instead of duplicating full Linear event payloads
per scenario.

### Criterion: test-through-owner-surfaces

**Claim:** Tests depend on subsystem behavior through owner surfaces.

**Evidence:** Persistence proof goes through `CaoEventDispatcher` and
`db_module` store entry points; migration proof goes through
`db_module._migrate_ensure_cao_event_tables()` as the existing migration owner;
timeline proof goes through `AgentIdentityTimelineService`.

### Criterion: test-artifact-containment

**Claim:** SQLite files, tables, and rows created by the tests stay contained in
test-owned lifecycles.

**Evidence:** Migration tests create SQLite database files only under
`tmp_path`; persistence tests use the `runtime_inbox_db_session` in-memory
SQLite fixture. No test writes migration artifacts into shared repo or user
paths.

### Criterion: test-file-organization

**Claim:** The expanded persistence test file remains organized by behavior
family.

**Evidence:** Added tests are placed near related persistence/restart proofs and
existing migration tests remain grouped at the bottom of
`test/events/test_cao_event_persistence.py`.

### Criterion: verification-scope-discipline

**Claim:** Focused and full verification were both run.

**Evidence:** Focused persistence command
`uv run pytest test/events/test_cao_event_persistence.py -q` passed after
implementation. The exact handoff Verification Command passed after final
formatting.

## Coding Test Contract — Task-Specific Proof Obligations

### Clause: C-TC-1

**Claim:** Every registered Linear/runtime event class is persisted and
reconstructed through production paths.

**Evidence:** `test_each_registered_cao_event_round_trips_through_kinded_storage`
covers every member of `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`.

### Clause: C-TC-2

**Claim:** New persisted table shape and payload kind are asserted directly.

**Evidence:** `test_new_cao_event_writes_store_kind_without_legacy_discriminator`
inspects `cao_events` columns and row `kind`; the all-event round-trip test
asserts `record.event_data["kind"] == event.kind`.

### Clause: C-TC-3

**Claim:** Legacy rows migrate and reconstruct through store, list, and timeline
read paths.

**Evidence:** `test_cao_event_migration_backfills_kind_and_reconstructs_legacy_rows`
seeds a pre-migration row, runs migration, registers events, then checks
`get_cao_event`, `list_cao_events_by_agent_identity`,
`list_cao_events_by_event_name`, `list_cao_events_by_source`,
`list_cao_events_by_correlation_id`, `list_cao_events_by_causation_id`, and
`AgentIdentityTimelineService.timeline_for_identity()`.

### Clause: C-TC-4

**Claim:** Fresh registry reconstruction requires explicit kind registration.

**Evidence:** `test_persisted_event_requires_explicit_kind_registration_after_registry_restart`
resets the serializer registry, asserts `UnknownCaoEventError`, then calls
`register_linear_cao_events(CaoEventDispatcher())` and proves reconstruction.

### Clause: C-TC-5

**Claim:** Existing participant index, ordering, duplicate replay,
non-persistent dispatcher, API, and runtime baselines are preserved.

**Evidence:** Existing tests in `test/events/test_cao_event_persistence.py`,
`test/api/test_agent_identity_routes.py`, and `test/runtime/test_agent_runtime.py`
all pass under the exact Verification Command. No existing participant,
ordering, duplicate replay, or route assertion was skipped.

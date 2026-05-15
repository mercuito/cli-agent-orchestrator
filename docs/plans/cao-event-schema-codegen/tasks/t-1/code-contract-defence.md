# Code Contract Defence — t-1

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Always applies; every claim below cites concrete code, discovery, or verification evidence. |
| `promotion-draft-durability` | This defence proposes one durable committed-decision entry for later tasks. |

## Feature-Level Code Contract

### Clause: F-CC-1

**Claim:** Every assigned Linear/runtime CAO event class declares a stable
instance-level `kind` literal default.

**Evidence:** `src/cli_agent_orchestrator/linear/workspace_events.py` declares
`kind: Literal[...]` on `LinearAgentMentionedEvent`,
`LinearIssueDelegatedToAgentEvent`, `LinearAgentSessionPromptedEvent`,
`LinearAgentSessionLifecycleActivityEvent`,
`LinearAgentSessionStopRequestedEvent`, and `LinearIssueCreatedEvent`.
`src/cli_agent_orchestrator/runtime/events.py` declares `kind: Literal[...]`
on `AgentRuntimeNotificationAcceptedEvent`,
`AgentRuntimeNotificationDeliveryEvent`, `AgentRuntimeLifecycleEvent`,
`AgentRuntimeWorkspaceContextSwitchEvent`, and `RuntimeWorkspaceEvent`.

### Clause: F-CC-2

**Claim:** Every assigned Linear/runtime CAO event class is now a Pydantic
dataclass while preserving dataclass/factory behavior.

**Evidence:** `linear/workspace_events.py` and `runtime/events.py` import
`dataclass` from `pydantic.dataclasses` and apply
`@dataclass(frozen=True, kw_only=True)` to the affected declarations. The exact
Verification Command passed; it exercises factory construction, dataclass
equality, `dataclasses.replace()`, and persistence reconstruction for those
types.

### Clause: F-CC-3

**Claim:** Serializer registration and reconstruction are keyed by registered
`kind`, and unknown kinds do not dynamically import classes.

**Evidence:** `events/serialization.py` stores `_event_types_by_kind`, validates
kind literals via `cao_event_kind()`, returns `event.kind` from `serialize()`
only when the kind is already registered for that class, and raises
`UnknownCaoEventError` from both `serialize()` and `deserialize()` when a kind
is not registered. The legacy `_import_event_type()` and `event_type_key()`
helpers are absent. Discovery command `rg 'event_type_key\\(|_import_event_type|_event_types_by_key|event_type_key = Column' src/cli_agent_orchestrator test --glob '!src/cli_agent_orchestrator/web_ui/assets/**'` returns only the new public compatibility helper name in `cao_event_store.py`, not the removed serializer helper, dynamic import fallback, old registry dict, or storage column.

### Clause: F-CC-6

**Claim:** `cao_events` stores `kind` as the backend storage discriminator,
migrates legacy rows, drops the legacy column, and read paths deserialize from
`kind`.

**Evidence:** `clients/cao_event_store.py` defines `CaoEventModel.kind`, writes
`"kind": kind` in `persist_cao_event()`, and calls `deserialize_cao_event(kind,
event_data_json)` in `_record_from_model()`. `clients/database_migrations.py`
adds/backfills `kind`, raises for unresolved legacy keys, drops
`event_type_key`, and creates `ix_cao_events_kind`. `test_cao_event_migration_backfills_kind_and_reconstructs_legacy_rows` seeds a legacy row, runs `_migrate_ensure_cao_event_tables()`, and proves `get_cao_event`, `list_cao_events_by_agent_identity`, and `AgentIdentityTimelineService` reconstruct it.

### Clause: F-CC-7

**Claim:** Backend/storage replacement surfaces are removed rather than
retained as parallel paths.

**Evidence:** `CaoEventModel` has no `event_type_key` column; `persist_cao_event`
does not dual-write; `events/serialization.py` has no `_import_event_type()` or
`event_type_key()` helper; Linear/runtime event modules use Pydantic dataclasses.
The remaining `event_type_key` code in backend production is limited to the
public compatibility projection on `CaoEventRecord`/timeline/API response
surfaces.

### Clause: F-CC-8

**Claim:** Backend/storage caller migration was discovered and classified.

**Evidence:** Discovery command
`rg 'serialize_cao_event|deserialize_cao_event' src/ test/ --glob '!src/cli_agent_orchestrator/web_ui/assets/**'`
found only `clients/cao_event_store.py` production callers plus the legacy
payload setup in `test/events/test_cao_event_persistence.py`; production callers
now pass `kind`. Discovery command `rg 'event_type_key' src test --glob '!src/cli_agent_orchestrator/web_ui/assets/**'`
found remaining production references in `agent_identity_timeline.py`,
`api/main.py`, and `cao_event_store.py` as public compatibility projection, and
in `database_migrations.py` as legacy migration-only input. Test matches are
public API assertions, legacy migration fixtures, or assertions that the legacy
column is absent. Constructor discovery command
`for name in LinearAgentMentionedEvent ... RuntimeWorkspaceEvent; do rg -l "$name" src test --glob '!src/cli_agent_orchestrator/web_ui/assets/**'; done`
found production references in declaration/factory/registration/export modules
(`linear/workspace_events.py`, `runtime/events.py`, `runtime/__init__.py`) and
type consumers (`linear/workspace_context_resolver.py`), with test references in
the assigned persistence/API/runtime baselines plus Linear provider/context
tests. Outcome: no production constructor caller needed a new `kind` argument
because every event class supplies a default literal; the exact Verification
Command passed.

### Clause: F-CC-9

**Claim:** Persistence reconstruction equality and required protocol
attributes are preserved.

**Evidence:** `test_each_registered_cao_event_round_trips_through_kinded_storage`
persists every member of `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS` through the
production dispatcher/write path and equality-asserts the production read path
result against the original. The exact Verification Command also preserves the
API and runtime baselines that construct and publish these events.

## Coding Code Contract — Selected Criteria

### Criterion: full-verification-required

**Claim:** The handoff Verification Command succeeded.

**Evidence:** `uv run pytest test/events/test_cao_event_persistence.py test/api/test_agent_identity_routes.py test/runtime/test_agent_runtime.py` passed with 70 collected tests and 70 passed.

### Criterion: semantic-continuity

**Claim:** Existing dispatch, persistence, participant indexing, and timeline
read behavior continue through the same owner paths with the new discriminator.

**Evidence:** Existing tests in `test/events/test_cao_event_persistence.py`,
`test/api/test_agent_identity_routes.py`, and `test/runtime/test_agent_runtime.py`
still pass under the exact Verification Command; no production caller bypasses
`persist_cao_event()`, `deserialize_cao_event()`, or the timeline service.

### Criterion: no-unnecessary-duplication

**Claim:** Kind vocabulary and legacy mapping reuse event declarations rather
than duplicating independent discriminator tables.

**Evidence:** `events/serialization.py::cao_event_kind()` derives kind from
the event class `Literal`; `database_migrations.py::_cao_event_kind_by_legacy_type_key()`
iterates `LINEAR_CAO_EVENTS` and `RUNTIME_CAO_EVENTS` and calls
`cao_event_kind()` for the backfill map.

### Criterion: respect-ownership-boundaries

**Claim:** Event declarations, serialization, storage, migration, and timeline
compatibility remained in their owning modules.

**Evidence:** Event kind declarations are in `runtime/events.py` and
`linear/workspace_events.py`; serializer lookup is in `events/serialization.py`;
storage model/read/write behavior is in `clients/cao_event_store.py`; migration
logic is in `clients/database_migrations.py`; API/timeline compatibility
models were not moved.

### Criterion: centralized-vocabulary

**Claim:** The storage discriminator has one authoritative event-class source.

**Evidence:** Serializer and migration code both consume `cao_event_kind()`;
tests assert concrete kind values only at storage/proof boundaries.

### Criterion: prefer-public-surfaces

**Claim:** Cross-boundary behavior uses owner entry points.

**Evidence:** Tests persist through `CaoEventDispatcher(..., persist_events=True)`,
read through `db_module.get_cao_event()` / list surfaces, and use
`AgentIdentityTimelineService` for timeline proof. Migration imports registered
event tuples and the serializer-owned `cao_event_kind()` helper rather than
deep-reading dataclass fields independently.

### Criterion: readable-and-explicit

**Claim:** New discriminator behavior and failure modes are explicit.

**Evidence:** `cao_event_kind()` names literal validation; `_event_instance_kind()`
checks instance/class alignment; migration raises `ValueError` naming unresolved
legacy rows; read-path compatibility uses `_public_event_type_key()`.

### Criterion: service-definition-surface

**Claim:** Shared service surfaces remain easy to scan after reshaping.

**Evidence:** `CaoEventSerializerRegistry` still exposes `register`,
`serialize`, and `deserialize` near the top of `events/serialization.py`.
`CaoEventModel`, `CaoEventRecord`, and persistence/list functions remain grouped
in `clients/cao_event_store.py`.

### Criterion: service-export-discipline

**Claim:** No speculative public export was added.

**Evidence:** The serializer vocabulary helper `cao_event_kind()` is intentionally
public because `database_migrations.py` needs the same authoritative kind
derivation for legacy backfill; `_event_instance_kind()` and
`_public_event_type_key()` remain private. No `__all__` or package-root export
was added.

### Criterion: well-defined-service

**Claim:** The reshaped serializer and store services have explicit owners,
homes, boundaries, and public surfaces.

**Evidence:** The serializer registry is owned by
`cli_agent_orchestrator.events.serialization`; its public surface remains
`register_cao_event_serializers`, `serialize_cao_event`, and
`deserialize_cao_event`, with `cao_event_kind()` as the public vocabulary helper
used by migrations, while `_event_instance_kind()` stays private. The event store
is owned by `cli_agent_orchestrator.clients.cao_event_store`; its consumer-facing
facade remains exported through
`cli_agent_orchestrator.clients.database`, while `_public_event_type_key()` stays
private. Migration-specific legacy mapping stays in
`clients/database_migrations.py`.

### Criterion: migration-discipline

**Claim:** Existing backend callers moved to the new shape and the retired
storage column/helper were removed.

**Evidence:** `clients/cao_event_store.py` writes and reads `kind`; legacy
column handling is isolated to `_migrate_ensure_cao_event_tables()`; discovery
found no remaining old serializer helper or SQLAlchemy storage column.

### Criterion: no-assumed-backwards-compatibility

**Claim:** No old backend storage/serializer compatibility path remains beyond
explicit public timeline projection.

**Evidence:** There is no dynamic import fallback, no dual-write storage, no
`event_type_key()` serializer helper, and no `event_type_key` model column.
`CaoEventRecord.event_type_key` is computed from the reconstructed class for
public timeline compatibility only.

## Coding Code Contract — Task-Specific Obligations

### Clause: C-CC-1

**Claim:** All assigned event classes are Pydantic dataclasses with one
class-specific kind field and preserved pre-existing members.

**Evidence:** Event modules show the decorator/import swap plus one `kind`
literal on each concrete class. Existing factory/runtime/API tests passed
without production caller rewrites.

### Clause: C-CC-2

**Claim:** Serializer registry is kind-keyed, explicit-registration-only, and
raises for unknown kinds.

**Evidence:** `CaoEventSerializerRegistry._event_types_by_kind`,
`serialize()`, and `deserialize()` implement this shape.
`test_persisted_event_requires_explicit_kind_registration_after_registry_restart`
proves unregistered kind failure then success after `register_linear_cao_events()`.

### Clause: C-CC-3

**Claim:** Persistence stores the discriminator only in `cao_events.kind`.

**Evidence:** `CaoEventModel.kind` replaces the model column; `persist_cao_event()`
writes only `"kind"`; `test_new_cao_event_writes_store_kind_without_legacy_discriminator`
inspects the real table and asserts `event_type_key` is absent.

### Clause: C-CC-4

**Claim:** Read paths reconstruct by `kind`; legacy-shaped record/API
compatibility is computed rather than stored.

**Evidence:** `_record_from_model()` reads `row.kind`, calls
`deserialize_cao_event(kind, ...)`, and sets `event_type_key` via
`_public_event_type_key(type(event))`.

### Clause: C-CC-5

**Claim:** Migration creates/backfills kind, blocks unresolved legacy rows, and
drops `event_type_key`.

**Evidence:** `_migrate_ensure_cao_event_tables()` adds `kind`, backfills from
`_cao_event_kind_by_legacy_type_key()`, raises on unresolved rows, drops
`ix_cao_events_event_type_key`, and drops the legacy column.

### Clause: C-CC-6

**Claim:** Caller discovery classified every remaining `event_type_key` match.

**Evidence:** The `rg 'event_type_key' ...` discovery output is limited to
public compatibility fields, the compatibility projection helper, migration
legacy-column handling, tests asserting absence of the legacy column, legacy
fixtures, and API compatibility assertions.

### Clause: C-CC-7

**Claim:** Service ownership and public/private boundaries are explicit after
the registry/store reshape.

**Evidence:** `events/serialization.py` owns the serializer registry, consumer
functions, and public `cao_event_kind()` vocabulary helper; `clients/cao_event_store.py`
owns model/read/write behavior; `clients/database.py` continues exporting store
facade functions; private helpers remain prefixed and module-local.

## Committed Implementation Decisions

No committed implementation decisions were in force at task start.

## Committed-Decision Promotion Draft

- `CID-1`: Backend CAO event storage no longer stores `event_type_key`; when
  backend reads still expose `CaoEventRecord.event_type_key`, that value is a
  public timeline compatibility projection computed from the reconstructed event
  class, while storage and deserialization use `kind` exclusively.

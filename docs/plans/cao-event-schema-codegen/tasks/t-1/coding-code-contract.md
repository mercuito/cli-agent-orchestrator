# Coding Code Contract — t-1

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| F-CC-1 | feature-level Code Contract | The task owns backend event declarations and must add the stable instance-level `kind` discriminator to every Linear and runtime CAO event class. |
| F-CC-2 | feature-level Code Contract | The task owns the decorator swap for every Linear and runtime CAO event class. |
| F-CC-3 | feature-level Code Contract | The task owns serializer registration, serialization, and reconstruction through `kind`. |
| F-CC-6 | feature-level Code Contract | The task owns the `cao_events` storage discriminator migration and backend read paths. |
| F-CC-7 | feature-level Code Contract | The task owns backend/storage replacement-surface removal for the legacy discriminator helper, dynamic import fallback, storage column, and stdlib decorators. |
| F-CC-8 | feature-level Code Contract | The task owns backend/storage caller discovery and migration proof. |
| F-CC-9 | feature-level Code Contract | The task owns preservation of event equality and protocol attributes across persistence reconstruction. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `full-verification-required` | The task produces code changes and must run the exact Verification Command from the handoff before completion. |
| `semantic-continuity` | Existing event construction, dispatch, persistence, participant indexing, and timeline reconstruction paths are extended to use `kind` without changing their preserved behavior. |
| `no-unnecessary-duplication` | The task adds kind lookup and migration helpers that must reuse the same event registry vocabulary instead of duplicating independent mappings. |
| `respect-ownership-boundaries` | Event declarations, serialization, storage, migration, and timeline reads are owned by separate modules and must remain in their owner surfaces. |
| `centralized-vocabulary` | Persisted discriminator names and per-event kind literals become named syntax consumed by storage, serializer, migration, and tests. |
| `prefer-public-surfaces` | Cross-module consumers must use the event registration/serialization/store surfaces rather than deep private helpers where a public surface exists. |
| `readable-and-explicit` | The discriminator pivot and migration failure behavior must be visible from names, types, and control flow. |
| `service-definition-surface` | The shared serializer registry and event store model/read surface are reshaped. |
| `service-export-discipline` | Any changed serializer/store exports must be required by current callers or the assigned feature contract only. |
| `well-defined-service` | The serializer registry and event store are reshaped shared services, so owner, home, boundary, and public surface must remain explicit. |
| `migration-discipline` | Existing storage and callers move to the new authoritative `kind` shape without compatibility shims except the public API compatibility value required outside storage. |
| `no-assumed-backwards-compatibility` | The legacy storage discriminator, dynamic import fallback, and serializer helper must not remain as hidden compatibility paths. |

## Task-Specific Code Obligations

- `C-CC-1`: Each class in `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS` must be a Pydantic dataclass and declare exactly one init field named `kind` whose value is a class-specific `Literal["<provider>.<event_name>"]` default; existing non-`kind` fields, defaults, `ClassVar`s, factory behavior, and computed properties must remain intact.
- `C-CC-2`: `CaoEventSerializerRegistry` must register classes by the class `kind` literal, serialize events by returning `event.kind`, and deserialize only by looking up a registered `kind`; unknown kinds must raise `UnknownCaoEventError` with no dynamic import fallback.
- `C-CC-3`: The persistence model and write path must store the discriminator only in `cao_events.kind`; `event_type_key` must not be a SQLAlchemy model column or write-path value.
- `C-CC-4`: Storage read paths must reconstruct events by `kind` and may expose the legacy-shaped `CaoEventRecord.event_type_key` only as a computed public timeline compatibility value derived from the reconstructed event class, not from storage.
- `C-CC-5`: The CAO event migration must create `kind` for new databases, backfill legacy rows from known registered event classes, block unresolved legacy discriminator values by raising from the migration helper, and drop the legacy `event_type_key` column.
- `C-CC-6`: Caller discovery must classify every `event_type_key` match in `src/` and the assigned tests as migrated storage/serializer usage or public API compatibility surface; internal storage/serializer matches must be removed.
- `C-CC-7`: The serializer registry remains owned by `cli_agent_orchestrator.events.serialization` with public entry points `register_cao_event_serializers`, `serialize_cao_event`, `deserialize_cao_event`, and the vocabulary helper `cao_event_kind`; the event store remains owned by `cli_agent_orchestrator.clients.cao_event_store` with database-facade exports through `cli_agent_orchestrator.clients.database`. Internal helpers for instance validation, legacy migration mapping, and public compatibility projection must stay private to their owner modules.

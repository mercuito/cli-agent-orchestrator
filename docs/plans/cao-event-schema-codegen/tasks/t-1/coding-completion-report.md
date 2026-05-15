# Coding Completion Report — t-1

## Implementation Summary

Implemented the backend kinded CAO event persistence foundation for `t-1`.
Linear and runtime CAO event declarations are now Pydantic dataclasses with
class-specific `kind: Literal[...]` instance fields. The CAO serializer registry
indexes registered event classes by `kind`, serializes the storage discriminator
as `event.kind`, and raises `UnknownCaoEventError` for unregistered kinds rather
than dynamically importing module-qualified class names.

`cao_events` storage now writes a canonical `kind` column instead of
`event_type_key`. The CAO event migration creates/backfills `kind`, rejects
legacy rows whose module-qualified discriminator cannot map to a registered
Linear/runtime event class, drops the legacy `event_type_key` column, and keeps
the participant occurrence index migration intact. Read paths reconstruct from
`kind` only; `CaoEventRecord.event_type_key` remains as a computed public
timeline compatibility projection derived from the reconstructed event class,
not from storage.

Backend persistence tests now prove all `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`
round-trip through production dispatcher/store/read paths, explicit serializer
registration is required after registry restart, and legacy rows migrate through
store and timeline read surfaces.

## Plan Divergence

No material architecture divergence. One implementation detail was clarified
during verification: the assigned API baseline has an experimental local test
event that is persisted through the same backend serializer path. That fixture
was updated to the new Pydantic dataclass + `kind` declaration contract so its
existing related-events assertions keep proving the same route behavior.

## Slice-Adequacy Self-Check

The assigned Feature Code Contract slice still fits the finished
implementation:

- `F-CC-1`, `F-CC-2`: every Linear/runtime CAO event class has the required
  Pydantic dataclass declaration and kind literal.
- `F-CC-3`: serializer registration/deserialization is kind-keyed with no
  dynamic import fallback.
- `F-CC-6`, `F-CC-7`: storage uses `kind`, migrates legacy rows, and removes
  backend/storage legacy discriminator surfaces.
- `F-CC-8`: caller discovery found no remaining internal serializer/storage
  use of the legacy helper or column; remaining `event_type_key` references are
  public compatibility, legacy migration fixture, or assertions that the legacy
  column is absent.
- `F-CC-9`: persistence reconstruction equality and protocol attributes are
  preserved by the assigned verification baseline and the all-event round-trip
  proof.

The assigned Feature Test Contract slice still fits. The finished tests cover
the named baseline, the all-event kind round-trip seam, legacy migration/read
path seam, and uncovered serializer-registration characterization. No upstream
feature clause was found wrong, over-broad, or infeasible.

## Contract Boundary And Escalation Check

The implementation stayed inside the assigned backend/storage refactor
boundary. It changed the backend storage wire shape exactly where assigned:
`cao_events.event_type_key` is removed and replaced by `cao_events.kind`. It did
not change non-event API routes, frontend generated typing, or frontend callers.

The public timeline compatibility field `event_type_key` remains available on
`CaoEventRecord`, `TimelineEventRead`, and the API response model, but it is a
computed compatibility projection from the reconstructed event class. It is not
a storage discriminator, dual-write column, dynamic import fallback, or
backward-compatibility shim for backend storage.

No unsupported compatibility scaffolding, duplicate old/new storage path,
compatibility re-export, or long-lived serializer bridge was added. No upstream
escalation was required.

## Verification Result

Exact Verification Command from the handoff:

```bash
uv run pytest test/events/test_cao_event_persistence.py test/api/test_agent_identity_routes.py test/runtime/test_agent_runtime.py
```

Result: passed, 70 tests collected and 70 passed.

Final exact run after reviewer-requested implementation and artifact revisions:
passed, 70 tests collected and 70 passed.

Focused red/green proof:

- Initial focused run of `uv run pytest test/events/test_cao_event_persistence.py -q`
  failed on missing `kind` payload/storage, dynamic-import reconstruction, and
  migration backfill/drop-column gaps.
- After implementation, the focused persistence suite passed.
- After API fixture adaptation and formatting, the exact Verification Command
  passed.

## Spec Sync

No upstream feature artifact required amendment. The implementation follows the
assigned Code/Test slices as issued. The committed-decision promotion proposed
in the Code Contract Defence was promoted to
`feature-committed-implementation-decisions.md` as `CID-1`.

## Files Changed

- `src/cli_agent_orchestrator/runtime/events.py`
- `src/cli_agent_orchestrator/linear/workspace_events.py`
- `src/cli_agent_orchestrator/events/serialization.py`
- `src/cli_agent_orchestrator/clients/cao_event_store.py`
- `src/cli_agent_orchestrator/clients/database_migrations.py`
- `test/events/test_cao_event_persistence.py`
- `test/api/test_agent_identity_routes.py`
- `docs/plans/cao-event-schema-codegen/tasks/t-1/coding-code-contract.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-1/coding-test-contract.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-1/coding-implementation-plan.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-1/coding-completion-report.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-1/code-contract-defence.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-1/test-contract-defence.md`

## Final Contract Review Outcomes

- `coding-code-contract-reviewer`: approved the Coding Code Contract criteria
  selection, Code Contract Defence, and landed production code for the assigned
  t-1 code slice. Changes made during review: removed implicit serializer
  registration on serialize, removed inapplicable standing-decision criterion
  selection, added `well-defined-service`/`C-CC-7`, explicitly declared
  `cao_event_kind()` as the public serializer vocabulary helper, and added
  constructor discovery evidence for `F-CC-8`.
- `coding-test-contract-reviewer`: approved the Coding Test Contract criteria
  selection, Test Contract Defence, and landed tests/proof artifacts for the
  assigned t-1 test slice. Changes made during review: extended migrated-row
  proof across all store list read paths and timeline service, and added the
  applicable `inspectable-authored-inputs` and `test-artifact-containment`
  criteria selections and evidence.

## Observations

Pydantic dataclasses preserved the existing dataclass equality, `replace()`,
`dataclasses.fields()`, factory defaults, and NewType reconstruction behavior
needed by the assigned backend tests.

The legacy migration can avoid a full table rebuild because SQLite supports
`ALTER TABLE DROP COLUMN` in the test environment; this preserves participant
foreign-key relationships while removing the legacy discriminator column.

## Hiccups

- The first exact verification run failed because `_ExperimentalAuditEvent` in
  `test/api/test_agent_identity_routes.py` was a persisted local dataclass
  without a `kind` literal. The fixture was updated to the same declaration
  contract required of persisted events, preserving the route assertions.
- The prior serializer-restart test expected dynamic import reconstruction.
  It was retargeted to prove reconstruction after explicit normal registration,
  and a separate negative assertion now proves unregistered kinds fail.

## Optimization Opportunities

- Future event-schema/codegen work may benefit from a shared test helper that
  constructs one valid instance per registered CAO event class.
- If CAO must support SQLite versions without `ALTER TABLE DROP COLUMN`, the
  migration should grow a table-rebuild fallback with explicit dependent-FK
  handling.

## Risks And Known Issues

No known issue remains within the assigned verification boundary. The only
noted residual risk is older SQLite compatibility for dropping a column, which
is outside the current test environment and not evidenced by the handoff
verification command.

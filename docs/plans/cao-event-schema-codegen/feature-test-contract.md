# Feature Test Contract — CAO Event Schema Codegen

Cross-task proof obligations for the CAO Event Schema Codegen refactor.
This is pure refactor work; the universal `test-validity-preserved`
criterion governs proof integrity at the coding altitude, and the
feature-level clauses below name the cross-task preservation baseline
and the coordinated proof shapes that no single task can satisfy alone.

## Applicable Feature-Level Test Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [stable-test-clause-ids](../../planning/methodology/criteria/feature-test-contract/stable-test-clause-ids.md) | Always applies; every clause below carries a stable `F-TC-<n>` ID for slicing in `feature-tasks.md`, handoffs, and Test Contract Defences. |

## Standing Proof Shapes

- **F-TC-1 — Preservation baseline.** The existing tests in
  `test/events/test_cao_event_persistence.py`,
  `test/api/test_agent_identity_routes.py`,
  `test/runtime/test_agent_runtime.py`, and the existing frontend
  timeline component tests under `web/src/test/` (notably
  `agent-identity-timeline-panel.test.tsx`, `agent-panel-deeplink.test.tsx`,
  and `api.test.ts`) form the preservation baseline for this refactor.
  Every task in this feature must leave these tests passing at the
  task's Verification Command boundary. New assertions added by a task
  must not weaken or replace any existing assertion's original target
  behavior; assertion edits to existing tests require escalation rather
  than local absorption.

- **F-TC-2 — Round-trip reconstruction is proven across the
  discriminator pivot.** The reconstruction tests
  `test_persistent_dispatcher_persists_and_reconstructs_linear_event`
  and `test_persisted_event_reconstructs_after_serializer_registry_restart`
  (in `test/events/test_cao_event_persistence.py`) continue to
  demonstrate that persisted events rehydrate into typed instances equal
  to the originals under dataclass equality. After the serializer's
  discriminator switches from `f"{module}.{qualname}"` to `kind`, these
  tests prove reconstruction by `kind` lookup; the existing assertions
  on `isinstance(record.event, …)` and `record.event == original` are
  preserved without modification beyond fixture changes required by the
  new field. The cold-registry variant continues to demonstrate that a
  fresh process can rehydrate persisted events purely from the stored
  discriminator and JSON payload.

- **F-TC-3 — OpenAPI schema asserts the discriminated event union.**
  A backend test, added by the task that lands `F-CC-4`, inspects the
  FastAPI application's `app.openapi()` output and asserts the affected
  timeline event-data schemas are JSON Schema `oneOf` constructs with a
  `discriminator` keyed on `kind`, with one branch per member of
  `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`. This test guards against
  silent drift between the registered event set and the published API
  contract; subsequent tasks that add or rename event classes must keep
  this assertion passing.

- **F-TC-4 — Persistence migration is proven complete.** A backend test
  demonstrates that after the migration task lands, every row in
  `cao_events` carries a populated `kind` value, the `event_type_key`
  column is no longer present in the schema, and `get_cao_event` /
  `list_cao_events_*` reconstruct typed event instances via `kind`
  lookup exclusively. The test set contains no assertion that exercises
  reading rows by the legacy `event_type_key` discriminator (such
  assertions are removed alongside the column they exercise, per F-CC-7).

## Feature-Specific Proof Obligations

- **F-TC-5 — Characterization tests for uncovered preserved behavior.**
  When research at task altitude surfaces preexisting behavior in this
  refactor's affected surfaces (per the scope preamble of
  `feature-code-contract.md`) that the F-TC-1 baseline does not assert,
  the task adds characterization tests describing that preexisting
  behavior before changing the surface. Characterization assertions
  describe what the system already does; they do not lock in behavior
  the system did not previously exhibit. New assertions that would
  encode novel behavior belong on the behavior-changing path and are
  out of scope for this refactor.

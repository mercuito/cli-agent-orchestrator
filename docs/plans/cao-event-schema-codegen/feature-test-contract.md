# Feature Test Contract — CAO Event Schema Codegen

Cross-task proof obligations for the CAO Event Schema Codegen refactor.
This is pure refactor work; the universal `test-validity-preserved`
criterion governs proof integrity at the coding altitude, and the
feature-level clauses below name the preservation baseline and the
cross-component seams whose proof spans tasks. Specific test instances
are a task-level concern, recorded in each task's Coding Test Contract.

## Applicable Feature-Level Test Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [stable-test-clause-ids](../../planning/methodology/criteria/feature-test-contract/stable-test-clause-ids.md) | Always applies; every clause below carries a stable `F-TC-<n>` ID for slicing in `feature-tasks.md`, handoffs, and Test Contract Defences. |
| [proof-shape-not-test-instance](../../planning/methodology/criteria/feature-test-contract/proof-shape-not-test-instance.md) | The clauses below describe proof shape (preservation baseline, seam-crossing scenarios, characterization); they do not enumerate specific tests, which are decided at task altitude. |
| [seam-proof-crosses-components](../../planning/methodology/criteria/feature-test-contract/seam-proof-crosses-components.md) | The refactor introduces multiple cross-component seams (kind round-trip, generated-schema correspondence, migration/read path) where per-component unit tests would mask failures the integration only reveals. |
| [preservation-baseline-discoverable](../../planning/methodology/criteria/feature-test-contract/preservation-baseline-discoverable.md) | This is pure refactor work and the task-specific preservation baseline clauses name baselines enumerated by file path. |

## Standing Proof Shapes

- **F-TC-1 — Kinded persistence preservation baseline.** The
  preservation baseline for the backend persistence foundation task is:

  - `test/events/test_cao_event_persistence.py`
  - `test/api/test_agent_identity_routes.py`
  - `test/runtime/test_agent_runtime.py`

  The task owning this slice leaves these tests passing at its
  Verification Command boundary. The universal
  `test-validity-preserved` criterion governs at the coding altitude:
  assertions in these files may not weaken or replace any existing
  assertion's original target behavior. Baseline additions, removals, or
  splits during the feature amend this contract; tasks do not extend the
  baseline silently.

- **F-TC-2 — Kind round-trip seam is proven end-to-end.** Proof at the
  event-class ↔ serializer ↔ storage ↔ deserializer seam requires a
  scenario shape that, for each member of
  `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`, constructs a real event
  instance, persists it through the production write path,
  reconstructs it through the production read path, and equality-
  asserts the reconstructed instance against the original under
  dataclass equality.

  Per-stage unit tests of the serializer or the storage layer in
  isolation do not satisfy this clause, because seam failures (a
  `kind` literal mismatch, a missing registration, a default-value
  collision between two events) only surface when the stages run
  together against the production code paths.

- **F-TC-3 — Backend event schema emission seam is proven.** Proof at
  the registered-events ↔ generated-schema seam requires that, for every
  member of `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`, the backend schema
  document used for frontend event-payload codegen carries exactly one
  branch keyed on its `kind` literal. Inspecting the production schema
  generation path satisfies the obligation; per-model unit tests that do
  not exercise schema generation do not satisfy it, because the seam
  concern is whether registered events flow through to the schema
  artifact consumed by codegen.

- **F-TC-4 — Codegen-freshness seam is proven.** Proof at the
  generated-schema ↔ generated-TS-types seam requires that the
  schema-derived TypeScript declarations consumed by the frontend carry a
  branch for every member of
  `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`, each branch matching its
  corresponding `kind` literal. A codegen-freshness check that re-
  runs `openapi-typescript` against the generated schema document and
  compares against the committed generated file satisfies the
  obligation. Inspecting the committed generated file without re-
  running the generator does not satisfy this clause, because the
  seam concern is whether the committed file remains in sync with the
  generated schema rather than whether it once was. F-TC-3 and F-TC-4
  together close the schema-correspondence seam end-to-end; satisfying
  one without the other leaves the other half of the seam unproven.

- **F-TC-5 — Migration ↔ read-path seam is proven over pre-existing
  rows.** Proof at the legacy-storage ↔ migration ↔ production-read-
  path seam requires a scenario shape that seeds `cao_events` with
  rows matching the pre-migration schema (legacy `event_type_key`
  populated, `kind` absent or empty), runs the production migration
  path, and asserts that every seeded row reconstructs through the
  production read path (`get_cao_event`, `list_cao_events_*`, and
  `agent_identity_timeline` reconstruction) into a typed instance
  equal under dataclass equality to a control instance built from the
  same source fixture.

  A scenario that constructs post-migration rows directly and reads
  them back does not satisfy this clause, because the seam concern is
  whether the migration translates legacy rows correctly — not whether
  post-migration rows read back.

  After the migration task lands, the proof set contains no assertion
  path that reads storage rows by the legacy `event_type_key` discriminator
  (such assertions are removed alongside the column they exercise,
  per F-CC-7).

- **F-TC-7 — Frontend codegen preservation baseline.** The preservation
  baseline for the generated event payload types task is:

  - `web/src/test/agent-identity-timeline-panel.test.tsx`
  - `web/src/test/agent-panel-deeplink.test.tsx`
  - `web/src/test/api.test.ts`

  The task owning this slice leaves these tests passing at its
  Verification Command boundary. The universal `test-validity-preserved`
  criterion governs at the coding altitude: assertions in these files
  may not weaken or replace any existing assertion's original target
  behavior. Baseline additions, removals, or splits during the feature
  amend this contract; tasks do not extend the baseline silently.

- **F-TC-8 — Final public compatibility preservation baseline.** The
  final compatibility sweep proves the full preservation baseline after
  the backend persistence and frontend codegen tasks have landed. The
  full baseline is the union of:

  - `test/events/test_cao_event_persistence.py`
  - `test/api/test_agent_identity_routes.py`
  - `test/runtime/test_agent_runtime.py`
  - `web/src/test/agent-identity-timeline-panel.test.tsx`
  - `web/src/test/agent-panel-deeplink.test.tsx`
  - `web/src/test/api.test.ts`

  The task owning this slice leaves the full baseline passing at its
  Verification Command boundary and verifies that remaining
  `event_type_key` observations are public API compatibility behavior,
  not storage/read-path dependence on the retired discriminator column.

## Feature-Specific Proof Obligations

- **F-TC-6 — Backend/storage characterization for uncovered preserved
  behavior.** When research in the backend persistence foundation task
  surfaces preexisting behavior in backend event declaration, serializer,
  storage, or read-path surfaces that the F-TC-1 baseline does not
  assert, that task adds characterization tests describing the
  preexisting behavior before changing the surface. Characterization
  assertions describe what the system already does; they do not lock in
  behavior the system did not previously exhibit.

- **F-TC-9 — Frontend/codegen characterization for uncovered preserved
  behavior.** When research in the generated event payload types task
  surfaces preexisting behavior in frontend event-view typing, generated
  event constants, or event-view registry surfaces that the F-TC-7
  baseline does not assert, that task adds characterization tests
  describing the preexisting behavior before changing the surface.
  Characterization assertions describe what the system already does; they
  do not lock in behavior the system did not previously exhibit.

- **F-TC-10 — Public compatibility characterization for uncovered
  preserved behavior.** When research in the final compatibility sweep
  surfaces preexisting behavior in the public timeline API response
  envelope or remaining frontend consumption of that envelope that the
  F-TC-8 baseline does not assert, that task adds characterization tests
  describing the preexisting behavior before changing the surface.
  Characterization assertions describe what the system already does; they
  do not lock in behavior the system did not previously exhibit. New
  assertions that would encode novel behavior belong on the
  behavior-changing path and are out of scope for this refactor.

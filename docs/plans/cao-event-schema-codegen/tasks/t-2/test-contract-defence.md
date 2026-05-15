# Test Contract Defence — t-2

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Always; every claim below cites concrete proof artifacts or command results. |

## Feature-Level Test Contract

### Clause: F-TC-3

**Claim:** Backend event schema emission is proven for every registered Linear and runtime CAO event kind.

**Evidence:** `scripts/generate_cao_event_payload_types.py` builds `CaoEventPayload` from `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS` and `_assert_schema_covers_registered_events()` compares the discriminator mapping against `{cao_event_kind(event_type) for event_type in CAO_EVENT_TYPES}` while requiring one `oneOf` branch per expected kind. `npm run check:event-types` exercises this path.

### Clause: F-TC-4

**Claim:** Codegen freshness is proven by re-running `openapi-typescript` and comparing against committed generated output.

**Evidence:** `npm run check:event-types` re-runs the generator in `--check` mode, which writes transient schema/candidate files, invokes `openapi-typescript`, and compares the candidate TypeScript output with `web/src/generated/caoEventPayloadTypes.ts` without rewriting it. The command passed after implementation.

### Clause: F-TC-7

**Claim:** The assigned frontend preservation baseline remains passing without weakened assertions.

**Evidence:** Exact Verification Command passed: `cd web && npm test -- agent-identity-timeline-panel.test.tsx agent-panel-deeplink.test.tsx api.test.ts`. Vitest reported 3 files and 48 tests passing. Test updates changed only generated-module imports; existing assertions for fallback events, known rows, terminal focus, deep links, and API typed event data remain.

### Clause: F-TC-9

**Claim:** Frontend/codegen preserved behavior surfaced during research is characterized.

**Evidence:** The existing F-TC-7 baseline already characterized the relevant behavior: known generated public event keys dispatch to Linear mention/runtime views; unknown event keys fall back; API wrapper preserves typed `event_data`. No additional uncovered preserved behavior was found.

## Coding Test Contract Criteria

### Criterion: test-validity-preserved

**Claim:** Existing tests continue to prove their original target behavior.

**Evidence:** Test bodies keep their original behavior assertions. Import-only migrations point to `caoEventPayloadTypes.ts`. The exact Verification Command passed.

### Criterion: given-when-then-test-structure

**Claim:** Multi-step proof remains readable through command and test phases.

**Evidence:** Codegen proof has generate/check/compare phases in the generator; frontend tests retain setup fixtures, render/API action, and assertions.

### Criterion: public-boundary-proof

**Claim:** The changed command and generated export boundaries are exercised directly.

**Evidence:** `pretest` invokes `npm run check:event-types` and `tsc --noEmit`; Vitest imports generated constants through the same `caoEventPayloadTypes.ts` module used by production views.

### Criterion: real-surface-proof-discipline

**Claim:** Proof exercises real integration surfaces rather than mocks.

**Evidence:** `check:event-types` imports real backend event declarations and runs the real `openapi-typescript` CLI. Vitest renders real frontend components and registry module discovery.

### Criterion: inspectable-authored-inputs

**Claim:** Behavior-relevant frontend payload examples remain visible.

**Evidence:** Authored timeline payloads stay inline in `agent-identity-timeline-panel.test.tsx`, `agent-panel-deeplink.test.tsx`, and `api.test.ts`.

### Criterion: setup-invariant-ownership

**Claim:** Schema branch invariants fail at the codegen owner boundary.

**Evidence:** `_assert_schema_covers_registered_events()` checks missing/extra discriminator kinds and branch count before TypeScript output is accepted.

### Criterion: test-through-owner-surfaces

**Claim:** Schema/codegen proof goes through owner surfaces.

**Evidence:** The check command calls the generator owner surface and exported backend event tuples; frontend tests import from the generated module rather than duplicating backend discovery.

### Criterion: test-artifact-containment

**Claim:** Transient artifacts are contained and cleaned up.

**Evidence:** The generator uses `tempfile.TemporaryDirectory(prefix="cao-event-payload-types-", dir=REPO_ROOT)` for schema/candidate artifacts. Post-run check `find . -maxdepth 1 -type d -name 'cao-event-payload-types-*' -print` produced no output.

### Criterion: verification-scope-discipline

**Claim:** Focused proof and broader handoff verification are both named and run.

**Evidence:** Focused proof: `npm run check:event-types` and `npx tsc --noEmit`. Broader required proof: exact Verification Command passed.

## Coding Test Contract Obligations

### Clause: C-TC-1

**Claim:** Codegen check validates schema branch coverage and committed-file freshness without rewriting in check mode.

**Evidence:** `--check` mode generates a candidate through `openapi-typescript`, validates branch coverage in `_assert_schema_covers_registered_events()`, compares to `OUTPUT_PATH`, and returns nonzero on mismatch/missing output. The initial red run failed on the missing generated file; the final check passed.

### Clause: C-TC-2

**Claim:** The F-TC-7 tests remain preserved after import migration.

**Evidence:** `agent-identity-timeline-panel.test.tsx` and `agent-panel-deeplink.test.tsx` import constants from `caoEventPayloadTypes.ts`; assertions were not weakened. `api.test.ts` remains unchanged for API envelope/data assertions.

### Clause: C-TC-3

**Claim:** Generated compatibility constants still drive known-view dispatch while unknown keys use fallback.

**Evidence:** `agent-identity-timeline-panel.test.tsx` renders known Linear/runtime events using generated constants and still asserts unknown audit fallback facts and related fallback behavior.

### Clause: C-TC-4

**Claim:** Type-level proof checks known views against generated payload declarations.

**Evidence:** `pretest` runs `tsc --noEmit`. `knownCaoEventViews.tsx` declares each known view as `KnownTimelineEventView<typeof GENERATED_CONSTANT>` and reads generated payload fields through typed `event.event_data`.

### Clause: C-TC-5

**Claim:** Freshness artifacts are temporary and removed.

**Evidence:** The generator writes schema/candidate files only inside `TemporaryDirectory`; the post-run `find` check found no leftover `cao-event-payload-types-*` directories.

# Coding Completion Report — t-2

## Implementation Summary

Replaced the retired frontend event-key generator with
`scripts/generate_cao_event_payload_types.py`. The new generator builds a
backend-derived OpenAPI schema from `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`,
validates that `CaoEventPayload` has exactly one discriminator branch per
registered `kind`, runs `openapi-typescript`, and writes
`web/src/generated/caoEventPayloadTypes.ts`.

The generated TypeScript module now owns both schema-generated payload types
and public timeline API compatibility constants. `web/package.json` keeps the
existing `generate:event-types` command name, adds `check:event-types`, and
runs codegen freshness plus `tsc --noEmit` before frontend tests.

Known timeline views now use generated payload typing through
`KnownTimelineEventView` and `CaoEventPayloadForTypeKey<T>`. The public
timeline API envelope remains unchanged in frontend API types:
`event_type_key: string` and object-shaped `event_data` are preserved.

## Plan Divergence

No material implementation divergence. The implementation followed the
approved plan. Two plan revisions were recorded before/around implementation:
isolated temporary schema/candidate artifacts and explicit caller discovery,
then post-implementation criteria selection for generated export and command
boundary proof.

## Slice-Adequacy Self-Check

The assigned slices still fit the finished implementation.

- F-CC-5, F-CC-10, and F-CC-11 remain the correct code slice: the task replaced
  frontend codegen, removed retired artifacts, and migrated assigned frontend
  callers.
- F-TC-3, F-TC-4, F-TC-7, and F-TC-9 remain the correct test slice: proof
  covers schema emission, codegen freshness, the assigned frontend baseline,
  and the known/fallback view characterization already present in that baseline.
- No Behavioral Contract slice applies; this remained pure refactor work.

No upstream contract or handoff clause was invalidated.

## Contract Boundary And Escalation Check

The implementation stayed within the assigned preservation boundary. It changed
developer command wiring and generated frontend artifacts, both explicitly
owned by t-2. It did not change backend storage/read paths, API response models,
or route outputs.

The remaining `event_type_key` uses in `web/src` are public timeline API
compatibility observations or generated compatibility constants. The task did
not add storage/serializer compatibility scaffolding, dual-shape storage, legacy
module re-exports, or wrappers for the retired generator/module. CID-1 remains
intact: generated public constants represent the public timeline envelope, not a
backend storage discriminator.

No assigned clause was wrong, over-broad, infeasible, or incompatible with the
actual system boundary. No upstream escalation was required.

## Verification Result

Exact Verification Command from the handoff:

```bash
cd web && npm test -- agent-identity-timeline-panel.test.tsx agent-panel-deeplink.test.tsx api.test.ts
```

Result: passed. `pretest` ran `npm run check:event-types && tsc --noEmit`, then
Vitest reported 3 files and 48 tests passing.

Additional focused proof:

- Initial red check: `npm run check:event-types` failed because
  `web/src/generated/caoEventPayloadTypes.ts` was missing.
- Freshness/type proof after implementation:
  `npm run generate:event-types && npm run check:event-types && npx tsc --noEmit`
  passed.
- Artifact containment check: `find . -maxdepth 1 -type d -name 'cao-event-payload-types-*' -print`
  produced no output after the check command exited.

## Spec Sync

No upstream feature artifact needed amendment. Task-level contracts were updated
during the required criteria revisit to select `service-export-discipline` and
`public-boundary-proof`, matching the finished generated export and command
surface changes.

## Files Changed

- `scripts/generate_cao_event_payload_types.py` added.
- `scripts/generate_cao_event_type_keys.py` removed.
- `web/src/generated/caoEventPayloadTypes.ts` added.
- `web/src/generated/caoEventTypeKeys.ts` removed.
- `web/package.json` and `web/package-lock.json` updated.
- `web/src/components/timelineEventViews.tsx` updated.
- `web/src/components/timelineEventViews/knownCaoEventViews.tsx` updated.
- `web/src/test/agent-identity-timeline-panel.test.tsx` updated.
- `web/src/test/agent-panel-deeplink.test.tsx` updated.
- Task artifacts under `docs/plans/cao-event-schema-codegen/tasks/t-2/` added or updated.

## Observations

Pydantic's `TypeAdapter` produced the required discriminator mapping once the
event union was built from the exported backend event tuples. `openapi-typescript`
generated usable discriminated payload types without changing the public API
timeline envelope.

## Hiccups

- The first generated payload map used computed type keys that TypeScript
  rejected. The generator now emits string-literal keys in
  `CaoEventPayloadByTypeKey`.
- The first temp-file implementation used the host temp directory. It now uses a
  repo-local isolated temporary directory and removes it before exit.

## Optimization Opportunities

The generated TypeScript file is large because it includes every schema emitted
by the event payload union. A future task could post-process or split generated
types only if the feature contract authorizes changing the generated artifact
shape.

## Risks And Known Issues

No known unresolved issues in the assigned t-2 scope. `npm install` reported one
moderate npm audit finding in the frontend dependency tree; this task did not
run `npm audit fix` because dependency remediation is outside the assigned
slice.

## Final Review Outcomes

| Reviewer role | Contract reviewed | Approval status | Changes made because of review |
|---------------|-------------------|-----------------|--------------------------------|
| `coding-test-contract-reviewer` | Test Contract Defence | Approved | None; reviewer approved the test criteria selection, feature test slice evidence, check-mode proof, temp artifact containment, and exact verification evidence. |
| `coding-code-contract-reviewer` | Code Contract Defence | Approved after revision | Revised `code-contract-defence.md` to enumerate and classify every contracted caller-discovery match for F-CC-11/C-CC-5, including frontend API/panel/test/generated matches and package command/dependency matches. |

Committed-decision promotion: CID-2 was promoted to
`docs/plans/cao-event-schema-codegen/feature-committed-implementation-decisions.md`
after code contract review approval.

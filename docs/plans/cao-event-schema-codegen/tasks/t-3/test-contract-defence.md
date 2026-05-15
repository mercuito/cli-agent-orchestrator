# Test Contract Defence — t-3

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Always; every proof claim cites concrete tests, fixtures, or command output. |

## Feature-Level Test Contract

### Clause: F-TC-8

**Claim:** The full final public compatibility preservation baseline passed after `t-1` and `t-2`.

**Evidence:** The exact Verification Command passed. Backend result: `test/events/test_cao_event_persistence.py`, `test/api/test_agent_identity_routes.py`, and `test/runtime/test_agent_runtime.py` collected 71 tests and all passed. Frontend result: `web` pretest passed `check:event-types` and `tsc --noEmit`; `agent-identity-timeline-panel.test.tsx`, `agent-panel-deeplink.test.tsx`, and `api.test.ts` ran 48 tests and all passed.

### Clause: F-TC-10

**Claim:** Uncovered public timeline API schema compatibility is now characterized.

**Evidence:** `test_agent_identity_timeline_openapi_preserves_public_event_envelope` was added to `test/api/test_agent_identity_routes.py`. It invokes the public `/openapi.json` route through the existing API test client and asserts `event_type_key` remains a required string, `event_data` remains an object with `additionalProperties: true`, timeline and related-event response schemas reference the shared timeline event response schema, and the nested related-event causation schema carries the same shared event response for `direct_cause` and `direct_effects`.

## Coding Test Contract Criteria

### Criterion: test-validity-preserved

**Claim:** Existing baseline assertions were not weakened.

**Evidence:** The task added one new test and did not remove or relax existing assertions. The full backend/frontend preservation command passed.

### Criterion: public-boundary-proof

**Claim:** Public API compatibility is proven at the actual public boundary.

**Evidence:** The new characterization test calls `/openapi.json` through `client.get()` rather than inspecting `AgentIdentityTimelineEventResponse` internals directly.

### Criterion: real-surface-proof-discipline

**Claim:** Proof exercises real integration surfaces.

**Evidence:** Backend route tests use the FastAPI test client and production route/model registration. Frontend verification renders real components, imports generated modules, runs the generated-type freshness check, and type-checks with `tsc --noEmit`.

### Criterion: test-through-owner-surfaces

**Claim:** Tests go through owner surfaces for API and generated-type behavior.

**Evidence:** API schema proof uses the FastAPI application OpenAPI owner surface. Generated frontend proof goes through `npm run check:event-types`, which invokes the generator owner command; component tests consume the generated module rather than duplicating event discovery.

### Criterion: verification-scope-discipline

**Claim:** Focused proof and broader verification were both run.

**Evidence:** Focused proof passed with `uv run pytest test/api/test_agent_identity_routes.py -q -k openapi_preserves_public_event_envelope`. Broader proof passed with the exact handoff Verification Command.

## Coding Test Contract Obligations

### Clause: C-TC-1

**Claim:** The full preservation baseline remains intact.

**Evidence:** Existing tests in all six baseline files passed as part of the exact Verification Command. No existing assertion was weakened or removed.

### Clause: C-TC-2

**Claim:** Focused route schema proof covers `event_type_key` and object-shaped `event_data`.

**Evidence:** The new OpenAPI test asserts those properties on `AgentIdentityTimelineEventResponse`, asserts timeline and related-event response schemas reference that response schema, and asserts the related-event causation envelope uses the same response schema for `direct_cause` and `direct_effects`.

### Clause: C-TC-3

**Claim:** Unknown/public frontend fixture keys remain compatibility/fallback proof, not generated known constants.

**Evidence:** Existing frontend tests still use unknown literals such as `cao.experimental.AuditEvent` to prove fallback rendering, while known Linear/runtime event fixtures use generated constants from `caoEventPayloadTypes.ts`. The frontend baseline passed.

### Clause: C-TC-4

**Claim:** The exact Verification Command passed after the test change.

**Evidence:** The command completed successfully with 71 backend tests passing and 48 frontend tests passing after `check:event-types` and `tsc --noEmit`.

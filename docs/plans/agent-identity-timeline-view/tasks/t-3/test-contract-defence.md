# Test Contract Defence — t-3

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Always applies; proof-quality claims must point to concrete test code and command output. |

## Feature-Level Test Contract

### Clause: F-TC-3

**Claim:** Frontend proof demonstrates that a newly recorded Aria-involving event appears in the watched identity timeline without reload, and that a newly recorded non-participant workspace event does not appear.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:153` renders `AgentIdentityTimelinePanel` once; `web/src/test/agent-identity-timeline-panel.test.tsx:177` advances the poll interval; `web/src/test/agent-identity-timeline-panel.test.tsx:181` asserts the new Aria event is visible; `web/src/test/agent-identity-timeline-panel.test.tsx:188` asserts the non-participant workspace event remains absent.

## Coding Test Contract

### Criteria: `test-validity-preserved`

**Claim:** Existing tests continue to validate their previous target behaviors.

**Evidence:** Full web test suite passed with `93 passed`; existing identity timeline tests for roster load, identity switching, related events, empty state, and unreachable state remain in `web/src/test/agent-identity-timeline-panel.test.tsx` and passed unchanged.

### Criteria: `given-when-then-test-structure`

**Claim:** The live-refresh test exposes setup, action, and observable outcome phases.

**Evidence:** Given/setup: `web/src/test/agent-identity-timeline-panel.test.tsx:154` uses fake timers and `web/src/test/agent-identity-timeline-panel.test.tsx:156` prepares API responses. When/action: `web/src/test/agent-identity-timeline-panel.test.tsx:170` renders the panel and `web/src/test/agent-identity-timeline-panel.test.tsx:177` advances the poll. Then/assertions: `web/src/test/agent-identity-timeline-panel.test.tsx:181` through `web/src/test/agent-identity-timeline-panel.test.tsx:188`.

### Criteria: `public-boundary-proof`

**Claim:** The proof exercises the dashboard component boundary a real operator uses rather than a lower-level polling helper.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:170` renders `AgentIdentityTimelinePanel`; `web/src/test/agent-identity-timeline-panel.test.tsx:174` reads the rendered `identity-timeline`; `web/src/test/agent-identity-timeline-panel.test.tsx:181` asserts the refreshed event is visible in the rendered UI.

### Criteria: `setup-invariant-ownership`

**Claim:** Fixture validity remains owned by existing fixture helpers and setup data, not by repeated behavior assertions.

**Evidence:** The new `liveMention` fixture is created through the existing `event(...)` helper at `web/src/test/agent-identity-timeline-panel.test.tsx:83`; the test asserts live refresh outcomes rather than reasserting every fixture field.

### Criteria: `reusable-test-state`

**Claim:** The new proof reuses existing identity and event fixture state.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:156` reuses the existing `timelines` map and only adds the behavior-specific `liveMention` row to the later Aria response.

### Criteria: `test-through-owner-surfaces`

**Claim:** The test exercises the component through its public API helper boundary rather than duplicating production internals.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:156` mocks `api.getAgentIdentityTimeline`, the owner helper consumed by the component; the test does not call component internals or implement client-side participant filtering.

### Criteria: `test-file-organization`

**Claim:** The new scenario stays in the behavior-grouped identity timeline component test file.

**Evidence:** The test is placed inside `describe('AgentIdentityTimelinePanel')` at `web/src/test/agent-identity-timeline-panel.test.tsx:116`, adjacent to the other identity timeline behavior tests.

### Criteria: `verification-scope-discipline`

**Claim:** Focused proof and broad verification were both run.

**Evidence:** Focused run `npm test -- --run src/test/agent-identity-timeline-panel.test.tsx` passed with 7 tests. Exact Verification Command passed:

```bash
uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py && cd web && npm test -- --run && npm run build
```

### Clause: C-TC-1

**Claim:** Focused proof shows a later Aria-involving event appears after polling without remounting or reopening the identity view.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:170` renders once; `web/src/test/agent-identity-timeline-panel.test.tsx:177` advances the poll interval; `web/src/test/agent-identity-timeline-panel.test.tsx:181` asserts `linear:agent_mentioned:live` appears.

### Clause: C-TC-2

**Claim:** Focused proof shows a newly recorded non-participant workspace event remains absent from Aria's watched timeline after refresh.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:164` models the refreshed identity timeline response without the workspace event, and `web/src/test/agent-identity-timeline-panel.test.tsx:188` asserts `workspace:context_refresh:non-participant` is absent after polling.

### Clause: C-TC-3

**Claim:** Proof uses mocked responses only at the API helper boundary and does not encode participant filtering logic.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:156` mocks `api.getAgentIdentityTimeline`; no filtering function or body-inspection logic is added to the test.

### Clause: C-TC-4

**Claim:** The exact handoff Verification Command ran successfully before completion.

**Evidence:** The command completed successfully with Python tests passing, Vitest passing, and the frontend production build succeeding.

# Test Contract Defence — t-2

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [claim-evidence-verifiability](../../../../planning/methodology/criteria/coding-test-contract-defence/claim-evidence-verifiability.md) | Every proof-quality claim must be checkable against concrete tests, fixtures, or command output. |

## Feature-Level Test Contract

### Clause: `F-TC-2`

**Claim:** Frontend proof uses existing Vitest and React Testing Library dashboard patterns with mocked API responses to demonstrate the assigned roster, identity view, timeline, related-event, broadcast, and empty-state behavior.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx` imports React Testing Library utilities at line `2`, spies on `api` methods at lines `112` through `118`, and covers roster/timeline, selection, related expansion, stale related-cache protection, empty/error states, and broadcast viewpoint scenarios. `web/src/test/agent-panel-deeplink.test.tsx:143` groups and renders `AgentPanel` to prove the identity timeline panel appears through the Agents boundary. `web/src/test/api.test.ts:141` through `web/src/test/api.test.ts:218` covers frontend API wrapper route paths.

## Coding Test Contract Criteria

### Criterion: `test-validity-preserved`

**Claim:** Existing frontend tests still validate their target behavior.

**Evidence:** The exact Verification Command ran all frontend tests: `92` tests passed across `6` files, including existing `components`, `store`, `terminal-view`, and `agent-panel-deeplink` tests.

### Criterion: `given-when-then-test-structure`

**Claim:** Multi-step component tests keep setup, action, and assertions identifiable.

**Evidence:** The test file defines inspectable identities/events first, sets API spies in `beforeEach`, then leaf tests render, click/select/expand, and assert UI outcomes. Examples: selection action at `web/src/test/agent-identity-timeline-panel.test.tsx:146` and assertions at lines `148` through `155`.

### Criterion: `public-boundary-proof`

**Claim:** API wrapper and user-visible component boundaries are tested directly.

**Evidence:** `web/src/test/api.test.ts:141` invokes `api.listAgentIdentities`; `web/src/test/api.test.ts:162` invokes `api.getAgentIdentityTimeline`; `web/src/test/api.test.ts:187` invokes `api.getAgentIdentityRelatedEvents`. The separately named `identity timeline boundary` group in `web/src/test/agent-panel-deeplink.test.tsx:143` renders the public `AgentPanel` boundary and asserts the identity timeline panel appears through it.

### Criterion: `inspectable-authored-inputs`

**Claim:** Behavior-relevant mocked identities, events, roles, and envelope IDs are visible from the test file.

**Evidence:** Authored identities are declared in `web/src/test/agent-identity-timeline-panel.test.tsx:45` through `web/src/test/agent-identity-timeline-panel.test.tsx:52`; authored timeline events and role/correlation/causation values are declared in lines `54` through `82`; the non-participant workspace event ID is explicit at line `83`.

### Criterion: `setup-invariant-ownership`

**Claim:** Valid repeated identity/event setup is owned by helpers and `beforeEach`, while leaf tests assert behavior.

**Evidence:** Helper functions `identity(...)` and `event(...)` build valid mocked API shapes at `web/src/test/agent-identity-timeline-panel.test.tsx:6` and `web/src/test/agent-identity-timeline-panel.test.tsx:24`. `beforeEach` wires valid API responses at lines `110` through `118`.

### Criterion: `reusable-test-state`

**Claim:** Repeated roster/timeline/related state is named and reused.

**Evidence:** The shared `timelines` map at `web/src/test/agent-identity-timeline-panel.test.tsx:85` is reused by the API spy; `relatedForDelivery` at line `100` is reused for related expansion proof.

### Criterion: `test-file-organization`

**Claim:** New tests are grouped by behavior and do not make existing broad component tests harder to navigate.

**Evidence:** Identity timeline component behavior lives in the dedicated `web/src/test/agent-identity-timeline-panel.test.tsx` file. `web/src/test/agent-panel-deeplink.test.tsx:143` groups the Agents-panel identity timeline boundary proof separately from terminal deep-link tests, which are grouped under `web/src/test/agent-panel-deeplink.test.tsx:155`. API wrapper route-path tests are grouped near existing API wrapper tests in `web/src/test/api.test.ts:141` through `web/src/test/api.test.ts:218`.

### Criterion: `verification-scope-discipline`

**Claim:** Focused proof and the exact handoff verification were both run.

**Evidence:** Focused tests were run for `src/test/api.test.ts`, `src/test/agent-identity-timeline-panel.test.tsx`, and `src/test/agent-panel-deeplink.test.tsx`; all passed after implementation and review fixes. The exact Verification Command also passed with `92` tests and a successful build.

## Coding Test Contract

### Clause: `C-TC-1`

**Claim:** API wrapper tests prove the three committed identity route methods and URL encoding.

**Evidence:** `web/src/test/api.test.ts:141`, `web/src/test/api.test.ts:162`, and `web/src/test/api.test.ts:187` assert identity list, timeline, and related-event wrapper behavior and encoded route paths.

### Clause: `C-TC-2`

**Claim:** Component tests prove configured identities, including inactive/no-event identities, are listed separately from terminal/session state.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:121` asserts Aria, Cael, and Unused Agent roster buttons render; `unused` is inactive with no terminal in `web/src/test/agent-identity-timeline-panel.test.tsx:51`.

### Clause: `C-TC-3`

**Claim:** Component tests prove selecting another identity replaces details and timeline.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:142` clicks Cael and asserts the Cael timeline call, Cael heading, removal of `term-aria`, canonical broadcast event ID, and Cael role.

### Clause: `C-TC-4`

**Claim:** Component tests prove timeline row summaries and ordering.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:129` through `web/src/test/agent-identity-timeline-panel.test.tsx:139` assert event kind, occurrence time, participant role, event ID ordering, and non-rendering of the non-participant event ID.

### Clause: `C-TC-5`

**Claim:** Component tests prove an authored non-participant workspace event absent from the selected identity timeline response is not rendered.

**Evidence:** `workspaceRefreshId` is declared at `web/src/test/agent-identity-timeline-panel.test.tsx:83`, omitted from the mocked Aria timeline at lines `85` through `89`, and asserted absent at line `139`.

### Clause: `C-TC-6`

**Claim:** Component tests prove causation and correlation related-event groups render from `api.getAgentIdentityRelatedEvents(...)`.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:158` expands the delivery row, asserts the API call with selected identity/event ID, and checks Direct Cause plus Shared Correlation Thread output. `web/src/test/agent-identity-timeline-panel.test.tsx:174` proves a stale in-flight related request fetched under Aria does not suppress a later Cael related-events call for the same canonical event ID.

### Clause: `C-TC-7`

**Claim:** Component tests prove one canonical broadcast event appears on Aria and Cael views with identity-specific roles.

**Evidence:** The same event ID is authored for Aria and Cael at `web/src/test/agent-identity-timeline-panel.test.tsx:72` through `web/src/test/agent-identity-timeline-panel.test.tsx:82`; `web/src/test/agent-identity-timeline-panel.test.tsx:153` through `web/src/test/agent-identity-timeline-panel.test.tsx:155` assert Cael's selected role.

### Clause: `C-TC-8`

**Claim:** Component tests prove empty timeline, loading, and unreachable states are distinct.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:227` through `web/src/test/agent-identity-timeline-panel.test.tsx:235` asserts empty no-recent-activity without loading/error text. `web/src/test/agent-identity-timeline-panel.test.tsx:238` through `web/src/test/agent-identity-timeline-panel.test.tsx:253` asserts loading then unreachable error without empty text.

### Clause: `C-TC-9`

**Claim:** The exact Verification Command passed before completion.

**Evidence:** `cd web && npm test -- --run && npm run build` completed with `92` passing tests and successful `tsc && vite build`.

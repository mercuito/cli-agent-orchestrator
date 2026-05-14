# Code Contract Defence — t-3

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Always applies; each code-shape claim points to concrete production code or verification evidence. |

## Feature-Level Code Contract

### Clause: F-CC-6

**Claim:** Live timeline refresh follows the dashboard's existing poll-and-reconcile pattern and does not introduce a different live transport.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:290` uses `setInterval` polling; `web/src/components/AgentIdentityTimelinePanel.tsx:295` clears the interval during cleanup; `web/src/components/AgentIdentityTimelinePanel.tsx:273` uses the existing API helper rather than a new transport.

## Coding Code Contract

### Criteria: `full-verification-required`

**Claim:** The exact handoff Verification Command ran successfully before completion.

**Evidence:** Verification succeeded with `23 passed` for the Python route/event tests, `93 passed` for the web Vitest suite, and successful `tsc && vite build`.

### Criteria: `red-green-refactor`

**Claim:** The task began with focused failing proof, then production code was changed until the focused proof passed.

**Evidence:** Focused run `npm test -- --run src/test/agent-identity-timeline-panel.test.tsx` first failed because `linear:agent_mentioned:live` was absent after timer advancement; after the production change the same focused run passed with 7 tests.

### Criteria: `semantic-continuity`

**Claim:** Live refresh extends the existing identity timeline execution path.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:273` continues to call `api.getAgentIdentityTimeline(selectedId)`, the same helper used by the pre-existing selected-identity load.

### Criteria: `minimal-cohesive-changes`

**Claim:** Production changes are limited to component-local identity timeline polling.

**Evidence:** Production diff touches only `web/src/components/AgentIdentityTimelinePanel.tsx`; no backend, route-shape, API helper, or unrelated dashboard files changed.

### Criteria: `no-unnecessary-duplication`

**Claim:** The implementation reuses one `fetchTimeline` path for initial load and polling.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:267` defines `fetchTimeline(initialLoad)` and both `web/src/components/AgentIdentityTimelinePanel.tsx:289` and `web/src/components/AgentIdentityTimelinePanel.tsx:291` call it.

### Criteria: `no-test-only-production-seams`

**Claim:** No production API, prop, export, or hook was added solely for tests.

**Evidence:** Production change adds only `IDENTITY_TIMELINE_REFRESH_MS` and component-internal polling logic in `web/src/components/AgentIdentityTimelinePanel.tsx`; the test controls time with Vitest fake timers without widening production surfaces.

### Criteria: `respect-ownership-boundaries`

**Claim:** Live refresh stays with the frontend consumer that owns the identity timeline view.

**Evidence:** Polling is implemented inside `AgentIdentityTimelinePanel`, which already owns selected identity timeline state and rendering; no backend owner or unrelated panel was changed.

### Criteria: `prefer-public-surfaces`

**Claim:** Cross-boundary data access continues through the public frontend API helper.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:273` calls `api.getAgentIdentityTimeline`; no direct `fetch` call was introduced.

### Criteria: `respect-standing-decisions`

**Claim:** The implementation remains compatible with `cid-1`.

**Evidence:** `api.getAgentIdentityTimeline` is the existing helper for `GET /agents/identities/{agent_id}/timeline`; the component continues to consume that helper and does not alter route shape.

### Criteria: `readable-and-explicit`

**Claim:** The polling lifecycle and stale-response guard are explicit.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:266` declares the effect-local `cancelled` guard; `web/src/components/AgentIdentityTimelinePanel.tsx:274` ignores responses after cleanup; `web/src/components/AgentIdentityTimelinePanel.tsx:293` marks cleanup and clears the interval.

### Clause: C-CC-1

**Claim:** The selected identity timeline polls while an identity is selected and stops on selection change/unmount.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:261` scopes the effect to `selectedId`; `web/src/components/AgentIdentityTimelinePanel.tsx:290` starts polling; `web/src/components/AgentIdentityTimelinePanel.tsx:293` performs cleanup.

### Clause: C-CC-2

**Claim:** Stale responses from a prior selected identity cannot overwrite the current view.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:266` creates an effect-local cancellation flag; `web/src/components/AgentIdentityTimelinePanel.tsx:274` returns before setting state after cleanup; React cleanup runs before the next `selectedId` effect.

### Clause: C-CC-3

**Claim:** The task uses the committed timeline API helper and does not add client-side membership rules.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:273` fetches through `api.getAgentIdentityTimeline(selectedId)`; no code was added to inspect CAO event bodies or filter participant membership in the client.

### Clause: C-CC-4

**Claim:** Poll failures preserve the displayed timeline, while initial load failures still show the existing unreachable state.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:277` sets an error only when `initialLoad` is true; `web/src/components/AgentIdentityTimelinePanel.tsx:275` replaces the timeline only on successful responses; existing test `web/src/test/agent-identity-timeline-panel.test.tsx:238` continues to pass for initial load failure.

## Committed Implementation Decisions

### Decision: cid-1

**Claim:** The frontend live refresh remains on the committed identity timeline route shape.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:273` calls `api.getAgentIdentityTimeline(selectedId)`, which wraps the committed `GET /agents/identities/{agent_id}/timeline` route.

### Decision: cid-2

**Claim:** This task does not change related-events route behavior.

**Evidence:** Related-event fetching and cache keying in `AgentIdentityTimelinePanel` are unchanged; no route or API helper for related events was modified.

## Committed-Decision Promotion Draft

No promotion warranted: this task implements the existing `F-CC-6` poll-and-reconcile obligation but does not settle a new durable cross-task fact beyond the current contracts and committed route decisions.

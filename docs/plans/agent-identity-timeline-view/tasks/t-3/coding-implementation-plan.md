# Coding Implementation Plan — t-3

## Research Findings

- Investigated `web/src/components/AgentIdentityTimelinePanel.tsx`, `web/src/components/AgentPanel.tsx`, `web/src/components/InboxPanel.tsx`, `web/src/store.ts`, and identity timeline tests under `web/src/test`.
- `AgentIdentityTimelinePanel` owns roster selection, selected identity timeline loading, related-event cache reset, and timeline rendering. It currently calls `api.getAgentIdentityTimeline(selectedId)` only when `selectedId` changes.
- Existing dashboard live refresh uses component-local `setInterval` effects with cleanup: session detail polling in `AgentPanel`, inbox polling in `InboxPanel`, and dashboard home polling. Store reconciliation uses replacement plus equality checks for shared global state, but the identity timeline is local component state.
- The committed route decision `cid-1` matches the existing frontend API helper `api.getAgentIdentityTimeline`, so live refresh can poll the same public helper without backend or route changes.
- Existing `agent-identity-timeline-panel.test.tsx` already has reusable identity/event fixtures, mocked API helper responses, and behavior-grouped tests for roster selection, timeline rendering, related-event expansion, empty state, and error state.
- Main implementation risk is stale async responses when the selected identity changes. The refresh effect must ignore responses after cleanup and preserve the existing initial-load empty/error behavior.

## High-Level Architecture

- **Surface shape.** Extend `AgentIdentityTimelinePanel` with a single timeline refresh function/effect for the selected identity. No new exports, backend routes, API helper names, or store state are planned.
- **Data flow.** When `selectedId` is set, the panel immediately fetches `api.getAgentIdentityTimeline(selectedId)`, places that result into local `timeline`, and starts a polling interval. Each poll calls the same API helper for the selected identity and replaces local `timeline` only if the effect is still current. The backend remains responsible for participant membership, so non-participant workspace events stay absent by not being returned for the selected identity.
- **Reuse points.** Reuse `api.getAgentIdentityTimeline`, the current timeline rendering path, the current related-event cache reset on identity changes, and existing dashboard polling conventions (`setInterval`, cleanup on dependency change/unmount, silent retry on poll failures).

## Sub-Task List

1. Add focused failing live-refresh proof.
   - **Clauses satisfied:** `B-11`, `F-TC-3`, `C-TC-1`, `C-TC-2`, `C-TC-3`, `red-green-refactor`, `given-when-then-test-structure`, `setup-invariant-ownership`, `reusable-test-state`, `test-through-owner-surfaces`, `test-file-organization`.
   - **Done condition:** A focused Vitest run for `agent-identity-timeline-panel.test.tsx` fails because, after advancing the poll interval, the displayed Aria timeline does not yet show the later Aria-involving event while still keeping the newly recorded non-participant workspace event absent. The new test reuses existing identity/event fixtures, keeps setup validity in fixture helpers, and stays in the component's identity timeline behavior group.
   - **Dependency order:** First.

2. Implement selected identity timeline polling.
   - **Clauses satisfied:** `B-11`, `F-CC-6`, `C-CC-1`, `C-CC-2`, `C-CC-3`, `semantic-continuity`, `respect-ownership-boundaries`, `prefer-public-surfaces`, `respect-standing-decisions`.
   - **Done condition:** The focused live-refresh test passes, and existing identity selection, empty state, unreachable state, and related-event tests still pass.
   - **Dependency order:** After sub-task 1.

3. Preserve initial-load/error behavior and poll retry behavior.
   - **Clauses satisfied:** `C-CC-4`, `minimal-cohesive-changes`, `readable-and-explicit`, `no-unnecessary-duplication`, `no-test-only-production-seams`.
   - **Done condition:** Existing unreachable timeline state test still proves initial load errors, and poll failures do not clear an already displayed timeline.
   - **Dependency order:** During or after sub-task 2.

4. Run focused and full verification.
   - **Clauses satisfied:** `full-verification-required`, `test-validity-preserved`, `verification-scope-discipline`, `C-TC-4`.
   - **Done condition:** Focused frontend tests pass during development, then the exact handoff Verification Command succeeds before completion.
   - **Dependency order:** After implementation and refactor.

## Revision Log

- Reviewer-requested revision before implementation: strengthened sub-task 1's done condition to explicitly include non-participant workspace event exclusion during the live refresh proof, and mapped all selected coding-level criteria into sub-task clause coverage.

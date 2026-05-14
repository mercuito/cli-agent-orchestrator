# Coding Implementation Plan — t-2

## Research Findings

Investigated:

- `web/src/App.tsx` for the existing top-level dashboard tab model and Agents panel wiring.
- `web/src/components/AgentPanel.tsx` for current Agents-area visual conventions, route-initialization behavior, session/terminal polling, and action-button style.
- `web/src/api.ts` for the existing typed API wrapper pattern and shared `fetchJSON` boundary.
- `web/src/store.ts` for the existing dashboard store and polling/reconciliation conventions that this task must not extend into `t-3` identity live refresh.
- `web/src/test/components.test.tsx`, `web/src/test/agent-panel-deeplink.test.tsx`, and `web/src/test/api.test.ts` for React Testing Library and API wrapper mocking conventions.
- `src/cli_agent_orchestrator/api/main.py` and `docs/plans/agent-identity-timeline-view/committed-implementation-decisions.md` for the committed backend route and response shape from `t-1`.
- `docs/plans/agent-identity-timeline-view/ui-mockup.png` for the target roster/detail/timeline composition.

Learned:

- `AgentPanel` already owns the top-level Agents tab content and mixes session/terminal workflows with local state and API calls; adding an identity-timeline section from this panel satisfies `F-CC-4` without touching `App.tsx` tab definitions.
- `api.ts` centralizes dashboard HTTP access through `fetchJSON`, so identity roster/timeline/related reads should be added there and consumed by React code.
- The committed backend routes are `GET /agents/identities`, `GET /agents/identities/{agent_id}/timeline`, and `GET /agents/identities/{agent_id}/events/{event_id}/related`.
- Backend timeline rows already carry envelope fields, canonical `event_id`, and the selected identity's `participant_role`; frontend code should display those fields rather than recomputing timeline membership.
- Existing frontend tests primarily mock the API wrapper for component behavior and mock `fetch` for API wrapper path assertions.

Risks and unknowns:

- `AgentPanel.tsx` is already large. A focused child component under `web/src/components` is the clearest way to add the identity UI while keeping session/terminal behavior stable.
- The static UI task must avoid identity timeline polling. Selection-triggered fetches are enough for `t-2`; live refresh remains reserved for `t-3`.

## High-Level Architecture

Surface shape:

- Extend `web/src/api.ts` with `AgentIdentityStatus`, `AgentIdentityTimelineEvent`, `AgentIdentityTimeline`, `AgentIdentityRelatedEvents`, and `AgentIdentityCausationRelatedEvents` interfaces plus `listAgentIdentities`, `getAgentIdentityTimeline`, and `getAgentIdentityRelatedEvents` methods.
- Add a focused `web/src/components/AgentIdentityTimelinePanel.tsx` component that renders the identity roster, selected identity detail, timeline rows, empty/loading/error states, and related-event expansion controls.
- Render `AgentIdentityTimelinePanel` from `AgentPanel` above the existing Sessions list so the feature stays inside the current Agents tab without replacing existing terminal/session workflows.
- Extend existing frontend tests in `web/src/test/api.test.ts` and add or group component tests in `web/src/test/components.test.tsx` for the new identity UI behavior.

Data flow:

- On mount, the identity component calls `api.listAgentIdentities()` and stores the roster locally.
- If identities exist and none is selected, the component selects the first identity and calls `api.getAgentIdentityTimeline(selectedId)`.
- When the operator selects another roster item, the component fetches that identity's timeline and replaces the details/events shown.
- When the operator expands a timeline row, the component calls `api.getAgentIdentityRelatedEvents(selectedId, eventId)` and renders the response's `correlation_events`, `causation_events.direct_cause`, and `causation_events.direct_effects`.
- The component keeps roster, timeline, and related-event loading/error states separate, and it treats an empty `events` array as no recent activity rather than loading or unreachable.

Reuse points:

- Existing `fetchJSON` wrapper, API-object style, and `encodeURIComponent` path conventions in `web/src/api.ts`.
- Existing Tailwind dark dashboard palette, border/card density, action-button styling, and lucide icons already used in `AgentPanel`.
- Existing React Testing Library render, screen, fireEvent, waitFor, and `vi.spyOn(api, ...)` patterns.

## Sub-Task List

1. Add failing frontend API wrapper proof.
   - Clauses satisfied: `F-CC-3`, `C-CC-1`, `C-TC-1`, `public-boundary-proof`, `red-green-refactor`.
   - Done condition: Focused API wrapper tests fail because identity roster/timeline/related methods do not exist yet.
   - Dependency order: First.

2. Add failing component proof for roster, selection, timeline rows, non-participant exclusion, broadcast viewpoints, related expansion, and empty/error states.
   - Clauses satisfied: `B-1`, `B-2`, `B-3`, `B-4`, `B-5`, `B-6`, `B-7`, `B-8`, `B-9`, `B-10`, `B-12`, `C-1`, `C-2`, `C-3`, `C-4`, `F-TC-2`, `C-TC-2` through `C-TC-8`.
   - Done condition: Focused component tests fail because the identity timeline UI is not yet rendered.
   - Dependency order: After sub-task 1 defines expected API method names.

3. Implement typed identity API wrappers.
   - Clauses satisfied: `F-CC-3`, `C-CC-1`, `prefer-public-surfaces`, `boundary-and-failure-testing`.
   - Done condition: API wrapper tests pass with URL-encoded identity/event path assertions.
   - Dependency order: After sub-task 1.

4. Implement identity roster and selected identity detail/timeline UI.
   - Clauses satisfied: `B-1` through `B-7`, `B-10`, `B-12`, `C-1`, `C-2`, `C-3`, `F-CC-4`, `C-CC-2`, `C-CC-3`, `C-CC-4`, `C-CC-6`, `C-CC-7`.
   - Done condition: Component tests for roster, selection, timeline rows, non-participant exclusion from the returned identity timeline, broadcast viewpoints, and empty/loading/error states pass without introducing identity polling.
   - Dependency order: After sub-task 3.

5. Implement related-event expansion UI.
   - Clauses satisfied: `B-8`, `B-9`, `C-4`, `C-CC-5`, `C-TC-6`.
   - Done condition: Component tests prove causation and correlation groups render from the related-events response.
   - Dependency order: After sub-task 4.

6. Refactor, build, and update static web output through the established build.
   - Clauses satisfied: `F-CC-5`, `full-verification-required`, `semantic-continuity`, `minimal-cohesive-changes`, `no-unnecessary-duplication`, `no-test-only-production-seams`, `respect-ownership-boundaries`, `respect-standing-decisions`, `readable-and-explicit`, `test-validity-preserved`, `verification-scope-discipline`, `C-TC-9`.
   - Done condition: The exact Verification Command succeeds: `cd web && npm test -- --run && npm run build`.
   - Dependency order: Last.

## Revision Log

- 2026-05-13: Added explicit `B-7` coverage to the component proof and identity timeline implementation sub-tasks after implementation-plan review identified the assigned-slice gap. The static UI coverage treats the selected identity timeline fetch/refetch response as the UI's refresh input and proves the component does not render non-participant workspace events that are absent from that identity timeline response; `t-3` remains responsible for live polling/refresh.

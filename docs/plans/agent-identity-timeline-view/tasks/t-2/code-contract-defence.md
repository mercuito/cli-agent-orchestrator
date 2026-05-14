# Code Contract Defence — t-2

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [claim-evidence-verifiability](../../../../planning/methodology/criteria/coding-code-contract-defence/claim-evidence-verifiability.md) | Every defence claim must be checkable against concrete code, diff, or command evidence. |

## Feature-Level Code Contract

### Clause: `F-CC-3`

**Claim:** Frontend data access for identity roster, timeline, and related-event reads is added to `web/src/api.ts` and consumed through React dashboard code.

**Evidence:** Response interfaces are defined in `web/src/api.ts:53` through `web/src/api.ts:90`; API methods are defined in `web/src/api.ts:194` through `web/src/api.ts:202`. The component consumes those methods in `web/src/components/AgentIdentityTimelinePanel.tsx:238`, `web/src/components/AgentIdentityTimelinePanel.tsx:265`, and `web/src/components/AgentIdentityTimelinePanel.tsx:301`.

### Clause: `F-CC-4`

**Claim:** The identity timeline experience extends the existing Agents dashboard area without adding a new top-level navigation surface.

**Evidence:** `AgentPanel` imports `AgentIdentityTimelinePanel` at `web/src/components/AgentPanel.tsx:16` and renders it inside the existing Agents panel at `web/src/components/AgentPanel.tsx:255`. `web/src/App.tsx` top-level tabs were not changed.

### Clause: `F-CC-5`

**Claim:** Dashboard source changes live under `web/src`, and static web UI output was updated only through the established frontend build.

**Evidence:** Production source changes are under `web/src/api.ts`, `web/src/components/AgentPanel.tsx`, and `web/src/components/AgentIdentityTimelinePanel.tsx`. The exact Verification Command ran `npm run build`, which emitted `src/cli_agent_orchestrator/web_ui/index.html` and hashed assets under `src/cli_agent_orchestrator/web_ui/assets`.

## Coding Code Contract Criteria

### Criterion: `full-verification-required`

**Claim:** The exact Verification Command ran successfully before completion.

**Evidence:** `cd web && npm test -- --run && npm run build` completed with `92` tests passing and a successful Vite build.

### Criterion: `red-green-refactor`

**Claim:** Testable UI/API behavior started with failing focused proof before implementation and was then made green.

**Evidence:** The focused API test first failed because `api.listAgentIdentities`, `api.getAgentIdentityTimeline`, and `api.getAgentIdentityRelatedEvents` did not exist. The focused component test first failed because `AgentIdentityTimelinePanel` did not exist. After implementation, both focused test files passed, and the exact Verification Command passed.

### Criterion: `boundary-and-failure-testing`

**Claim:** Frontend API identifier boundaries and timeline loading/empty/error states are tested.

**Evidence:** `web/src/test/api.test.ts:162` and `web/src/test/api.test.ts:187` assert URL-encoded identity/event IDs. `web/src/test/agent-identity-timeline-panel.test.tsx:174` and `web/src/test/agent-identity-timeline-panel.test.tsx:185` assert empty, loading, and unreachable timeline states.

### Criterion: `semantic-continuity`

**Claim:** The new UI follows the existing dashboard API wrapper and Agents-panel component path.

**Evidence:** New HTTP access uses the existing `fetchJSON`-backed `api` object in `web/src/api.ts:194`. `AgentIdentityTimelinePanel` is integrated from `AgentPanel` rather than creating a new root component or tab.

### Criterion: `minimal-cohesive-changes`

**Claim:** The implementation stays inside the `t-2` frontend/dashboard UI slice.

**Evidence:** Production changes are limited to `web/src/api.ts`, `web/src/components/AgentPanel.tsx`, and `web/src/components/AgentIdentityTimelinePanel.tsx`. No backend route shape, backend service, or `t-3` live polling code was changed.

### Criterion: `no-unnecessary-duplication`

**Claim:** Existing API wrapper and dashboard visual patterns are reused, and repeated timeline formatting remains local and focused.

**Evidence:** API access uses `fetchJSON`; UI styling follows existing Tailwind dark dashboard cards and lucide icon usage in `AgentPanel`. Shared event label/time rendering is centralized in `formatLabel` and `formatTime` at `web/src/components/AgentIdentityTimelinePanel.tsx:5` and `web/src/components/AgentIdentityTimelinePanel.tsx:14`.

### Criterion: `no-test-only-production-seams`

**Claim:** New production exports and component boundaries serve dashboard behavior, not only tests.

**Evidence:** `AgentIdentityTimelinePanel` is exported and rendered by `AgentPanel` in production. New API methods are called by the production component. No test-only props, bypass constructors, or unsafe hooks were added.

### Criterion: `respect-ownership-boundaries`

**Claim:** API typing/access belongs to `web/src/api.ts`, while identity timeline presentation belongs to a focused dashboard component.

**Evidence:** Types and methods are in `web/src/api.ts:53` through `web/src/api.ts:90` and `web/src/api.ts:194` through `web/src/api.ts:202`. UI state and rendering live in `web/src/components/AgentIdentityTimelinePanel.tsx`.

### Criterion: `prefer-public-surfaces`

**Claim:** React code consumes committed backend routes only through the frontend `api` object.

**Evidence:** The component imports `api` from `../api` at `web/src/components/AgentIdentityTimelinePanel.tsx:2`. There are no component-local `fetch(...)` calls in the new component.

### Criterion: `respect-standing-decisions`

**Claim:** The task remains compatible with committed decisions `cid-1` and `cid-2`.

**Evidence:** `api.getAgentIdentityTimeline` calls `/agents/identities/{agent_id}/timeline` in `web/src/api.ts:195`, matching `cid-1`. `api.getAgentIdentityRelatedEvents` calls `/agents/identities/{agent_id}/events/{event_id}/related` in `web/src/api.ts:199`, matching `cid-2`.

### Criterion: `readable-and-explicit`

**Claim:** Names and UI labels make identity selection, participant role, canonical event ID, and related grouping explicit.

**Evidence:** State names include `selectedId`, `timeline`, `expandedEventId`, and `relatedByEvent`. UI labels include `Event ID` at `web/src/components/AgentIdentityTimelinePanel.tsx:170`, `Direct Cause` at `web/src/components/AgentIdentityTimelinePanel.tsx:198`, and `Shared Correlation Thread` at `web/src/components/AgentIdentityTimelinePanel.tsx:208`.

## Coding Code Contract

### Clause: `C-CC-1`

**Claim:** `web/src/api.ts` defines typed response shapes and URL-encoded methods for the three committed identity read routes.

**Evidence:** Interfaces are declared in `web/src/api.ts:53` through `web/src/api.ts:90`; URL-encoded methods are declared in `web/src/api.ts:194` through `web/src/api.ts:202`. API tests assert the route paths in `web/src/test/api.test.ts:141`, `web/src/test/api.test.ts:162`, and `web/src/test/api.test.ts:187`.

### Clause: `C-CC-2`

**Claim:** The identity timeline UI is rendered from `AgentPanel` inside the existing Agents tab.

**Evidence:** `AgentPanel` renders `<AgentIdentityTimelinePanel />` at `web/src/components/AgentPanel.tsx:255`; `web/src/App.tsx` was not changed.

### Clause: `C-CC-3`

**Claim:** The roster renders configured identities from `api.listAgentIdentities()`, and selected details/timeline render from `api.getAgentIdentityTimeline(...)`.

**Evidence:** Roster loading uses `api.listAgentIdentities()` in `web/src/components/AgentIdentityTimelinePanel.tsx:238`; timeline loading uses `api.getAgentIdentityTimeline(selectedId)` in `web/src/components/AgentIdentityTimelinePanel.tsx:265`.

### Clause: `C-CC-4`

**Claim:** Timeline rows display event kind, occurrence time, participant role, and canonical event ID from API rows without deriving membership from typed bodies.

**Evidence:** `TimelineRow` renders `event.event_name`, `event.occurred_at`, `event.participant_role`, and `event.event_id` in `web/src/components/AgentIdentityTimelinePanel.tsx:140` through `web/src/components/AgentIdentityTimelinePanel.tsx:172`. `AgentIdentityTimelineEvent` has no typed body field in `web/src/api.ts:64` through `web/src/api.ts:74`.

### Clause: `C-CC-5`

**Claim:** Related expansion calls the related-events API wrapper for the selected identity and renders correlation/causation collections from the current identity-scoped response, including when stale in-flight related requests resolve after identity selection changes.

**Evidence:** `relatedEventCacheKey(agentId, eventId)` identity-scopes related cache keys in `web/src/components/AgentIdentityTimelinePanel.tsx:23`. Selection changes clear related state in `web/src/components/AgentIdentityTimelinePanel.tsx:269` through `web/src/components/AgentIdentityTimelinePanel.tsx:271`. `handleToggleRelated` computes the current identity/event cache key and calls `api.getAgentIdentityRelatedEvents(selectedId, eventId)` in `web/src/components/AgentIdentityTimelinePanel.tsx:301` through `web/src/components/AgentIdentityTimelinePanel.tsx:310`. Rendering reads related state by the current selected identity/event key in `web/src/components/AgentIdentityTimelinePanel.tsx:436` through `web/src/components/AgentIdentityTimelinePanel.tsx:444`.

### Clause: `C-CC-6`

**Claim:** Loading, empty, and unreachable timeline states are distinct.

**Evidence:** Timeline rendering branches separately for `timelineLoading`, `timelineError`, and empty `timeline.events` in `web/src/components/AgentIdentityTimelinePanel.tsx:413` through `web/src/components/AgentIdentityTimelinePanel.tsx:424`.

### Clause: `C-CC-7`

**Claim:** The implementation does not add live identity polling/refresh behavior.

**Evidence:** The component fetches identities once on mount in `web/src/components/AgentIdentityTimelinePanel.tsx:234` and fetches timeline data on `selectedId` changes in `web/src/components/AgentIdentityTimelinePanel.tsx:255`; it does not call `setInterval` or dashboard store polling for identity timelines.

## Committed Implementation Decisions

### Decision: `cid-1`

**Claim:** The frontend consumes the committed timeline route shape.

**Evidence:** `web/src/api.ts:195` calls `/agents/identities/${encodeURIComponent(agentId)}/timeline`.

### Decision: `cid-2`

**Claim:** The frontend consumes the committed related-events route shape.

**Evidence:** `web/src/api.ts:199` calls `/agents/identities/${encodeURIComponent(agentId)}/events/${encodeURIComponent(eventId)}/related`.

## Committed-Decision Promotion Draft

No promotion warranted: this task consumes existing route-shape decisions and adds task-local frontend component/API wrapper structure, but it does not settle a new durable cross-task implementation fact.

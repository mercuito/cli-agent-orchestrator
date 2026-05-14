# Code Contract Defence — t-1

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Every feature/code contract and coding-level criterion claim needs concrete code or verification evidence. |
| `promotion-draft-durability` | This task settles durable payload and frontend registry boundaries that later tasks should inherit. |

## Feature-Level Code Contract

### Clause: `F-CC-1`

**Claim:** Timeline APIs expose typed payload data and do not author UI
presentation values.

**Evidence:** `CaoEventRecord.event_data` is parsed from persisted
`event_data_json` in `src/cli_agent_orchestrator/clients/cao_event_store.py`,
then carried by `TimelineEventRead.event_data` and
`AgentIdentityTimelineEventResponse.event_data`. No backend
`TimelineEventPresentation`, presenter registry, `to_timeline_presentation`,
title, summary, chip, or label code was added. `rg` during research found no
backend presenter surface in the changed code, and the exact Verification
Command passed.

### Clause: `F-CC-2`

**Claim:** Frontend main timeline and related-event rows dispatch through a
single event-view registry keyed by `event_type_key`.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx` calls
`eventTimelineViewRegistry.viewFor(event.event_type_key)` for both
`TimelineRow` and `RelatedEventList`. The registry lives in
`web/src/components/timelineEventViews.tsx`.

### Clause: `F-CC-4`

**Claim:** Unknown event type keys render through a frontend-owned generic
fallback from event facts and safe payload facts.

**Evidence:** `EventTimelineViewRegistry.viewFor` returns
`FallbackTimelineEventView` when no view is registered. The fallback renders
event name, envelope/source facts, participant role, and primitive top-level
`event_data` facts. The frontend fallback test proves unregistered
`cao.experimental.*` events remain visible on main and related surfaces.

## Coding Code Contract

### Selected Criteria

**Claim:** The selected coding-level criteria are satisfied by the landed
shape.

**Evidence:** Red-green proof was run for backend and frontend focused tests;
the exact Verification Command succeeded. Changes stayed in the assigned
backend timeline/API/event-log surfaces, frontend API/timeline rendering
surfaces, and task artifacts. Existing timeline ordering, participant
selection, and relatedness paths were extended rather than replaced.

### Clause: `C-CC-1`

**Claim:** Timeline and related read DTOs expose `event_data`.

**Evidence:** `TimelineEventRead` includes `event_data`, and `_timeline_event_from_record`
copies it from `CaoEventRecord`. `AgentIdentityTimelineEventResponse.from_read`
copies it into API responses.

### Clause: `C-CC-2`

**Claim:** Backend implementation remains data-only and does not introduce UI
presentation concepts.

**Evidence:** Backend changes are limited to parsed payload data on event-log
records, timeline read DTOs, and API response models. No backend presentation
registry or UI label/title/summary values were added.

### Clause: `C-CC-3`

**Claim:** Frontend API types expose generic JSON payload data while preserving
existing envelope fields.

**Evidence:** `web/src/api.ts` adds `event_data: Record<string, unknown>` to
`AgentIdentityTimelineEvent`; existing envelope fields remain unchanged.

### Clause: `C-CC-4`

**Claim:** Main and related frontend rows use the registry dispatch surface.

**Evidence:** `TimelineRow` and `RelatedEventList` both call
`eventTimelineViewRegistry.viewFor(event.event_type_key)`.

### Clause: `C-CC-5`

**Claim:** Unregistered event type keys return a generic fallback view showing
event name, envelope facts, participant role, and safe `event_data` facts.

**Evidence:** `EventTimelineViewRegistry.viewFor` falls back to
`FallbackTimelineEventView`; `displayableEventDataFacts` filters to primitive
top-level values and limits output.

### Clause: `C-CC-6`

**Claim:** No `t-2` known Linear/runtime/workspace/lifecycle views were added.

**Evidence:** The registry starts empty and no concrete event type key is
registered. The only view implemented is the fallback.

### Clause: `C-CC-7`

**Claim:** The registry service/export boundary is small and consumer-facing.

**Evidence:** `web/src/components/timelineEventViews.tsx` exports only
`eventTimelineViewRegistry`; view types, formatting helpers, and fallback
internals remain unexported. `AgentIdentityTimelinePanel` consumes the registry
instance directly.

## Committed Implementation Decisions

No prior committed implementation decisions were in force beyond the artifact's
empty ledger.

## Committed-Decision Promotion Draft

Proposed entries were approved by `coding-code-contract-reviewer` and promoted
to `feature-committed-implementation-decisions.md` as `CID-1` and `CID-2`:

- `CID-1`: Identity timeline and related-event backend reads expose typed CAO
  payload data as `event_data`, parsed from the persisted event-log
  `event_data_json` at `CaoEventRecord.event_data` and carried through
  `TimelineEventRead` into API responses. Backend timeline code remains
  data-only and must not add UI presentation values.
- `CID-2`: The frontend event-view registry for identity timeline rows lives
  at `web/src/components/timelineEventViews.tsx`. Main timeline rows and
  related-event rows dispatch through `eventTimelineViewRegistry.viewFor(event_type_key)`;
  unregistered event types render through the module's generic fallback.

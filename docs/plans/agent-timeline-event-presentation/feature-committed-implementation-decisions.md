# Feature Committed Implementation Decisions — Agent Timeline Event Presentation

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [self-sufficient-entries](../../planning/methodology/criteria/feature-committed-implementation-decisions/self-sufficient-entries.md) | Every promoted entry must stand on its own for later tasks. |
| [defence-promoted-additions-only](../../planning/methodology/criteria/feature-committed-implementation-decisions/defence-promoted-additions-only.md) | Entries must be promoted from Code Contract Defences rather than added directly during planning. |

## Entries

- `CID-1`: Identity timeline and related-event backend reads expose typed
  CAO payload data as `event_data`, parsed from the persisted event-log
  `event_data_json` at `CaoEventRecord.event_data` and carried through
  `TimelineEventRead` into API responses. Backend timeline code remains
  data-only and must not add UI presentation values.
- `CID-2`: The frontend event-view registry for identity timeline rows
  lives at `web/src/components/timelineEventViews.tsx`. Main timeline
  rows and related-event rows dispatch through
  `eventTimelineViewRegistry.viewFor(event_type_key)`; unregistered event
  types render through the module's generic fallback.
- `CID-3`: Generated frontend CAO event type constants live at
  `web/src/generated/caoEventTypeKeys.ts` and are refreshed by
  `scripts/generate_cao_event_type_keys.py`, which discovers backend
  module-owned `*_CAO_EVENTS` tuples and calls
  `cli_agent_orchestrator.events.serialization.event_type_key`.
- `CID-4`: Frontend known event view modules self-register by exporting
  `timelineEventViewRegistrations` from files under
  `web/src/components/timelineEventViews/`; `timelineEventViews.tsx`
  discovers those modules with Vite `import.meta.glob` and registers the
  declared views.

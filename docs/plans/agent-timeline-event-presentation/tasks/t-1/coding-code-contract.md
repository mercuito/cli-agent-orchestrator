# Coding Code Contract — t-1

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-CC-1` | Feature Code Contract | Timeline and related-event API responses must expose typed `event_data` while the backend remains data-only. |
| `F-CC-2` | Feature Code Contract | Timeline and related-event rows must dispatch through a frontend event-view registry keyed by `event_type_key`. |
| `F-CC-4` | Feature Code Contract | Untaught event kinds must remain visible through a frontend-owned generic fallback. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `full-verification-required` | The handoff names an exact backend/frontend verification command for this code-changing task. |
| `red-green-refactor` | The task changes observable backend API shape and frontend timeline behavior that can be proven before implementation. |
| `boundary-and-failure-testing` | HTTP response boundaries and frontend registry fallback behavior accept event payloads and unknown event type keys. |
| `semantic-continuity` | Existing identity timeline and related-event read paths are extended and must keep ordering, participant filtering, and relatedness semantics. |
| `minimal-cohesive-changes` | The task must stop at typed payload exposure, registry dispatch, and fallback visibility without implementing `t-2` known event views. |
| `no-unnecessary-duplication` | Main timeline rows and related-event rows need the same fallback rendering semantics without copied event formatting logic. |
| `no-test-only-production-seams` | Any new registry/export must serve production rendering, not test convenience. |
| `respect-ownership-boundaries` | Backend owns persisted event facts and API reads; frontend owns event presentation dispatch and fallback rendering. |
| `prefer-public-surfaces` | API responses must consume event-log read records through service/database owner surfaces rather than serializer internals in routes. |
| `respect-standing-decisions` | The committed implementation decisions artifact is in force even though it currently has no promoted entries. |
| `readable-and-explicit` | Typed payload and fallback behavior must be visible in names and types. |
| `service-definition-surface` | `AgentIdentityTimelineService` and related response types are shared read surfaces being extended. |
| `service-export-discipline` | The frontend registry module exports the consumer-facing registry instance used by the timeline component. |
| `well-defined-service` | The task creates the frontend event-view registry as a small shared service surface for current fallback rendering and later registrations. |

## Task-Specific Code Obligations

- `C-CC-1`: `TimelineEventRead` and `AgentIdentityTimelineEventResponse` must expose an `event_data` JSON object derived from the persisted CAO event payload for both identity timeline rows and related-event rows.
- `C-CC-2`: Backend timeline service and API code must not introduce `TimelineEventPresentation`, presenter registries, `to_timeline_presentation`, display titles, summaries, chips, entity-reference labels, or other backend-authored UI presentation values.
- `C-CC-3`: The frontend `AgentIdentityTimelineEvent` type must include `event_data` as a generic JSON object and preserve existing envelope fields unchanged.
- `C-CC-4`: Frontend timeline and related-event rendering must ask a single event-view registry for row content by `event_type_key`; concrete event-kind matching must live only inside that registry surface.
- `C-CC-5`: The registry must return a generic fallback view for unregistered event type keys, and that fallback must show event name, envelope facts, watched participant role when present, and safely displayable top-level `event_data` facts.
- `C-CC-6`: The `t-1` frontend implementation must not add known Linear/runtime/workspace/lifecycle event-specific presentations reserved for `t-2`, beyond an empty or fallback-only registry capable of later registrations.
- `C-CC-7`: The frontend registry service must keep its owner boundary in `web/src/components/timelineEventViews.tsx`, exporting only the registry instance consumed by `AgentIdentityTimelinePanel`.

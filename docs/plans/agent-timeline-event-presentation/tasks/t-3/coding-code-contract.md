# Coding Code Contract — t-3

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-CC-5` | Feature Code Contract | This task owns frontend entity-reference affordances and their external/internal navigation behavior. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `full-verification-required` | The handoff names an exact frontend verification command for this code-changing task. |
| `red-green-refactor` | Related-event continuity and entity-reference navigation are observable frontend behaviors that can be proven before implementation. |
| `semantic-continuity` | Related rows already dispatch through the registry; entity-reference behavior must extend that path without changing fallback or existing taught-view semantics. |
| `minimal-cohesive-changes` | The task must stop at related-event view continuity and entity-reference navigation/focus, without reworking unrelated dashboard session controls or backend presentation. |
| `no-unnecessary-duplication` | Main and related rows need the same entity-reference behavior and should share the same typed-view props and affordance primitives. |
| `no-test-only-production-seams` | Any widened component/view props must serve production navigation and focus behavior, not only test injection. |
| `respect-ownership-boundaries` | Typed event views own entity-reference affordances; `AgentPanel` owns dashboard terminal focus/opening; backend timeline code remains data-only. |
| `prefer-public-surfaces` | Terminal focus must use the existing dashboard terminal lookup/opening flow and API surface instead of duplicating session internals. |
| `respect-standing-decisions` | `CID-1` through `CID-4` require data-only backend reads, frontend registry dispatch for main/related rows, generated event constants, and view self-registration. |
| `readable-and-explicit` | Entity-reference target kind, missing target behavior, and navigation side effects must be visible in names, types, and accessible UI labels. |
| `service-export-discipline` | The registry owner module exports new consumer-facing navigation callback types for timeline event views and panel consumers. |

## Task-Specific Code Obligations

- `C-CC-1`: `TimelineEventViewProps` must carry production navigation callbacks for entity references so main and related rows use the same frontend typed views and the same entity-reference behavior.
- `C-CC-2`: Entity-reference UI must be rendered by frontend typed views from `event.event_data`; backend code must not author display labels, chips, URLs, target kinds, presenter registries, `TimelineEventPresentation`, or `to_timeline_presentation`.
- `C-CC-3`: Linear mention views must render an external entity-reference affordance only when a string `issue_url` exists in `event.event_data`; following it must open that URL in an outside browser context with `noopener,noreferrer`.
- `C-CC-4`: Runtime delivery views must render an internal terminal entity-reference affordance only when a string `terminal_id` exists in `event.event_data`; following it must ask the dashboard to focus/open that terminal without leaving the Agents dashboard.
- `C-CC-5`: `AgentPanel` must remain the owner of terminal focus/open behavior. The identity timeline panel may request focus by terminal id, but it must not duplicate session selection, terminal lookup, or `TerminalView` opening logic.
- `C-CC-6`: Missing Linear issue URLs or terminal IDs must degrade to non-clickable readable event facts rather than broken buttons or thrown render errors.
- `C-CC-7`: Related-event rows must continue to call `eventTimelineViewRegistry.viewFor(event.event_type_key)` for every related event group and must pass the same navigation callbacks that main rows pass.
- `C-CC-8`: New exports from `web/src/components/timelineEventViews.tsx` must be limited to production-facing event-view props or navigation callback types required by timeline row consumers.

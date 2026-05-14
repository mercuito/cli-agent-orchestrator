# Coding Implementation Plan — t-1

## Research Findings

- Backend timeline reads are assembled by `AgentIdentityTimelineService` from `CaoEventRecord` objects returned by `clients.cao_event_store`; the current service preserves ordering, participant filtering, correlation, and causation membership but drops the serialized event payload before the API response.
- `CaoEventRecord` already reconstructs the typed dataclass from `event_data_json`; exposing the parsed JSON payload at the record/read layer is the smallest data-only path and avoids route-level serializer knowledge.
- FastAPI models in `src/cli_agent_orchestrator/api/main.py` mirror `TimelineEventRead` directly, so adding `event_data` to the read model and response model extends both timeline and related-event routes through their existing conversion path.
- Frontend `AgentIdentityTimelinePanel.tsx` currently formats main rows and related rows inline. Related rows use a smaller separate list component, so shared fallback behavior needs a small frontend registry/view surface that can be reused by both contexts.
- `web/src/api.ts` owns the dashboard API TypeScript shapes. It has no generic JSON type today, so this task needs a local JSON-object type for `event_data`.
- Existing tests already provide real backend route coverage, real persisted event fixtures, API wrapper coverage, and rendered timeline component coverage. These should be extended instead of replaced.
- No committed implementation decisions have been promoted yet. The handoff explicitly forbids backend presentation registries and backend-authored UI values; that remains a hard scope boundary.

## High-Level Architecture

**Surface shape.** Add a parsed `event_data` JSON mapping to `CaoEventRecord`, carry it through `TimelineEventRead`, and expose it from `AgentIdentityTimelineEventResponse`. The response keeps all existing envelope fields intact and adds only data.

**Frontend registry.** Add a frontend-owned event-view registry module near the agent timeline component. It will export an `eventTimelineViewRegistry` plus a fallback rendering path. For `t-1`, the registry has no known event-specific registrations; every event uses the generic fallback unless a later task registers a concrete view.

**Data flow.** Persisted CAO event JSON is parsed in the event-log owner surface, copied into timeline read DTOs, serialized by FastAPI, typed by `web/src/api.ts`, then rendered by the frontend registry fallback for main and related rows.

**Reuse points.** Keep existing timeline ordering, related-event composition, `formatLabel`, `formatTime`, and route conversion patterns. Extend existing test scenario builders and frontend event helpers with `event_data`.

## Sub-Task List

1. **Backend red proof for typed payload API shape.**
   - Clauses satisfied: `B-9`, `C-1`, `C-4`, `F-CC-1`, `F-TC-1`, `C-TC-1`, `C-TC-2`, `C-TC-3`.
   - Done condition: focused backend assertions fail because `event_data` is missing from persistence/timeline/related response objects.
   - Dependency order: first.

2. **Backend typed payload implementation.**
   - Clauses satisfied: `F-CC-1`, `C-CC-1`, `C-CC-2`, `C-TC-1`, `C-TC-2`, `C-TC-3`.
   - Done condition: backend focused tests pass and route responses include typed JSON payload data with no backend presentation fields.
   - Dependency order: after sub-task 1.

3. **Frontend red proof for API types and fallback visibility.**
   - Clauses satisfied: `B-9`, `C-1`, `C-4`, `F-CC-2`, `F-CC-4`, `F-TC-1`, `C-TC-4`, `C-TC-5`, `C-TC-6`.
   - Done condition: focused frontend tests fail because the API type/component do not preserve or render `event_data` through a registry fallback.
   - Dependency order: after backend shape is known.

4. **Frontend registry and fallback implementation.**
   - Clauses satisfied: `B-9`, `C-1`, `C-4`, `F-CC-2`, `F-CC-4`, `C-CC-3`, `C-CC-4`, `C-CC-5`, `C-CC-6`, `C-CC-7`, `C-TC-4`, `C-TC-5`, `C-TC-6`.
   - Done condition: `web/src/api.ts` exposes `event_data` on `AgentIdentityTimelineEvent`, and main timeline and related-event rows render through the registry fallback for untaught events, showing envelope facts, participant role, and safe top-level `event_data` facts without known event-specific branches.
   - Dependency order: after sub-task 3.

5. **Refactor and exact verification.**
   - Clauses satisfied: all selected coding-level criteria, `C-TC-7`, and `test-validity-preserved`.
   - Done condition: duplicated fallback formatting is minimized, existing behavior remains intact, and the exact handoff Verification Command succeeds.
   - Dependency order: last.

## Revision Log

- Plan revision 1: Moved `C-CC-3` from backend typed payload implementation to frontend registry and fallback implementation because the reviewer identified it as the `web/src/api.ts` type obligation, not a backend service obligation.
- Plan revision 2: Added post-implementation coding criteria and `C-CC-7` for the new frontend registry service/export boundary; sub-task 4 already implemented and verified that boundary.

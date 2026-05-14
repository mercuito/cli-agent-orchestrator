# Coding Completion Report — t-1

## Implementation Summary

Implemented the typed payload and fallback surface for identity timeline
events. Backend event-log reads now expose parsed persisted CAO event JSON as
`event_data`; identity timeline and related-event API responses carry that
data alongside the existing envelope fields and participant role.

Frontend API types now include `event_data`, and identity timeline rendering
routes main and related rows through a frontend event-view registry in
`web/src/components/timelineEventViews.tsx`. For `t-1`, the registry has no
known event-specific registrations and therefore uses the generic fallback
view for untaught event kinds. The fallback shows event name, source/time,
correlation/causation facts, participant role, event id where appropriate,
and safely displayable top-level primitive `event_data` facts.

No Linear/runtime-specific known event views were implemented.

## Plan Divergence

The implementation followed the approved plan. Two plan revisions were made:

- Revision 1 moved `C-CC-3` from the backend implementation sub-task to the
  frontend implementation sub-task after plan review identified it as the
  `web/src/api.ts` type obligation.
- Revision 2 added post-implementation coding criteria and `C-CC-7` for the
  frontend registry service/export boundary after the criteria revisit.

Both revisions remained within the assigned `t-1` slice.

## Slice-Adequacy Self-Check

The assigned behavioral slices `B-9`, `C-1`, and `C-4` still fit the finished
implementation. Untaught event kinds remain visible on the main timeline and
related-events panel through fallback rows, and all displayed facts come from
the event envelope, `event_data`, or selected participant role.

The assigned code slices `F-CC-1`, `F-CC-2`, and `F-CC-4` still fit. Backend
responses expose typed payload data without backend presentation values, and
frontend registry/fallback ownership is established.

The assigned test slice `F-TC-1` still fits. Backend route/persistence tests
and frontend API/component tests now prove typed payload response shape and
fallback visibility.

No upstream feature contract, handoff, or committed decision was invalidated.

## Verification Result

Exact Verification Command:

```bash
uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py && cd web && npm test -- --run src/test/api.test.ts src/test/agent-identity-timeline-panel.test.tsx && npm run build
```

Result: succeeded. Backend: 24 tests passed. Frontend: 38 tests passed. Build:
`tsc && vite build` succeeded.

## Spec Sync

No upstream planning artifact needed a behavior, capability, code, or test
contract amendment. Task-level coding contracts were updated after the
post-implementation criteria revisit to reflect the actual registry service
boundary and authored fallback fixture criteria.

## Files Changed

- `src/cli_agent_orchestrator/clients/cao_event_store.py`
- `src/cli_agent_orchestrator/services/agent_identity_timeline.py`
- `src/cli_agent_orchestrator/api/main.py`
- `web/src/api.ts`
- `web/src/components/AgentIdentityTimelinePanel.tsx`
- `web/src/components/timelineEventViews.tsx`
- `test/api/test_agent_identity_routes.py`
- `test/events/test_cao_event_persistence.py`
- `web/src/test/api.test.ts`
- `web/src/test/agent-identity-timeline-panel.test.tsx`
- `docs/plans/agent-timeline-event-presentation/tasks/t-1/coding-code-contract.md`
- `docs/plans/agent-timeline-event-presentation/tasks/t-1/coding-test-contract.md`
- `docs/plans/agent-timeline-event-presentation/tasks/t-1/coding-implementation-plan.md`
- `docs/plans/agent-timeline-event-presentation/tasks/t-1/behavioral-contract-defence.md`
- `docs/plans/agent-timeline-event-presentation/tasks/t-1/code-contract-defence.md`
- `docs/plans/agent-timeline-event-presentation/tasks/t-1/test-contract-defence.md`

## Observations

The event-log already stored canonical JSON payloads, but `CaoEventRecord`
only exposed the reconstructed dataclass. Exposing parsed JSON at that owner
surface kept routes data-only and avoided serializer knowledge in FastAPI
models.

The existing related-events panel used a smaller rendering path than main
timeline rows, so the registry fallback had to be reusable across both
surfaces rather than only replacing `TimelineRow`.

## Hiccups

- The implementation-plan review found one incorrect clause mapping
  (`C-CC-3` assigned to backend work). Resolved by revising the plan and
  receiving explicit plan approval.
- The first frontend fallback assertion matched the same related event in
  two related groups. Resolved by asserting at least one matching fallback
  fact because the duplicate visibility is expected from correlation plus
  direct-effect membership.
- Final behavioral review identified that related-event reads did not carry
  the watched identity's participant role and that untaught relatedness lacked
  real backend evidence. Resolved by adding participant-role lookup to related
  reads and an untaught backend relatedness route test.
- Final code review identified unused helper exports from the registry module.
  Resolved by keeping formatting helpers and view types internal and exporting
  only `eventTimelineViewRegistry`.
- Final test review identified missing `test-artifact-containment` selection.
  Resolved by adding the criterion and defence evidence for the in-memory
  SQLite persisted-event harness.

## Optimization Opportunities

- Later known event-view tasks can decide whether to register views by direct
  calls to `eventTimelineViewRegistry.register(...)` or by a small local
  registration helper if the list grows.
- The fallback currently displays up to six primitive top-level payload facts.
  Later UX work could tune ordering or elision once real untaught event
  examples accumulate.

## Risks And Known Issues

- The generic fallback deliberately ignores nested arrays/objects in
  `event_data` to avoid noisy or unsafe rendering. This is compliant for
  `t-1`, but known views in later tasks should render typed nested facts
  intentionally where needed.

## Final Review Outcomes

- `coding-implementation-plan-reviewer` (`Gauss`): approved the revised
  Coding Implementation Plan after `C-CC-3` was moved to the frontend
  implementation sub-task.
- `coding-behavioral-contract-reviewer` (`Carver`): approved after related
  reads were updated to carry watched-identity participant roles and backend
  untaught-event relatedness proof was added.
- `coding-code-contract-reviewer` (`Locke`): approved after the frontend
  registry module export surface was narrowed to `eventTimelineViewRegistry`.
  Approved committed-decision promotion draft was promoted to
  `feature-committed-implementation-decisions.md` as `CID-1` and `CID-2`.
- `coding-test-contract-reviewer` (`McClintock`): approved after
  `test-artifact-containment` was added to the Coding Test Contract and
  defended with the in-memory SQLite persisted-event harness evidence.

# Coding Test Contract — t-3

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-TC-3` | Feature-level Test Contract | Live-refresh proof must demonstrate that a newly recorded Aria-involving event appears without dashboard reload and that a newly recorded non-participant workspace event does not appear. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `test-validity-preserved` | Universal criterion; existing tests remain authoritative for their target behavior. |
| `given-when-then-test-structure` | The focused proof has setup, polling action, and observable timeline assertions. |
| `public-boundary-proof` | Live identity timeline refresh changes the dashboard user boundary and must be proved through rendered component behavior. |
| `setup-invariant-ownership` | Identity and event fixtures must remain valid setup, not hidden assertions of the behavior under test. |
| `reusable-test-state` | Existing identity and timeline fixtures are reused across scenarios and should be extended rather than copied wholesale. |
| `test-through-owner-surfaces` | The React test should exercise `AgentIdentityTimelinePanel` through its public API helper boundary, not duplicate filtering or reconciliation internals. |
| `test-file-organization` | `agent-identity-timeline-panel.test.tsx` covers multiple identity timeline behavior families and must remain grouped by behavior. |
| `verification-scope-discipline` | Focused Vitest proof is required during development and the exact handoff Verification Command is required before completion. |

## Task-Specific Proof Obligations

- `C-TC-1`: Add focused component proof that, while Aria remains selected, advancing the dashboard polling interval causes a later `api.getAgentIdentityTimeline('aria')` response containing a new Aria-involving event to render that event without remounting or reopening the identity view.
- `C-TC-2`: The same focused proof, or a paired proof, must demonstrate that a later timeline response excluding a newly recorded workspace event with no agent participants keeps that workspace event absent from Aria's displayed timeline.
- `C-TC-3`: The focused proof must use mocked API responses only at the HTTP-helper boundary and must not implement participant filtering logic inside the test.
- `C-TC-4`: Before completion, run the exact Verification Command from the handoff: `uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py && cd web && npm test -- --run && npm run build`.

# Coding Test Contract — t-2

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-TC-2` | Feature-level Test Contract | Frontend proof must use existing Vitest and React Testing Library dashboard patterns with mocked API responses for roster, identity view, timeline rows, related-event interactions, broadcast viewpoints, and empty timeline state. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| [test-validity-preserved](../../../../planning/methodology/criteria/coding-test-contract/test-validity-preserved.md) | Universal criterion for every code-touching task. |
| [given-when-then-test-structure](../../../../planning/methodology/criteria/coding-test-contract/given-when-then-test-structure.md) | Component tests prove multi-step rendering, selecting identities, and expanding related-event rows. |
| [public-boundary-proof](../../../../planning/methodology/criteria/coding-test-contract/public-boundary-proof.md) | The task adds frontend API wrapper methods and user-visible dashboard UI boundaries. |
| [inspectable-authored-inputs](../../../../planning/methodology/criteria/coding-test-contract/inspectable-authored-inputs.md) | Mocked identities, participant roles, event IDs, correlation IDs, and causation IDs directly explain the UI assertions. |
| [setup-invariant-ownership](../../../../planning/methodology/criteria/coding-test-contract/setup-invariant-ownership.md) | Shared frontend mock setup must establish valid API responses before leaf tests assert UI behavior. |
| [reusable-test-state](../../../../planning/methodology/criteria/coding-test-contract/reusable-test-state.md) | Roster, timeline, broadcast, and related-event scenarios share repeated identity/event mock state. |
| [test-file-organization](../../../../planning/methodology/criteria/coding-test-contract/test-file-organization.md) | Existing component and API test files cover multiple behavior families, so identity-timeline tests must be grouped by behavior. |
| [verification-scope-discipline](../../../../planning/methodology/criteria/coding-test-contract/verification-scope-discipline.md) | Focused frontend proof and the exact handoff Verification Command are both required before completion. |

## Task-Specific Proof Obligations

- `C-TC-1`: API wrapper tests must prove identity list, identity timeline, and related-event methods call the committed route paths with URL-encoded identity/event identifiers.
- `C-TC-2`: Component tests must prove the Agents panel lists configured identities including inactive/no-event identities and keeps them separate from terminal/session state.
- `C-TC-3`: Component tests must prove selecting one identity opens that identity's configured details and timeline, then selecting another identity replaces the prior details and timeline.
- `C-TC-4`: Component tests must prove timeline rows display event kind, occurrence time, selected identity participant role, and canonical event ID in recent occurrence order as provided by the API.
- `C-TC-5`: Component tests must prove an authored non-participant workspace event that is absent from the selected identity timeline response is not rendered during the UI's timeline fetch/refetch path.
- `C-TC-6`: Component tests must prove expanding a row renders causation and correlation related-event groups from `api.getAgentIdentityRelatedEvents(...)`.
- `C-TC-7`: Component tests must prove one canonical broadcast event appears on Aria and Cael identity timelines with each selected identity's own participant role.
- `C-TC-8`: Component tests must prove an identity with no events displays a no-recent-activity state distinct from loading and unreachable/error states.
- `C-TC-9`: The exact Verification Command from the handoff must pass before completion: `cd web && npm test -- --run && npm run build`.

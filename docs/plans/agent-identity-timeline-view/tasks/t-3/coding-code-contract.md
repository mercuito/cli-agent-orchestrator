# Coding Code Contract — t-3

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-CC-6` | Feature-level Code Contract | Live timeline refresh must follow the dashboard's existing poll-and-reconcile pattern unless the feature contract is amended. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `full-verification-required` | Code changes will be produced and the handoff names one exact Verification Command. |
| `red-green-refactor` | The live refresh behavior is testable from the existing React component surface. |
| `semantic-continuity` | The task extends the existing identity timeline fetch path and existing dashboard polling patterns. |
| `minimal-cohesive-changes` | The task is limited to live refresh for the selected identity timeline. |
| `no-unnecessary-duplication` | Polling and reconciliation should reuse the component's existing timeline load path rather than duplicating a separate data path. |
| `no-test-only-production-seams` | Any production changes must serve live refresh behavior, not only test control. |
| `respect-ownership-boundaries` | Frontend live refresh belongs with the Agents identity timeline consumer and should not reshape backend routes or unrelated dashboard owners. |
| `prefer-public-surfaces` | The component must continue to consume the identity timeline through `web/src/api.ts` public API helpers. |
| `respect-standing-decisions` | `cid-1` establishes the committed identity timeline route shape used by the frontend. |
| `readable-and-explicit` | Polling, stale-response guards, and timeline replacement behavior must be clear to future readers. |

## Task-Specific Code Obligations

- `C-CC-1`: `AgentIdentityTimelinePanel` refreshes the selected identity timeline by polling `api.getAgentIdentityTimeline(selectedId)` while an identity remains selected, and clears that polling when the selected identity changes or the panel unmounts.
- `C-CC-2`: Polled timeline responses replace the displayed timeline only when they correspond to the identity still selected at response time, preventing stale responses from a prior identity from overwriting the current view.
- `C-CC-3`: Live refresh continues to use the committed timeline API route through `api.getAgentIdentityTimeline`; this task does not introduce backend route-shape changes, direct ad hoc fetches, or client-side event membership rules.
- `C-CC-4`: Poll failures preserve the currently displayed timeline and retry on the next poll, while the initial selected-identity load still exposes the existing unreachable timeline state when no prior timeline is available.

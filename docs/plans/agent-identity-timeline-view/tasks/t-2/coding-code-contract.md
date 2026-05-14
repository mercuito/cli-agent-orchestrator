# Coding Code Contract — t-2

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-CC-3` | Feature-level Code Contract | Frontend identity-timeline data access must be added to `web/src/api.ts` and consumed through React dashboard code instead of direct component fetches. |
| `F-CC-4` | Feature-level Code Contract | The identity timeline UI must extend the existing top-level Agents dashboard area rather than adding another dashboard navigation surface. |
| `F-CC-5` | Feature-level Code Contract | Dashboard source changes must stay under `web/src`, with static web UI output updated only by the established frontend build. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| [full-verification-required](../../../../planning/methodology/criteria/coding-code-contract/full-verification-required.md) | The task produces frontend production code changes and has an exact Verification Command. |
| [red-green-refactor](../../../../planning/methodology/criteria/coding-code-contract/red-green-refactor.md) | The roster, identity view, timeline rows, related-event expansion, and empty/error states are testable UI behaviors. |
| [boundary-and-failure-testing](../../../../planning/methodology/criteria/coding-code-contract/boundary-and-failure-testing.md) | Frontend API wrappers accept identity/event identifiers and the UI must distinguish loading, empty, and unreachable timeline states. |
| [semantic-continuity](../../../../planning/methodology/criteria/coding-code-contract/semantic-continuity.md) | The work extends the existing Agents dashboard panel, dashboard API wrapper, and frontend test conventions. |
| [minimal-cohesive-changes](../../../../planning/methodology/criteria/coding-code-contract/minimal-cohesive-changes.md) | The task owns only the static frontend dashboard UI slice and must not implement `t-3` live refresh or backend route changes. |
| [no-unnecessary-duplication](../../../../planning/methodology/criteria/coding-code-contract/no-unnecessary-duplication.md) | New UI helpers, formatting, and fixtures should reuse existing dashboard/API patterns and avoid copied component logic. |
| [no-test-only-production-seams](../../../../planning/methodology/criteria/coding-code-contract/no-test-only-production-seams.md) | Any new props, helpers, or exports in production UI code must serve dashboard behavior rather than only simplifying tests. |
| [respect-ownership-boundaries](../../../../planning/methodology/criteria/coding-code-contract/respect-ownership-boundaries.md) | API typing belongs in `web/src/api.ts`; identity-timeline presentation belongs in dashboard React components under `web/src/components`. |
| [prefer-public-surfaces](../../../../planning/methodology/criteria/coding-code-contract/prefer-public-surfaces.md) | The UI must consume the committed backend route shape through the frontend `api` object rather than deep backend or ad hoc fetch access. |
| [respect-standing-decisions](../../../../planning/methodology/criteria/coding-code-contract/respect-standing-decisions.md) | The task must remain compatible with `cid-1` and `cid-2` route-shape decisions. |
| [readable-and-explicit](../../../../planning/methodology/criteria/coding-code-contract/readable-and-explicit.md) | Timeline membership, selected participant role, canonical event ID, and related-thread grouping must be apparent from names and UI labels. |

## Task-Specific Code Obligations

- `C-CC-1`: `web/src/api.ts` must define typed frontend response shapes and API methods for `GET /agents/identities`, `GET /agents/identities/{agent_id}/timeline`, and `GET /agents/identities/{agent_id}/events/{event_id}/related`, using URL-encoded path identifiers.
- `C-CC-2`: The identity timeline UI must be rendered from `AgentPanel` inside the existing Agents tab and must not add or alter the top-level tab/navigation model.
- `C-CC-3`: The roster must render configured identities from `api.listAgentIdentities()` independently of active terminal/session state, and selected identity details/timeline must render from `api.getAgentIdentityTimeline(...)`.
- `C-CC-4`: Timeline rows must display event kind, occurrence time, selected identity participant role, and canonical event ID from the API response without deriving membership or role from event typed bodies.
- `C-CC-5`: Related-event expansion must call `api.getAgentIdentityRelatedEvents(...)` and group returned correlation and causation records by the response's envelope-based related collections.
- `C-CC-6`: Loading, empty timeline, and unreachable/error states must be visually and textually distinct in the identity timeline panel.
- `C-CC-7`: The implementation must not add live polling/refresh behavior for identity timelines beyond the one-time fetches needed for roster selection in this static UI slice.

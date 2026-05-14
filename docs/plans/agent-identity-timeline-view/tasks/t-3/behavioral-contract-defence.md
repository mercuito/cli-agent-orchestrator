# Behavioral Contract Defence — t-3

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Always applies; the B-11 claim must point to concrete test and implementation evidence. |
| `broad-claim-coverage` | B-11 depends on selected-identity visibility and participant partitioning semantics during refresh. |

## Behavior: B-11

**Claim:** While Aria remains the selected identity, the panel polls the Aria identity timeline and renders a newly returned Aria-involving CAO event without dashboard reload or identity reopen.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:261` starts a selected-identity effect; `web/src/components/AgentIdentityTimelinePanel.tsx:273` fetches `api.getAgentIdentityTimeline(selectedId)`; `web/src/components/AgentIdentityTimelinePanel.tsx:289` performs the initial fetch; `web/src/components/AgentIdentityTimelinePanel.tsx:290` starts a 5s poll; `web/src/components/AgentIdentityTimelinePanel.tsx:293` clears the poll on selection change or unmount. `web/src/test/agent-identity-timeline-panel.test.tsx:153` renders the panel once, advances the poll interval, and asserts `linear:agent_mentioned:live` appears in the same watched timeline.

**Partitioning evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:156` mocks only the owner API helper response for the selected identity; `web/src/test/agent-identity-timeline-panel.test.tsx:164` returns the refreshed Aria timeline without the non-participant workspace event; `web/src/test/agent-identity-timeline-panel.test.tsx:188` asserts `workspace:context_refresh:non-participant` remains absent after the live refresh. Backend participant membership remains owned by the committed timeline route and is reverified by the exact Verification Command.

## Verification Evidence

Exact Verification Command succeeded:

```bash
uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py && cd web && npm test -- --run && npm run build
```

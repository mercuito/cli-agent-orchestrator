# Behavioral Contract Defence — t-2

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [claim-evidence-verifiability](../../../../planning/methodology/criteria/coding-behavioral-contract-defence/claim-evidence-verifiability.md) | Every behavior claim must be checkable against concrete tests or UI code evidence. |
| [broad-claim-coverage](../../../../planning/methodology/criteria/coding-behavioral-contract-defence/broad-claim-coverage.md) | The assigned behaviors depend on selection, ordering, visibility, partitioning, and related-event composition semantics. |

## Behavior: `B-1`

**Claim:** The Agents-area roster lists configured identities whether active or inactive and without requiring terminal/session state.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:234` calls `api.listAgentIdentities()`, and `web/src/test/agent-identity-timeline-panel.test.tsx:121` asserts Aria, Cael, and Unused Agent roster buttons render from mocked configured identities.

## Behavior: `B-2`

**Claim:** Selecting a roster identity opens the identity-scoped view for that identity.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:356` sets `selectedId` from the clicked identity. `web/src/test/agent-identity-timeline-panel.test.tsx:142` clicks Cael and asserts `api.getAgentIdentityTimeline` was last called with `cael`.

## Behavior: `B-3`

**Claim:** The selected identity view presents configured details and the identity timeline together.

**Evidence:** Details render from `selectedIdentity` in `web/src/components/AgentIdentityTimelinePanel.tsx:365` through `web/src/components/AgentIdentityTimelinePanel.tsx:389`, and timeline rows render in `web/src/components/AgentIdentityTimelinePanel.tsx:425` through `web/src/components/AgentIdentityTimelinePanel.tsx:438`. `web/src/test/agent-identity-timeline-panel.test.tsx:127` asserts Aria's terminal detail and `web/src/test/agent-identity-timeline-panel.test.tsx:129` asserts the timeline renders.

## Behavior: `B-4`

**Claim:** Selecting a different identity replaces the prior identity details and timeline.

**Evidence:** The timeline effect clears prior timeline state when `selectedId` changes in `web/src/components/AgentIdentityTimelinePanel.tsx:255` through `web/src/components/AgentIdentityTimelinePanel.tsx:278`. `web/src/test/agent-identity-timeline-panel.test.tsx:142` asserts selecting Cael removes Aria's terminal detail and displays Cael's broadcast role.

## Behavior: `B-5`

**Claim:** Timeline rows render the selected identity's events in the order returned by the identity timeline API.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:427` maps `timeline.events` without reordering. `web/src/test/agent-identity-timeline-panel.test.tsx:134` asserts the rendered event IDs appear as mention, delivery, broadcast.

## Behavior: `B-6`

**Claim:** Each timeline row shows event kind, occurrence time, and selected identity participant role.

**Evidence:** `TimelineRow` renders event kind, participant role, and occurrence time in `web/src/components/AgentIdentityTimelinePanel.tsx:140` through `web/src/components/AgentIdentityTimelinePanel.tsx:153`. `web/src/test/agent-identity-timeline-panel.test.tsx:130` through `web/src/test/agent-identity-timeline-panel.test.tsx:133` assert those fields for Aria's rows.

## Behavior: `B-7`

**Claim:** The UI renders only events returned for the selected identity timeline and does not surface a non-participant workspace event that is absent from that identity timeline response.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:425` renders only `timeline.events`. `web/src/test/agent-identity-timeline-panel.test.tsx:83` defines an authored non-participant workspace event ID and `web/src/test/agent-identity-timeline-panel.test.tsx:139` asserts it is not rendered.

## Behavior: `B-8`

**Claim:** Expanding a row shows the directly causing event returned by the related-events API.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:197` renders `related.causation_events.direct_cause` under Direct Cause. `web/src/test/agent-identity-timeline-panel.test.tsx:158` expands the delivery row and asserts Direct Cause plus the mention event ID.

## Behavior: `B-9`

**Claim:** Expanding a row shows the shared correlation thread returned by the related-events API.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:207` renders `related.correlation_events` under Shared Correlation Thread. `web/src/test/agent-identity-timeline-panel.test.tsx:168` through `web/src/test/agent-identity-timeline-panel.test.tsx:171` assert the shared thread renders the mention and delivery event IDs.

## Behavior: `B-10`

**Claim:** The same canonical broadcast event can appear on Aria and Cael timelines with each selected identity's participant role.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:72` through `web/src/test/agent-identity-timeline-panel.test.tsx:82` define the same broadcast event ID with Aria and Cael roles. `web/src/test/agent-identity-timeline-panel.test.tsx:142` asserts selecting Cael renders that event ID with role `Observer` instead of Aria's `Mentioned` role.

## Behavior: `B-12`

**Claim:** An identity with no returned events is shown as no recent activity, distinct from loading and unreachable states.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:413` through `web/src/components/AgentIdentityTimelinePanel.tsx:424` renders separate loading, error, and empty branches. `web/src/test/agent-identity-timeline-panel.test.tsx:174` asserts the empty state appears without loading or unreachable text.

## Constraint: `C-1`

**Claim:** Identity visibility does not depend on a terminal.

**Evidence:** Roster data comes from `api.listAgentIdentities()` in `web/src/components/AgentIdentityTimelinePanel.tsx:238`, not sessions or terminals. The test identity `unused` has `active: false` and no terminal in `web/src/test/agent-identity-timeline-panel.test.tsx:51`, and is asserted visible in `web/src/test/agent-identity-timeline-panel.test.tsx:126`.

## Constraint: `C-2`

**Claim:** The UI presents timeline membership and selected participant roles from the identity timeline API response.

**Evidence:** Timeline rows map `timeline.events` directly in `web/src/components/AgentIdentityTimelinePanel.tsx:427`, and roles render from `event.participant_role` in `web/src/components/AgentIdentityTimelinePanel.tsx:144`. `web/src/test/agent-identity-timeline-panel.test.tsx:153` through `web/src/test/agent-identity-timeline-panel.test.tsx:155` assert Cael's selected role replaces Aria's role.

## Constraint: `C-3`

**Claim:** Multi-identity visibility preserves the canonical event ID returned by the API.

**Evidence:** Event IDs render from `event.event_id` in `web/src/components/AgentIdentityTimelinePanel.tsx:171`. `web/src/test/agent-identity-timeline-panel.test.tsx:153` asserts Cael's broadcast timeline row retains `linear:agent_mentioned:broadcast`.

## Constraint: `C-4`

**Claim:** Related threads are rendered from the related endpoint's envelope-based causation and correlation collections rather than typed body inspection.

**Evidence:** `handleToggleRelated` calls `api.getAgentIdentityRelatedEvents(selectedId, eventId)` in `web/src/components/AgentIdentityTimelinePanel.tsx:301`, and rendering uses `causation_events` / `correlation_events` in `web/src/components/AgentIdentityTimelinePanel.tsx:197` through `web/src/components/AgentIdentityTimelinePanel.tsx:210`. No typed event body fields exist in the frontend response types at `web/src/api.ts:64`.

# Behavioral Contract Defence — t-1

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Every assigned behavior and constraint needs concrete test or implementation evidence. |
| `broad-claim-coverage` | The assigned behavior depends on visibility, relatedness, and source-of-fact composition across main and related timeline surfaces. |

## Behavior: `B-9`

**Claim:** Untaught event type keys remain visible on both main timeline and
related-events surfaces through the generic fallback.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx` test
`renders untaught event kinds through fallback views on the timeline and
related panel` renders `cao.experimental.AuditEvent` and
`cao.experimental.RelatedAuditEvent` without any registered known view and
asserts the event name, main participant role, related participant role,
source, correlation, payload facts, and related direct-effect visibility.
`test_agent_identity_related_events_route_keeps_untaught_events_related_and_roleful`
proves the related endpoint supplies participant roles for untaught canonical
and direct-effect rows. The exact Verification Command passed.

## Constraint: `C-1`

**Claim:** Fallback rows display only event envelope facts, selected participant
role, and primitive top-level facts already present in `event_data`.

**Evidence:** `web/src/components/timelineEventViews.tsx` fallback view reads
`event.event_name`, `event.source_type`, `event.source_id`, `event.occurred_at`,
`event.correlation_id`, `event.causation_id`, `event.participant_role`, and
primitive entries from `event.event_data`. The frontend fallback test asserts
`nested_fact` and `tags` are not rendered while `audit_kind` and `confidence`
are rendered from authored `event_data`.

## Constraint: `C-4`

**Claim:** Untaught events continue to participate in correlation and causation
relatedness while remaining visible through fallback rendering.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx` includes an
untaught related event as both a direct effect and a correlation-thread member;
the related panel renders it through the same fallback path. Backend
`test_agent_identity_related_events_route_keeps_untaught_events_related_and_roleful`
publishes two `_ExperimentalAuditEvent` records sharing correlation and
causation facts, then proves the related endpoint returns the untaught event in
the correlation thread and direct effects with typed `event_data` and
participant role. The exact Verification Command passed.

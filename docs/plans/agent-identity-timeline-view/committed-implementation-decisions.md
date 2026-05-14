# Committed Implementation Decisions — Agent Identity Timeline View

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [self-sufficient-entries](../../planning/methodology/criteria/feature-committed-implementation-decisions/self-sufficient-entries.md) | Any promoted decision must stand on its own for later tasks. |
| [defence-promoted-additions-only](../../planning/methodology/criteria/feature-committed-implementation-decisions/defence-promoted-additions-only.md) | New decisions enter this ledger only through task Code Contract Defence promotion drafts. |

## Promoted Decisions

### cid-1 — Backend Identity Timeline Route Shape

Promoted from
`docs/plans/agent-identity-timeline-view/tasks/t-1/code-contract-defence.md`
after `coding-code-contract-reviewer` approval.

The backend identity timeline read route is
`GET /agents/identities/{agent_id}/timeline`. It resolves the identity through
the manager-owned identity surface and returns an `identity` object plus
`events` rows carrying event envelope fields and the selected identity's
`participant_role`.

### cid-2 — Backend Identity Related-Events Route Shape

Promoted from
`docs/plans/agent-identity-timeline-view/tasks/t-1/code-contract-defence.md`
after `coding-code-contract-reviewer` approval.

The backend related-event read route is
`GET /agents/identities/{agent_id}/events/{event_id}/related`. It resolves the
identity through the manager-owned identity surface, resolves the canonical CAO
event by ID, and returns `event`, `correlation_events`, and
`causation_events` with `direct_cause` and `direct_effects`; missing
relatedness is represented as `null` / empty arrays rather than fabricated
events.

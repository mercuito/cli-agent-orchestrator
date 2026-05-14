# Behavioral Contract Defence — t-2

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Every assigned behavior needs concrete test and implementation evidence. |
| `broad-claim-coverage` | `B-1` depends on distinct visibility across multiple event kinds on one timeline. |

## Behavior: `B-1`

**Claim:** Linear mention, runtime delivery, workspace switch, and runtime
lifecycle rows render as distinct known presentations.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx` test
`renders taught Linear and runtime event kinds through registered typed views`
renders all four generated event type keys on Aria's timeline and asserts
distinct Linear issue, delivery terminal/message, workspace from/to, and
lifecycle phase/status/context content. The exact Verification Command passed.

## Behavior: `B-2`

**Claim:** The Linear mention row shows issue context, mentioner, and mention
text from typed payload data.

**Evidence:** The frontend known-view test asserts `OPS-417`, `Restore
dashboard event detail`, `Nia`, the mention text, and `Linear issue` appear
for a row keyed by `LINEAR_AGENT_MENTIONED_EVENT`.

## Behavior: `B-3`

**Claim:** The runtime delivery row shows triggering source kind, delivered
message, and receiving terminal from typed payload data.

**Evidence:** The frontend known-view test asserts `Linear Mention`, the
delivered message, and `term-aria-main` appear for a row keyed by
`AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT`. Backend runtime test
`test_notify_publishes_typed_runtime_events_with_provider_causation` proves
the runtime delivery event payload carries `source_kind`, `source_id`, and
`message_body`; API route test
`test_agent_identity_timeline_route_returns_participant_index_rows` proves
those facts flow through timeline `event_data`.

## Behavior: `B-4`

**Claim:** The workspace context switch row shows both the from-context and
to-context.

**Evidence:** The frontend known-view test asserts `cli-agent-orchestrator`,
`yards`, and `switched` appear for a row keyed by
`AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT`.

## Behavior: `B-5`

**Claim:** The runtime lifecycle row shows lifecycle phase and surrounding
runtime/workspace context.

**Evidence:** The frontend known-view test asserts `restarted`, `idle`,
`term-aria-main`, and `yards` appear for a row keyed by
`AGENT_RUNTIME_LIFECYCLE_EVENT`.

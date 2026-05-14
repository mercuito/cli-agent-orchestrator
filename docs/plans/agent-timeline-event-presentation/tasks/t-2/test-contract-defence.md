# Test Contract Defence — t-2

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Every feature and coding test contract claim needs concrete proof artifact evidence. |

## Feature-Level Test Contract

### Clause: `F-TC-2`

**Claim:** Known frontend-view proof covers Linear mention, runtime delivery,
workspace context switch, and runtime lifecycle details from typed event data.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx` test
`renders taught Linear and runtime event kinds through registered typed views`
uses authored `event_data` examples for all four known kinds and asserts their
issue, mention, delivery, terminal, workspace context, and lifecycle details.

## Coding Test Contract

### Selected Criteria

**Claim:** Selected proof-quality criteria are satisfied.

**Evidence:** Frontend tests render the real `AgentIdentityTimelinePanel`
surface and use generated event constants. Authored payload facts are inline
in the leaf test. Existing setup helpers continue to own identity/timeline
fixture shape. Runtime/API backend tests use owner surfaces for event creation,
dispatch, persistence, and route reads. Persisted CAO event/database rows are
contained by the in-memory SQLite harness from `test/conftest.py`, and runtime
data dirs use `tmp_path`. The exact Verification Command succeeded.

### Clause: `C-TC-1`

**Claim:** Frontend tests prove Linear mention row details.

**Evidence:** The known-view frontend test asserts `OPS-417`, `Restore
dashboard event detail`, `Nia`, the mention text, and `Linear issue`.

### Clause: `C-TC-2`

**Claim:** Frontend tests prove runtime delivery row details.

**Evidence:** The known-view frontend test asserts `Linear Mention`, delivered
message text, and `term-aria-main` for
`AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT`.

### Clause: `C-TC-3`

**Claim:** Frontend tests prove workspace switch movement details.

**Evidence:** The known-view frontend test asserts `cli-agent-orchestrator`,
`yards`, and `switched` for
`AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT`.

### Clause: `C-TC-4`

**Claim:** Frontend tests prove runtime lifecycle state/context details.

**Evidence:** The known-view frontend test asserts `restarted`, `idle`,
`term-aria-main`, and `yards` for `AGENT_RUNTIME_LIFECYCLE_EVENT`.

### Clause: `C-TC-5`

**Claim:** Proof demonstrates generated-key registration and fallback
preservation.

**Evidence:** The known-view test imports generated constants from
`web/src/generated/caoEventTypeKeys.ts` and renders rows through the real
registry owner; the same test includes `unknownAudit` and asserts
`Experimental Audit Event` still renders through fallback. Existing fallback
test continues to prove untaught main and related fallback behavior.

### Clause: `C-TC-6`

**Claim:** Missing optional payload facts degrade to readable content.

**Evidence:** The known-view frontend test includes
`deliveryWithMissingOptionalFacts` and asserts `Unknown source`,
`No message text recorded`, and `No terminal recorded`.

### Clause: `C-TC-7`

**Claim:** Runtime/backend tests prove delivery payload source/message facts
without backend presentation values.

**Evidence:** `test_notify_publishes_typed_runtime_events_with_provider_causation`
asserts `source_kind` and `message_body` on the runtime delivery event.
`test_agent_identity_timeline_route_returns_participant_index_rows`
asserts timeline `event_data` carries `source_kind` and `message_body`.

### Clause: `C-TC-8`

**Claim:** The exact handoff Verification Command succeeded.

**Evidence:** The exact command ran successfully after implementation:
backend 55 tests passed, frontend 39 tests passed, and `npm run build`
succeeded.

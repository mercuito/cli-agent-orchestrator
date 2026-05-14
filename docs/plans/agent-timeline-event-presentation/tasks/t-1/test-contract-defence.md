# Test Contract Defence — t-1

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Every feature and coding test contract claim needs concrete proof artifact evidence. |

## Feature-Level Test Contract

### Clause: `F-TC-1`

**Claim:** Core typed-payload and fallback proof uses backend identity timeline
API tests and frontend identity timeline component tests, with no backend
presentation value required.

**Evidence:** `test/api/test_agent_identity_routes.py` proves timeline and
related-event responses include `event_data`; `test/events/test_cao_event_persistence.py`
proves persisted records expose typed JSON payload data while preserving typed
event reconstruction; `web/src/test/agent-identity-timeline-panel.test.tsx`
proves untaught main and related events render through fallback. Backend code
contains no presentation value surface.

## Coding Test Contract

### Selected Criteria

**Claim:** Selected proof-quality criteria are satisfied.

**Evidence:** Backend tests use real dispatcher/persistence plus FastAPI test
client surfaces. Persisted event rows are contained by the
`runtime_inbox_db_session` fixture, which creates an in-memory SQLite database
and monkeypatches `SessionLocal`. Frontend tests use the rendered component and
API wrapper surface. The authored unknown `event_data` examples are inline in
the leaf tests. Focused backend/frontend checks were run during development,
and the exact Verification Command succeeded.

### Clause: `C-TC-1`

**Claim:** Backend API tests prove timeline `event_data` and participant role.

**Evidence:** `test_agent_identity_timeline_route_returns_participant_index_rows`
asserts event ids, participant roles, and `event_data` fields including
`issue_title`, `message_body`, `raw_payload`, and delivery `terminal_id`.

### Clause: `C-TC-2`

**Claim:** Backend API tests prove related-event `event_data` without changing
relatedness membership.

**Evidence:** `test_agent_identity_related_events_route_uses_envelope_threads`
asserts existing correlation/direct-effect ids plus `event_data` on the
canonical event, correlation events, direct effects, and direct cause.

### Clause: `C-TC-3`

**Claim:** Persistence tests prove event-log records expose JSON payload data
without losing typed reconstruction.

**Evidence:** `test_persistent_dispatcher_persists_and_reconstructs_linear_event`
asserts `record.event_data` payload facts and `record.event == event`.

### Clause: `C-TC-4`

**Claim:** Frontend API tests prove wrappers preserve `event_data`.

**Evidence:** `web/src/test/api.test.ts` test
`getAgentIdentityTimeline preserves typed event data in returned rows` asserts
the returned timeline row keeps the typed payload object.

### Clause: `C-TC-5`

**Claim:** Frontend component tests prove untaught main timeline fallback
visibility.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx` test
`renders untaught event kinds through fallback views on the timeline and
related panel` asserts event name, participant role, source, correlation, and
primitive payload facts for an unregistered event type.

### Clause: `C-TC-6`

**Claim:** Frontend component tests prove untaught related-event fallback
visibility.

**Evidence:** The same fallback test expands the row and asserts an untaught
direct-effect/correlation related event is visible with payload and cause facts.

### Clause: `C-TC-7`

**Claim:** The exact handoff Verification Command succeeded.

**Evidence:** The exact command ran successfully after implementation:
backend 24 tests passed, frontend 38 tests passed, and `npm run build`
succeeded.

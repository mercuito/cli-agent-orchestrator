# Test Contract Defence — t-1

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [claim-evidence-verifiability](../../../../planning/methodology/criteria/coding-test-contract-defence/claim-evidence-verifiability.md) | Every defence claim must be checkable against concrete test or command evidence. |

## Feature-Level Test Contract

### Clause: `F-TC-1`

**Claim:** Backend proof uses existing in-memory SQLite event-log and API test
patterns to demonstrate identity timeline membership, broadcast visibility,
causation relatedness, correlation relatedness, and zero-participant event
exclusion.

**Evidence:** `test/api/test_agent_identity_routes.py` uses the existing API
`client` fixture and `runtime_inbox_db_session` fixture. The tests publish
typed Linear/runtime CAO events through `CaoEventDispatcher(...,
persist_events=True)` and assert public route responses. The exact Verification
Command passed with `23 passed`.

## Coding Test Contract Criteria

### Criterion: `test-validity-preserved`

**Claim:** Existing tests continue to validate their original target behavior.

**Evidence:** The exact Verification Command includes the pre-existing
identity route and event persistence tests, and all `23` tests passed.

### Criterion: `given-when-then-test-structure`

**Claim:** New multi-step tests keep setup, route invocation, and assertions
separate and readable.

**Evidence:** New API tests create event state with
`_publish_identity_timeline_scenario()`, invoke `client.get(...)`, then assert
response status and JSON. The event-store test publishes an event, then reads
`list_cao_event_participants_by_agent_identity(...)`, then asserts selected
roles.

### Criterion: `public-boundary-proof`

**Claim:** Public API routes are tested directly rather than only testing
service internals.

**Evidence:** API tests invoke
`/agents/identities/implementation_partner/timeline`,
`/agents/identities/reviewer/timeline`, and
`/agents/identities/implementation_partner/events/{event_id}/related` through
the FastAPI test client.

### Criterion: `real-surface-proof-discipline`

**Claim:** Integration risk is covered through real FastAPI routing and the
real in-memory SQLite event-store surface.

**Evidence:** Tests use `TestClientWithHost` from `test/api/conftest.py` and
`runtime_inbox_db_session` from `test/conftest.py`; they publish and query real
SQLAlchemy-backed event-store rows.

### Criterion: `inspectable-authored-inputs`

**Claim:** Behavior-relevant authored roles and envelope values are visible
from leaf tests through explicit helper parameters or inline event inputs.

**Evidence:** Timeline and related-event API tests call
`_publish_identity_timeline_scenario(...)` with explicit
`mention_correlation_id`, `broadcast_partner_role`, `broadcast_reviewer_role`,
and `workspace_correlation_id` values. The isolated-event relatedness test
passes `correlation_id=None` and `causation_id=None` directly to
`_linear_mentioned_event(...)`.

### Criterion: `setup-invariant-ownership`

**Claim:** Valid event setup lives in helper setup, while leaf tests assert the
route or event-store behavior under test.

**Evidence:** `_linear_mentioned_event(...)` builds valid typed Linear events,
and `_publish_identity_timeline_scenario()` owns the repeated event world.
Leaf tests assert timeline, relatedness, and boundary outcomes.

### Criterion: `reusable-test-state`

**Claim:** Repeated timeline scenario state is named and reused.

**Evidence:** `_publish_identity_timeline_scenario()` is reused by timeline,
broadcast, and related-event API tests. `_event_ids(...)` centralizes response
event ID extraction.

### Criterion: `test-through-owner-surfaces`

**Claim:** Tests depend on event persistence and identity route behavior
through owner surfaces.

**Evidence:** Event setup uses public CAO event constructors and
`CaoEventDispatcher(..., persist_events=True)`. API proof uses route calls
through `client.get(...)` and manager-backed identities from
`agent_identity_manager_factory`. Event-store proof uses the public database
facade `db_module.list_cao_event_participants_by_agent_identity(...)`.

### Criterion: `test-artifact-containment`

**Claim:** Persisted event-log artifacts stay contained in the scoped in-memory
SQLite fixture.

**Evidence:** New tests use `runtime_inbox_db_session`, which patches
`db_module.SessionLocal` to a `sqlite://` engine backed by `StaticPool` for the
test lifecycle. No filesystem or shared database path is written.

### Criterion: `test-file-organization`

**Claim:** The target test files remain organized by behavior family.

**Evidence:** New API tests are appended to `test/api/test_agent_identity_routes.py`
with shared helpers before the new route tests. The event-store participant
role proof is placed next to existing participant-index event persistence tests
in `test/events/test_cao_event_persistence.py`.

### Criterion: `verification-scope-discipline`

**Claim:** Focused proof and broader handoff verification were both run.

**Evidence:** Focused red tests were run for the participant-role event-store
read and API route groups. The exact Verification Command then passed with
`23 passed`.

## Coding Test Contract

### Clause: `C-TC-1`

**Claim:** API tests prove the identity timeline route resolves identity status
through the manager and returns selected participant roles.

**Evidence:** `test_agent_identity_timeline_route_returns_participant_index_rows`
asserts `manager.status_calls == ("implementation_partner",)` and checks
timeline `participant_role` values.

### Clause: `C-TC-2`

**Claim:** API tests prove broadcast events appear as one canonical event on
each participant timeline with request-specific roles.

**Evidence:** `test_agent_identity_timeline_route_preserves_broadcast_viewpoint`
asserts the same broadcast event ID appears with `mentioned` for
`implementation_partner` and `observer` for `reviewer`.

### Clause: `C-TC-3`

**Claim:** API tests prove zero-participant workspace events do not appear on
an identity timeline while existing in the event log.

**Evidence:** `test_agent_identity_timeline_route_returns_participant_index_rows`
publishes a `RuntimeWorkspaceEvent` and asserts its event ID is absent from the
identity timeline response, then asserts
`db_module.get_cao_event(str(workspace.event_id)) is not None`.

### Clause: `C-TC-4`

**Claim:** API tests prove correlation and causation related-event reads return
envelope-based related records.

**Evidence:** `test_agent_identity_related_events_route_uses_envelope_threads`
asserts correlation events include the mention and delivery sharing a
correlation ID, and causation direct effects/direct cause follow the event
causation ID.

### Clause: `C-TC-5`

**Claim:** API tests prove unknown identity, unknown event, and empty
relatedness boundary cases.

**Evidence:** `test_agent_identity_timeline_route_unknown_identity_returns_404`
asserts unknown identity `404`.
`test_agent_identity_related_events_route_handles_missing_relatedness_and_unknown_event`
asserts empty correlation/causation collections for an isolated event and
`404` for a missing event ID.

### Clause: `C-TC-6`

**Claim:** Event-store tests prove selected participant roles come from the
participant index rather than typed body fields.

**Evidence:** `test_agent_identity_timeline_read_exposes_selected_participant_role_from_index`
publishes one event with `implementation_partner` and `reviewer` participant
roles, then asserts the public participant read returns the selected role for
each identity.

### Clause: `C-TC-7`

**Claim:** The exact Verification Command from the handoff passed before
completion.

**Evidence:** `uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py` completed with `23 passed`.

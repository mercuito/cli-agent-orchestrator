# Coding Implementation Plan — t-1

## Research Findings

Investigated:

- `src/cli_agent_orchestrator/api/main.py` for existing `/agents/identities` route placement, response models, and error mapping.
- `src/cli_agent_orchestrator/services/agent_identity_manager.py` for the manager-owned identity status and resolution surface.
- `src/cli_agent_orchestrator/clients/cao_event_store.py` for durable CAO event persistence, participant index, correlation lookup, and causation lookup.
- `src/cli_agent_orchestrator/events/__init__.py` for `AgentParticipant`, `agent_participants_for`, and CAO event envelope primitives.
- `test/api/test_agent_identity_routes.py`, `test/events/test_cao_event_persistence.py`, and shared fixtures for existing API and in-memory SQLite event-log test patterns.

Learned:

- Existing identity routes call `default_agent_identity_manager().list_statuses(...)` and `.status_for_identity(...)`, mapping `AgentIdentityConfigError` to dashboard-facing `404` for one-identity reads.
- The event store already persists canonical event envelope facts and a first-class participant index, and it exposes public reads by agent identity, correlation ID, causation ID, source, event name, and event ID.
- The current identity event read returns `CaoEventRecord` only; it does not expose the selected identity's participant role even though that role is stored in `cao_event_agent_participants`.
- Existing event tests already create realistic Linear/runtime events through public event constructors and `CaoEventDispatcher(..., persist_events=True)`.

Risks and unknowns:

- The backend route shape is not pre-existing. The implementation will introduce focused routes under the existing `/agents/identities/{agent_id}` area so later UI tasks can consume one identity timeline and related event threads without frontend work in this slice.
- The event-store participant timeline read must stay generic enough for durable event-log ownership while avoiding dashboard-specific response concerns in the store.

## High-Level Architecture

Surface shape:

- Extend `cli_agent_orchestrator.clients.cao_event_store` with a public `CaoEventParticipantRecord` dataclass and `list_cao_event_participants_by_agent_identity(agent_identity_id: str)` read. The shape pairs a `CaoEventRecord` with the participant role from the selected identity's participant-index row.
- Add `cli_agent_orchestrator.services.agent_identity_timeline` as a focused backend service that composes identity manager status reads with event-store timeline, correlation, and causation reads. Its public surface will provide timeline and related-thread reads for the API.
- Extend `src/cli_agent_orchestrator/api/main.py` with response models and routes:
  - `GET /agents/identities/{agent_id}/timeline`
  - `GET /agents/identities/{agent_id}/events/{event_id}/related`

Data flow:

- The route asks the identity manager for `status_for_identity(agent_id)`.
- The timeline service asks the event store for participant records for that identity and maps each participant record into an API response row carrying envelope facts and participant role.
- The related route first resolves the identity through the manager, then resolves the canonical event by ID. It uses the event's `correlation_id` and `causation_id` to read correlation siblings, direct cause, and directly caused events from the event store. Empty relatedness remains an empty collection.
- Typed event payloads are reconstructed by the event store as existing behavior, but timeline membership, selected role, and related membership are selected from participant-index and envelope columns only.

Reuse points:

- Existing `AgentIdentityStatusResponse.from_status(...)` for identity details in timeline responses.
- Existing `default_agent_identity_manager()` route pattern and `AgentIdentityConfigError` handling.
- Existing `db_module` event-store facade imports from `cli_agent_orchestrator.clients.database`.
- Existing API `TestClient` fixture, in-memory SQLite `runtime_inbox_db_session`, `_linear_mentioned_event`, and runtime event factories.

## Sub-Task List

1. Add failing event-store proof for participant-role timeline reads.
   - Clauses satisfied: `F-CC-2`, `F-TC-1`, `C-CC-2`, `C-TC-6`, `test-validity-preserved`, `red-green-refactor`, `test-through-owner-surfaces`.
   - Done condition: Focused event-store test fails because no public participant timeline read exists.
   - Dependency order: First.

2. Add failing API proof for identity timeline rows, broadcasts, zero-participant exclusion, and unknown identity handling.
   - Clauses satisfied: `F-CC-1`, `F-CC-2`, `F-TC-1`, `C-CC-1`, `C-CC-2`, `C-CC-4`, `C-TC-1`, `C-TC-2`, `C-TC-3`, `C-TC-5`.
   - Done condition: Focused API tests fail because the timeline route/service does not exist.
   - Dependency order: After sub-task 1 can share fixture conventions, before production route implementation.

3. Implement participant-role event-store read.
   - Clauses satisfied: `F-CC-2`, `C-CC-2`, `C-CC-4`, `prefer-public-surfaces`, `readable-and-explicit`.
   - Done condition: Event-store participant-role test passes without changing existing event-log behavior.
   - Dependency order: After sub-task 1.

4. Implement identity timeline service and API route.
   - Clauses satisfied: `F-CC-1`, `F-CC-2`, `C-CC-1`, `C-CC-2`, `C-CC-4`, `C-CC-5`, `service-definition-surface`, `service-export-discipline`, `well-defined-service`, `minimal-cohesive-changes`.
   - Done condition: Timeline API tests pass and route handlers remain thin.
   - Dependency order: After sub-task 3.

5. Add failing API proof for related-event reads by correlation and causation, including unknown event and empty relatedness cases.
   - Clauses satisfied: `F-CC-2`, `F-TC-1`, `C-CC-3`, `C-TC-4`, `C-TC-5`, `boundary-and-failure-testing`.
   - Done condition: Focused API tests fail because related-event route/service behavior does not exist yet.
   - Dependency order: After timeline service route shape exists.

6. Implement related-event service and API route.
   - Clauses satisfied: `F-CC-2`, `C-CC-3`, `C-CC-4`, `C-CC-5`, `readable-and-explicit`, `no-test-only-production-seams`.
   - Done condition: Related-event API tests pass using event-store correlation and causation reads only.
   - Dependency order: After sub-task 5.

7. Refactor and verify.
   - Clauses satisfied: `full-verification-required`, `semantic-continuity`, `no-unnecessary-duplication`, `respect-ownership-boundaries`, `respect-standing-decisions`, `C-TC-7`.
   - Done condition: The exact Verification Command succeeds: `uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py`.
   - Dependency order: Last.

## Revision Log

No revisions yet.

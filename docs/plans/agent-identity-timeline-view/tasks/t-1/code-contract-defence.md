# Code Contract Defence — t-1

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [claim-evidence-verifiability](../../../../planning/methodology/criteria/coding-code-contract-defence/claim-evidence-verifiability.md) | Every defence claim must be checkable against concrete code or command evidence. |
| [promotion-draft-durability](../../../../planning/methodology/criteria/coding-code-contract-defence/promotion-draft-durability.md) | This defence proposes route-shape decisions that later UI tasks should inherit. |

## Feature-Level Code Contract

### Clause: `F-CC-1`

**Claim:** Timeline and related-event API reads resolve configured identities
through the same manager-owned surface as `/agents/identities`.

**Evidence:** `get_agent_identity_timeline_endpoint(...)` constructs
`AgentIdentityTimelineService(default_agent_identity_manager())` in
`src/cli_agent_orchestrator/api/main.py:579`, and
`AgentIdentityTimelineService.timeline_for_identity(...)` calls
`self._identity_manager.status_for_identity(agent_id)` before reading events in
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:66`.
`related_events_for_identity_event(...)` also calls
`self._identity_manager.status_for_identity(agent_id)` before event lookup in
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:84`.

### Clause: `F-CC-2`

**Claim:** Timeline membership and related-thread reads use durable event-log
participant, correlation, and causation lookups, not typed event body
inspection.

**Evidence:** Timeline reads call
`db_module.list_cao_event_participants_by_agent_identity(...)` in
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:69`, which joins
`CaoEventAgentParticipantModel` to `CaoEventModel` and returns participant
roles in `src/cli_agent_orchestrator/clients/cao_event_store.py:195`.
Related reads call `db_module.get_cao_event(...)`,
`db_module.list_cao_events_by_correlation_id(...)`, and
`db_module.list_cao_events_by_causation_id(...)` in
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:88`,
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:95`, and
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:100`.

## Coding Code Contract Criteria

### Criterion: `full-verification-required`

**Claim:** The exact Verification Command ran successfully before completion.

**Evidence:** `uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py` completed with `23 passed`.

### Criterion: `red-green-refactor`

**Claim:** Testable backend behavior was introduced through failing focused
proof before production code, then made green and cleaned up.

**Evidence:** The event-store focused test first failed with missing
`list_cao_event_participants_by_agent_identity(...)`; after the event-store
implementation, the focused test passed. The API focused route tests first
failed with `404 Not Found`; after adding the service and routes, those tests
passed. The final exact Verification Command passed with `23 passed`.

### Criterion: `boundary-and-failure-testing`

**Claim:** The new API boundaries cover invalid and empty input cases.

**Evidence:** `test_agent_identity_timeline_route_unknown_identity_returns_404`
asserts unknown identity handling in `test/api/test_agent_identity_routes.py`.
`test_agent_identity_related_events_route_handles_missing_relatedness_and_unknown_event`
asserts unknown event `404` and empty correlation/causation collections.

### Criterion: `semantic-continuity`

**Claim:** The new routes extend the existing identity route area and reuse the
existing event-store read semantics.

**Evidence:** The routes are added under `/agents/identities/{agent_id}` in
`src/cli_agent_orchestrator/api/main.py:579` and
`src/cli_agent_orchestrator/api/main.py:599`, next to the existing identity
routes. The service uses the existing `database` event-store facade rather than
adding a parallel persistence path.

### Criterion: `minimal-cohesive-changes`

**Claim:** The implementation stayed inside the backend/API/event-read `t-1`
slice.

**Evidence:** Changed production files are limited to API, event-store facade,
event-store read surface, and the new backend timeline service. No files under
`web/`, `src/cli_agent_orchestrator/web_ui`, or `tasks/t-2` / `tasks/t-3`
were modified.

### Criterion: `no-unnecessary-duplication`

**Claim:** Existing manager, event-store, event constructors, and test fixtures
were reused rather than creating a duplicate identity or event discovery path.

**Evidence:** The service consumes `AgentIdentityManager` and `db_module`
public event-store functions. Tests reuse the existing API `client` fixture,
`runtime_inbox_db_session`, public CAO event constructors, and
`CaoEventDispatcher(..., persist_events=True)`.

### Criterion: `respect-ownership-boundaries`

**Claim:** Backend timeline composition is owned by a focused service, generic
participant-index reads stay in the event store, and HTTP serialization stays
in the API layer.

**Evidence:** `src/cli_agent_orchestrator/services/agent_identity_timeline.py`
owns composition. `src/cli_agent_orchestrator/clients/cao_event_store.py:195`
owns the generic participant-index read. `src/cli_agent_orchestrator/api/main.py:230`
owns FastAPI response models.

### Criterion: `prefer-public-surfaces`

**Claim:** Cross-boundary reads use public manager and event-store surfaces.

**Evidence:** Identity reads use `AgentIdentityManager.status_for_identity`.
Event reads use the `cli_agent_orchestrator.clients.database` facade exports
added in `src/cli_agent_orchestrator/clients/database.py:21` and
`src/cli_agent_orchestrator/clients/database.py:193`.

### Criterion: `respect-standing-decisions`

**Claim:** The implementation does not contradict committed implementation
decisions.

**Evidence:** The committed-decision ledger had no promoted decisions before
implementation, so there were no binding entries to violate.

### Criterion: `readable-and-explicit`

**Claim:** Names and types make timeline filtering, participant role selection,
and related-event grouping explicit.

**Evidence:** Public names include `CaoEventParticipantRecord`,
`list_cao_event_participants_by_agent_identity`, `TimelineEventRead`,
`IdentityTimelineRead`, `RelatedEventsRead`, and
`CausationRelatedEventsRead`.

### Criterion: `service-definition-surface`

**Claim:** The new service has an obvious definition surface with public read
methods and owned read dataclasses grouped near the top.

**Evidence:** `src/cli_agent_orchestrator/services/agent_identity_timeline.py:20`
defines read dataclasses, and
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:60` defines
`AgentIdentityTimelineService` with the two public methods consumed by the API.

### Criterion: `service-export-discipline`

**Claim:** New public exports are required by current consumers and do not
expose internal helpers.

**Evidence:** The API imports only service entrypoints and read dataclasses in
`src/cli_agent_orchestrator/api/main.py:61`. The event-store facade exports
`CaoEventParticipantRecord` and
`list_cao_event_participants_by_agent_identity` in
`src/cli_agent_orchestrator/clients/database.py:21` and
`src/cli_agent_orchestrator/clients/database.py:193`; `_timeline_event_from_record`
is not exported.

### Criterion: `well-defined-service`

**Claim:** `AgentIdentityTimelineService` is a well-defined backend read
service whose owner is the agent identity timeline read surface.

**Evidence:** The service is placed under `services`, accepts an
`AgentIdentityManager`, exposes timeline and related-event read methods, and
returns service-owned dataclasses without owning HTTP concerns.

### Criterion: `no-test-only-production-seams`

**Claim:** Production seams added by the task serve the dashboard read surface,
not only the tests.

**Evidence:** The service is invoked by the new API routes in
`src/cli_agent_orchestrator/api/main.py:586` and
`src/cli_agent_orchestrator/api/main.py:609`. No test-only constructors or
unsafe bypasses were added.

## Coding Code Contract

### Clause: `C-CC-1`

**Claim:** The identity timeline API resolves identity status through
`default_agent_identity_manager().status_for_identity(...)` and returns `404`
for manager resolution failures.

**Evidence:** API route construction uses `default_agent_identity_manager()` in
`src/cli_agent_orchestrator/api/main.py:586`, and the service calls
`status_for_identity(...)` in
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:69`.
`AgentIdentityConfigError` maps to `404` in
`src/cli_agent_orchestrator/api/main.py:590`.

### Clause: `C-CC-2`

**Claim:** Timeline rows expose envelope facts and selected participant role
from the participant index.

**Evidence:** `AgentIdentityTimelineEventResponse` fields are declared in
`src/cli_agent_orchestrator/api/main.py:230`. The service maps
`participant_record.participant_role` into `TimelineEventRead` in
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:76`.

### Clause: `C-CC-3`

**Claim:** Related-event reads resolve a canonical event by ID, then use
correlation and causation lookup surfaces.

**Evidence:** `related_events_for_identity_event(...)` calls
`db_module.get_cao_event(event_id)`, then correlation and causation reads in
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:88` through
`src/cli_agent_orchestrator/services/agent_identity_timeline.py:100`.

### Clause: `C-CC-4`

**Claim:** The production service keeps route handlers thin and exposes only
consumer-facing read methods.

**Evidence:** Route handlers construct the service and convert service reads
to response models in `src/cli_agent_orchestrator/api/main.py:583` and
`src/cli_agent_orchestrator/api/main.py:603`. Composition logic is in
`src/cli_agent_orchestrator/services/agent_identity_timeline.py`.

### Clause: `C-CC-5`

**Claim:** The implementation did not change frontend, live-refresh, generated
web assets, or `t-2`/`t-3` artifacts.

**Evidence:** `git status --short` shows changed files only in backend source,
tests, and `tasks/t-1` artifacts.

## Committed Implementation Decisions

No committed implementation decisions were in force before this task.

## Committed-Decision Promotion Draft

- `cid-1`: The backend identity timeline read route is
  `GET /agents/identities/{agent_id}/timeline`. It resolves the identity
  through the manager-owned identity surface and returns an `identity` object
  plus `events` rows carrying event envelope fields and the selected
  identity's `participant_role`.
- `cid-2`: The backend related-event read route is
  `GET /agents/identities/{agent_id}/events/{event_id}/related`. It resolves
  the identity through the manager-owned identity surface, resolves the
  canonical CAO event by ID, and returns `event`, `correlation_events`, and
  `causation_events` with `direct_cause` and `direct_effects`; missing
  relatedness is represented as `null` / empty arrays rather than fabricated
  events.

# CAO-90 Framework-Wide Typed Event Core

## CAO-90 Feature Task Handoff

Source of truth: Linear issue CAO-90.

Scope:

- Add a CAO-owned event core at `cli_agent_orchestrator.events`.
- Provide structural event protocols and typed metadata primitives for event
  ids, source refs, correlation ids, causation ids, and occurred-at timestamps.
- Provide `AgentParticipant`, `WithAgentParticipants`, participant extraction,
  and agent-involvement helpers.
- Provide a synchronous dispatcher that registers typed event classes and
  publishes concrete event instances to all-event and concrete-type
  subscribers.
- Keep Linear/provider event behavior unchanged in this phase.

Out of scope:

- Migrating Linear or `workspace_providers.events` to the new core.
- Publishing provider events through both event systems.
- Defining global participant role values.
- Dict-shaped primary event payloads.

## Committed Implementation Decisions

- The framework-wide event core is owned by `cli_agent_orchestrator.events`,
  not `workspace_providers`.
- Concrete events are structural typed objects: dataclasses are supported, but
  inheritance from a CAO base event class is not required.
- Event families own their own string `event_name` and optional participant `role`
  vocabulary.
- Event-class registration validates the typed CAO metadata annotations before
  an event class can be published.
- Linear remains on its existing provider event dispatcher until a later
  migration slice.

## CAO-90 Coding Implementation Plan

1. Read CAO-90, the criteria catalog, and the existing
   `workspace_providers.events` reference.
2. Add the CAO-owned event core with typed metadata, participant facets,
   helpers, dispatcher, publication result, and a bounded public export surface.
3. Add focused tests for registration/publication, all-event and concrete
   subscribers, participant helpers, type-oriented protocol usage, and invalid
   boundary inputs.
4. Run focused formatting, type checking, event/provider tests, Linear-adjacent
   regression tests, and the full non-e2e suite.
5. Dispatch a reviewer and address grounded findings.

## Selected Criteria

Coding code criteria:

- `full-verification-required`: CAO-90 adds production code and requires
  focused and broader proof before handoff.
- `minimal-cohesive-changes`: the slice adds only the new event core, focused
  tests, and this plan/defence artifact.
- `no-unnecessary-duplication`: the existing provider dispatcher informed the
  shape, but Linear/provider code remains unmoved as required.
- `respect-ownership-boundaries`: framework primitives live under
  `cli_agent_orchestrator.events`; provider behavior stays in provider owners.
- `readable-and-explicit`: validation, publication, and participant helpers
  use named types and explicit error paths.
- `respect-standing-decisions`: CAO-90 explicitly leaves Linear behavior
  unchanged and avoids duplicate provider event publication.
- `boundary-and-failure-testing`: dispatcher registration/publication and
  participant helpers accept runtime inputs and define failure behavior.
- `centralized-vocabulary`: CAO event metadata vocabulary and public names are
  centralized in the event core.
- `prefer-public-surfaces`: tests import through `cli_agent_orchestrator.events`.
- `red-green-refactor`: focused tests were added before the event core existed,
  first failing on the missing public package.
- `service-definition-surface`, `service-export-discipline`,
  `well-defined-service`: `cli_agent_orchestrator.events` is the public service
  surface and declares `__all__` for consumer-facing exports.

Coding test criteria:

- `test-validity-preserved`: existing provider and Linear tests continue to
  pass without assertion changes.
- `verification-scope-discipline`: focused event tests, Linear-adjacent tests,
  type checks, format checks, and full non-e2e pytest were run.
- `reusable-test-state`: shared event factories and typed constants keep
  repeated setup named.
- `test-through-owner-surfaces`: tests exercise the public event package and
  dispatcher rather than private helpers.
- `public-boundary-proof`: tests import the new exported package surface and
  prove the dispatcher front door.
- `given-when-then-test-structure`: multi-step dispatcher tests keep setup,
  subscription/publication, and assertions visible.
- `setup-invariant-ownership`: helper factories own valid CAO event metadata so
  leaf tests can focus on behavior.

## CAO-90 Coding Completion Report

Implemented files:

- `src/cli_agent_orchestrator/events/__init__.py`
- `test/events/test_core.py`
- `docs/plans/cao-90-framework-wide-event-core.md`

Verification commands:

- `uv run pytest test/events/test_core.py -q` initially failed because the
  public package did not exist.
- `uv run black --check src/cli_agent_orchestrator/events test/events/test_core.py`
- `uv run isort --check-only src/cli_agent_orchestrator/events test/events/test_core.py`
- `uv run mypy src/cli_agent_orchestrator/events test/events/test_core.py`
- `uv run pytest test/events/test_core.py test/workspace_providers/test_events.py -q`
- `uv run pytest test/events/test_core.py test/workspace_providers/test_events.py test/api/test_linear_app_routes.py test/services/test_linear_agent_runtime_service.py test/linear -q --no-cov`
- `uv run pytest -q --no-cov`

Reviewer result:

- Code reviewer requested stricter event-class registration, an explicit
  service export surface, and a persisted CAO-90 plan/defence artifact.
- Registration now rejects malformed event classes before they can be
  registered.
- `cli_agent_orchestrator.events` now declares `__all__`.
- This plan/defence artifact records the selected criteria and verification
  claim surface.

## CAO-90 Code Contract Defence

- Typed event metadata is represented by `NewType` aliases and
  `CaoEventSourceRef`, and validated at publish time.
- `CaoEvent` and `WithAgentParticipants` are protocols with read-only
  properties so frozen dataclass events satisfy the public contracts without
  inheriting from framework base classes.
- Concrete event classes must declare typed CAO metadata annotations before
  registration succeeds.
- Concrete event instances must satisfy `CaoEvent`, have non-empty ids, source
  refs, optional non-empty correlation/causation ids, and timezone-aware
  `occurred_at` values before publication succeeds.
- `AgentParticipant` keeps roles as optional event-family-owned strings, and
  participant helper validation is centralized in the event core.
- The dispatcher stores broad and concrete subscriptions in registration order
  and publishes only to matching subscribers.
- The new code does not import or invoke Linear/provider event publishers, so
  it cannot duplicate provider events in this phase.

## CAO-90 Test Contract Defence

- `test_dispatcher_registers_and_publishes_concrete_typed_events` proves
  registration, concrete subscription, typed handler field access, publication
  results, and unknown subscription failure.
- `test_dispatcher_supports_all_event_and_concrete_type_subscribers_in_order`
  proves all-event subscribers and concrete event-type subscribers both receive
  matching events in subscription order.
- `test_participant_helpers_cover_zero_one_and_many_agent_participants` proves
  participant extraction and identity matching for zero, one, and many
  participants.
- `test_generic_timeline_code_can_reason_through_event_protocols` gives a
  mypy-friendly example for generic code using `CaoEvent` and
  `WithAgentParticipants`.
- `test_dispatcher_rejects_unregistered_or_malformed_event_instances` and
  `test_event_metadata_and_participant_values_must_be_non_empty` prove
  registration/publication failure paths and metadata boundary validation.
- Existing `workspace_providers` and Linear tests prove this phase did not
  change provider event routing behavior.

## Review Readiness Command

```bash
uv run black --check src/cli_agent_orchestrator/events test/events/test_core.py && \
uv run isort --check-only src/cli_agent_orchestrator/events test/events/test_core.py && \
uv run mypy src/cli_agent_orchestrator/events test/events/test_core.py && \
uv run pytest test/events/test_core.py test/workspace_providers/test_events.py -q && \
uv run pytest test/events/test_core.py test/workspace_providers/test_events.py test/api/test_linear_app_routes.py test/services/test_linear_agent_runtime_service.py test/linear -q --no-cov && \
uv run pytest -q --no-cov
```

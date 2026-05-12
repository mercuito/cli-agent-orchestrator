# CAO-92 CAO Runtime Events

## CAO-92 Feature Task Handoff

Source of truth: Linear issue CAO-92.

Scope:

- Add CAO-owned runtime event types for agent identity notification and
  lifecycle boundaries that are actually emitted by this slice.
- Publish those runtime events through `cli_agent_orchestrator.events`, the same
  framework-wide dispatcher used by Linear after CAO-91.
- Instrument `AgentRuntimeHandle` and adjacent runtime paths where facts become
  true: notification acceptance, terminal delivery or deferral, runtime
  start/reuse/refresh/failure, and workspace context switch success or deferral.
- Preserve causation/correlation from provider-originated events where the
  triggering CAO event is available.
- Prove every emitted event has typed fields and `agent_participants` for
  identity filtering.

Out of scope:

- Dashboard timeline projection or UI.
- Wholesale log-to-event conversion.
- Placeholder runtime event classes that are not emitted.
- Duplicate publication for retries or idempotent paths.
- Reworking Linear's CAO event migration from CAO-91.

Assigned behavioral slice:

- CAO can observe framework-owned agent notification and runtime lifecycle
  facts through the same event system as provider events.
- A generic consumer can filter these events by involved agent identity without
  knowing the concrete runtime event type.
- A concrete consumer can still use typed runtime event fields directly.

Assigned Feature Code Contract slice:

- Runtime events belong to the CAO framework/runtime ownership surface, not
  Linear or `workspace_providers`.
- Event families own their event names and participant role strings.
- Concrete events must be typed dataclass-style objects satisfying the CAO event
  protocols rather than dict-shaped payloads.
- Publication must occur at owner surfaces where the runtime fact becomes true.
- The implementation must not keep speculative unused event classes.

Assigned Feature Test Contract slice:

- Tests must cover every emitted runtime event type, typed fields, and
  `agent_participants`.
- Tests must prove useful success, deferred, and failure paths for the emitted
  set.
- Tests must prove provider-caused runtime events preserve correlation and
  causation when available.
- Existing runtime freshness, inbox delivery, Linear notification, and
  workspace-context behavior must continue to pass.

Deterministic task artifact paths:

- Feature Task Handoff:
  `docs/plans/cao-92-cao-runtime-events.md`
- Coding Code Contract:
  `docs/plans/cao-92-cao-runtime-events.md#cao-92-coding-code-contract`
- Coding Test Contract:
  `docs/plans/cao-92-cao-runtime-events.md#cao-92-coding-test-contract`
- Coding Implementation Plan:
  `docs/plans/cao-92-cao-runtime-events.md#cao-92-coding-implementation-plan`
- Coding Completion Report:
  `docs/plans/cao-92-cao-runtime-events.md#cao-92-coding-completion-report`
- Behavioral Contract Defence:
  `docs/plans/cao-92-cao-runtime-events.md#cao-92-behavioral-contract-defence`
- Code Contract Defence:
  `docs/plans/cao-92-cao-runtime-events.md#cao-92-code-contract-defence`
- Test Contract Defence:
  `docs/plans/cao-92-cao-runtime-events.md#cao-92-test-contract-defence`

## Committed Implementation Decisions

- CAO-90 established `cli_agent_orchestrator.events` as the framework-wide
  event system.
- CAO-90 established structural typed event protocols instead of inheritance as
  the composition mechanism.
- CAO-90 established that event families own participant role strings.
- CAO-91 established that Linear provider events publish through
  `cli_agent_orchestrator.events` only.
- CAO-92 runtime events must live under CAO runtime/framework ownership and must
  not reintroduce provider-only dispatch paths.
- CAO-92 should implement only event classes that are emitted by the completed
  slice.

## CAO-92 Coding Code Contract

Selected criteria:

- `full-verification-required`: this slice changes production runtime code.
- `minimal-cohesive-changes`: changes should stay within runtime event types,
  runtime publication points, and direct proof updates.
- `no-unnecessary-duplication`: event builders, participant construction, and
  metadata propagation should avoid copy/pasted classification logic.
- `respect-ownership-boundaries`: CAO runtime event ownership belongs under
  runtime/framework surfaces; Linear remains provider-owned.
- `readable-and-explicit`: runtime event names, typed fields, and publication
  points should make the fact being recorded obvious.
- `respect-standing-decisions`: CAO-90 and CAO-91 event-system decisions remain
  in force.
- `semantic-continuity`: existing runtime, inbox, notification, and workspace
  context behavior should be extended without changing user-visible behavior
  except event publication.
- `boundary-and-failure-testing`: runtime publication claims success, deferred,
  and failure semantics.
- `centralized-vocabulary`: runtime event names and role strings should live in
  a single runtime-owned module/surface.
- `prefer-public-surfaces`: consumers and tests should use public CAO event and
  runtime owner surfaces.
- `service-export-discipline`: any new runtime event exports must be deliberate
  and bounded.
- `no-test-only-production-seams`: do not widen production APIs solely for test
  convenience.

## CAO-92 Coding Test Contract

Selected criteria:

- `test-validity-preserved`: existing behavior tests remain meaningful.
- `verification-scope-discipline`: run focused runtime event proof plus broader
  runtime/Linear/inbox regression checks.
- `reusable-test-state`: shared setup should own valid runtime identities,
  notifications, events, and workspace context fixtures when repeated.
- `test-through-owner-surfaces`: tests should prove publication through runtime
  owner flows rather than calling private helpers as the only proof.
- `real-surface-proof-discipline`: runtime behavior crosses persistence,
  dispatch, terminal, and provider-adjacent surfaces.
- `public-boundary-proof`: event exports and dispatcher publication are public
  CAO boundaries.
- `given-when-then-test-structure`: multi-step runtime delivery/switch tests
  should keep setup, action, and assertions visible.
- `setup-invariant-ownership`: helper setup owns valid identities, terminals,
  and notifications so tests can focus on event facts.

## CAO-92 Coding Implementation Plan

1. Inspect `cli_agent_orchestrator.runtime.agent`, inbox delivery, Linear
   runtime integration, and workspace-context owner flows to identify the
   existing fact boundaries.
2. Add a runtime-owned CAO event module/export surface with only concrete events
   emitted by this slice.
3. Register runtime event types with the default CAO dispatcher at the same
   owner boundary pattern used after CAO-91.
4. Publish typed events at selected success/deferred/failure runtime facts while
   preserving causation and correlation when available.
5. Add focused tests for every emitted event's typed fields, agent participants,
   correlation/causation, and owner-surface publication.
6. Run the Review Readiness Command and fill in the completion report and
   contract defences.
7. Dispatch required reviewers and address grounded findings.

## CAO-92 Coding Completion Report

To be completed by the implementer.

## CAO-92 Behavioral Contract Defence

To be completed by the implementer.

## CAO-92 Code Contract Defence

To be completed by the implementer.

## CAO-92 Test Contract Defence

To be completed by the implementer.

## Review Readiness Command

```bash
uv run black --check src/cli_agent_orchestrator/runtime src/cli_agent_orchestrator/events test/runtime test/services/test_linear_agent_runtime_service.py test/services/test_inbox_service.py test/integration/test_agent_runtime_provider_state.py && \
uv run isort --check-only src/cli_agent_orchestrator/runtime src/cli_agent_orchestrator/events test/runtime test/services/test_linear_agent_runtime_service.py test/services/test_inbox_service.py test/integration/test_agent_runtime_provider_state.py && \
uv run mypy src/cli_agent_orchestrator/runtime src/cli_agent_orchestrator/events && \
uv run pytest test/events/test_core.py test/runtime test/services/test_inbox_service.py test/services/test_linear_agent_runtime_service.py test/integration/test_agent_runtime_provider_state.py -q --no-cov && \
uv run pytest test/linear -q --no-cov
```

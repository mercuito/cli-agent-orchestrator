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
2. Add `cli_agent_orchestrator.runtime.events` as the runtime-owned event
   vocabulary and bounded export surface. The emitted event set for this slice
   is:
   - `AgentRuntimeNotificationAcceptedEvent`, emitted only when the runtime
     accepts a newly durable notification for an agent identity.
   - `AgentRuntimeNotificationDeliveryEvent`, emitted when a runtime
     notification delivery fact becomes observable: delivered, deferred, or
     failed for the accepted notification.
   - `AgentRuntimeLifecycleEvent`, emitted from freshness reconciliation when
     the runtime is started, reused, refreshed/restarted, deferred, or failed.
   - `AgentRuntimeWorkspaceContextSwitchEvent`, emitted when switching away
     from another workspace context succeeds, defers because the other runtime
     is busy/waiting, or fails.
3. Keep participant vocabulary centralized in the runtime event module. All
   emitted events expose `agent_participants` for the involved identity using
   runtime-owned role strings.
4. Register runtime event types with the default CAO dispatcher at runtime
   publication boundaries, matching CAO-91's owner-surface registration pattern.
5. Extend `AgentRuntimeHandle.notify` and `accept_notification` with optional
   CAO provider event context. Linear passes the triggering
   `LinearIssueContextEvent` where available; runtime events copy
   `correlation_id` and set `causation_id` from the provider event id without
   adding Linear-owned event classes or dispatch paths.
6. Publish at owner surfaces where facts become true:
   - notification accepted after `_create_or_get_notification` or
     `accept_notification` confirms a newly durable notification;
   - delivery event after the scoped notification is delivered, deferred, or
     failed;
   - lifecycle event from `ensure_fresh_started`/freshness reconciliation for
     start, reuse, restart, defer, and fail outcomes;
   - workspace-context switch event inside
     `_deactivate_other_context_terminal_for_switch` for success, deferred,
     and failed switch outcomes.
7. Avoid duplicate publication by gating notification accepted and
   notification delivery events on the scoped notification's first observable
   transition: no accepted event when idempotency returns an existing
   notification, no delivery event for already-delivered notifications, and no
   additional event when Linear retry paths only re-encounter prior state.
8. Add focused tests for every emitted event's typed fields, direct field access,
   `agent_participants`, provider correlation/causation, useful
   success/deferred/failure outcomes, workspace-context switch outcomes, and
   idempotent duplicate suppression.
9. Run the Review Readiness Command and fill in the completion report and
   contract defences.
10. Dispatch required reviewers and address grounded findings.

## CAO-92 Coding Completion Report

- Status: implemented and verified.
- Repo-local methodology source: this checkout does not contain
  `docs/planning/methodology/*`; CAO-92 used this persisted handoff plus
  `docs/criteria/*` as the repo-local methodology source per dispatch
  instruction.
- Files changed:
  - `src/cli_agent_orchestrator/runtime/events.py`
  - `src/cli_agent_orchestrator/runtime/agent.py`
  - `src/cli_agent_orchestrator/runtime/__init__.py`
  - `src/cli_agent_orchestrator/linear/runtime.py`
  - `test/runtime/test_agent_runtime.py`
  - `test/services/test_linear_agent_runtime_service.py`
  - `test/linear/test_monitor.py`
  - `docs/plans/cao-92-cao-runtime-events.md`
- Implemented emitted runtime events:
  - `AgentRuntimeNotificationAcceptedEvent`: emitted only for newly durable
    runtime notifications.
  - `AgentRuntimeNotificationDeliveryEvent`: emitted when the scoped
    notification is delivered, deferred, or failed as a new observable delivery
    fact.
  - `AgentRuntimeLifecycleEvent`: emitted for freshness reconciliation start,
    reuse, restart/refresh, deferred, and failed outcomes, and for direct
    `ensure_started()` start/reuse compatibility callers.
  - `AgentRuntimeWorkspaceContextSwitchEvent`: emitted for workspace-context
    switch success, deferred, and failed outcomes.
- Intentionally deferred candidates:
  - No timeline/UI/projection events.
  - No log-derived events.
  - No placeholder runtime taxonomy beyond the four emitted classes above.
  - No retry/idempotency duplicate events for unchanged existing
    notifications.
- Production notes:
  - Runtime event vocabulary, event names, participant roles, builders,
    registration, and publication live under `cli_agent_orchestrator.runtime`.
  - Linear passes its triggering CAO provider event as optional
    `causing_event`; runtime events copy provider `correlation_id` and set
    `causation_id` to the provider event id when available.
  - `test/services/test_linear_agent_runtime_service.py` had a pre-existing
    Black line-wrap diff inside the Review Readiness Command surface. It was
    mechanically formatted so the exact command could run to completion; no
    behavior was changed there except updating one runtime-handle test double
    for the new provider-event context argument.
- Review Readiness Command result:
  - Initial exact run stopped at Black because
    `test/services/test_linear_agent_runtime_service.py` required formatting.
  - After mechanical Black formatting, test-double updates, and reviewer-driven
    direct `ensure_started()` lifecycle proof, the exact command passed:
    `black --check` passed; `isort --check-only` passed; `mypy` passed for
    runtime/events; pytest runtime/inbox/Linear service/integration set passed
    with 88 tests; `pytest test/linear -q --no-cov` passed with 147 tests.
- Focused proof run:
  - `uv run pytest test/runtime/test_agent_runtime.py -q --no-cov` passed with
    42 tests.
- Reviewer tracking:
  - Coding Implementation Plan reviewer `019e1c84-1819-7241-9db8-172266e39e81`
    round 1 requested a concrete emitted event inventory, provider
    causation/correlation route, and duplicate suppression plan; round 2
    approved after plan revision.
  - Behavioral Contract reviewer `019e1c9e-eb48-7793-8040-b7365fcbd554`
    approved in round 1 with no findings.
  - Code Contract reviewer `019e1c9f-bbef-78c1-8938-cff2e993d00a` requested
    direct `ensure_started()` lifecycle publication in round 1; round 2
    approved after the owner-surface lifecycle fix and tests.
  - Test Contract reviewer `019e1ca0-7976-7523-90f1-3800fa5f99af` requested
    participant identity assertions for every emitted event type in round 1;
    round 2 approved after proof updates.
- Committed decision update or promotion draft: none needed. CAO-92 stays
  within existing CAO-90/CAO-91 decisions and adds no new cross-task standing
  decision.
- Acceptance criteria status:
  - Runtime-owned typed event classes added and emitted: satisfied.
  - Direct typed fields rather than dict payloads: satisfied.
  - `agent_participants` for identity filtering with runtime-owned role
    strings: satisfied.
  - Provider-caused correlation/causation preservation: satisfied.
  - No timeline UI/projection, wholesale log events, placeholder classes, or
    duplicate unchanged idempotent notification events: satisfied.
- Residual risks and opportunities:
  - Runtime event publication remains synchronous like the CAO event core;
    subscriber failures propagate as the existing dispatcher contract implies.
  - Direct `ensure_started()` compatibility callers publish the same lifecycle
    event family rather than a separate compatibility event type.

## CAO-92 Behavioral Contract Defence

- Assigned behavior: CAO can observe framework-owned agent notification and
  runtime lifecycle facts through the same event system as provider events.
  Defence: runtime publication uses `cli_agent_orchestrator.events` via
  `register_runtime_cao_events()` and `publish_runtime_event()`. Runtime facts
  are emitted from `AgentRuntimeHandle` where notification acceptance,
  lifecycle freshness, direct start/reuse, delivery outcomes, and
  workspace-context switch outcomes become true. Focused runtime tests subscribe
  through a `CaoEventDispatcher` and assert the emitted runtime event sequence
  for successful delivery, direct start/reuse, startup failure, busy deferral,
  duplicate suppression, and workspace-context switch success/defer.
- Assigned behavior: a generic consumer can filter these events by involved
  agent identity without knowing the concrete runtime event type. Defence:
  every emitted runtime event carries `agent_participants` as
  `tuple[AgentParticipant, ...]` with the involved CAO identity id and a
  runtime-owned role string. Tests assert participant identity and role for
  notification, lifecycle, delivery, and context-switch events.
- Assigned behavior: a concrete consumer can still use typed runtime event
  fields directly. Defence: concrete frozen dataclass events expose direct
  fields such as `agent_identity_id`, `workspace_context_id`,
  `inbox_notification_id`, `terminal_id`, `runtime_status`, `outcome`,
  `action`, `ready`, `fresh`, `from_workspace_context_id`, and
  `to_workspace_context_id`. Tests access these fields directly without
  payload dicts.
- Behavioral constraints: provider-caused events preserve correlation/causation
  when available; retries/idempotent paths do not duplicate unchanged runtime
  notification events. Defence: Linear passes the provider CAO event into
  runtime handle calls; tests assert copied `correlation_id` and
  `causation_id` derived from the provider event id. Duplicate-source tests
  assert no additional accepted, lifecycle, or delivery event is published when
  a retry re-encounters the same pending notification without a new observable
  transition.

## CAO-92 Code Contract Defence

- Feature Code Contract: runtime events belong to CAO runtime/framework
  ownership. Defence: event declarations, vocabulary, builders, registration,
  and publication helpers live in `cli_agent_orchestrator.runtime.events`;
  Linear only supplies optional provider event context to the runtime owner.
- Feature Code Contract: event families own event names and participant role
  strings. Defence: `RUNTIME_CAO_SOURCE_TYPE`,
  `RUNTIME_AGENT_PARTICIPANT_ROLE_*`, event `event_name` values, and
  `RUNTIME_CAO_EVENTS` are centralized in the runtime event module.
- Feature Code Contract: concrete events are typed dataclass-style objects
  satisfying CAO event protocols rather than dict payloads. Defence: four
  frozen dataclass event classes declare typed CAO metadata fields and direct
  runtime fields; no event class subclasses `Mapping` or carries a primary
  payload dict.
- Feature Code Contract: publication occurs at owner surfaces where runtime
  facts become true. Defence: `AgentRuntimeHandle` publishes after durable
  notification creation/acceptance, after scoped delivery outcome refresh,
  from direct `ensure_started()` start/reuse, from freshness reconciliation
  returns, and inside context-switch success, deferred, and failed branches.
- Feature Code Contract: no speculative unused event classes. Defence:
  `RUNTIME_CAO_EVENTS` contains only the four concrete event classes emitted by
  this implementation.
- Coding Code Contract criteria:
  - `full-verification-required`: exact Review Readiness Command passed after
    the noted formatting unblock.
  - `minimal-cohesive-changes`: production edits stay within runtime event
    ownership, runtime publication points, and Linear provider-context
    threading; no UI/projection/log conversion was added.
  - `no-unnecessary-duplication`: event metadata construction, participant
    creation, registration, and publication are centralized in the runtime
    event module.
  - `respect-ownership-boundaries`: Linear retains provider event ownership;
    runtime owns runtime event vocabulary and publication.
  - `readable-and-explicit`: event names, outcome/action fields, and
    publication helper names describe the fact being recorded.
  - `respect-standing-decisions`: implementation uses CAO-90 structural typed
    protocols and CAO-91 framework dispatcher only.
  - `semantic-continuity`: existing runtime delivery, freshness, inbox, Linear
    notification, and workspace-context behavior is preserved; tests assert the
    existing result objects and side effects continue to work.
  - `boundary-and-failure-testing`: tests cover delivered, deferred, failed,
    context-switch success, and context-switch deferred paths.
  - `centralized-vocabulary`: runtime names and roles are in one module.
  - `prefer-public-surfaces`: tests use CAO event dispatcher and runtime owner
    flows rather than private event helper calls as sole proof.
  - `service-export-discipline`: runtime package exports only the four event
    types and `register_runtime_cao_events`.
  - `no-test-only-production-seams`: optional `causing_event` is required by
    production Linear causation propagation, not test convenience.
- Promotion draft/update: none. No standing decision change required.

## CAO-92 Test Contract Defence

- Feature Test Contract: tests cover every emitted runtime event type, typed
  fields, and `agent_participants`. Defence:
  `test_notify_publishes_typed_runtime_events_with_provider_causation` covers
  notification accepted, lifecycle, and delivery event typed fields and
  participant identity/roles; direct `ensure_started()` tests cover lifecycle
  start/reuse typed fields and participant identity; workspace-context tests
  cover switch event typed fields and participant identity/role.
- Feature Test Contract: tests prove useful success, deferred, and failure
  paths for the emitted set. Defence: focused runtime tests prove delivered
  notification on fresh idle runtime, busy delivery deferral, startup failure,
  direct lifecycle start/reuse, workspace-context switch success, and
  workspace-context switch deferral.
- Feature Test Contract: tests prove provider-caused runtime events preserve
  correlation and causation when available. Defence:
  `test_notify_publishes_typed_runtime_events_with_provider_causation` passes a
  real Linear CAO event as `causing_event` and asserts runtime events carry its
  correlation id and causation id.
- Feature Test Contract: existing runtime freshness, inbox delivery, Linear
  notification, and workspace-context behavior continues to pass. Defence: the
  exact Review Readiness Command passed the runtime, inbox, Linear service,
  integration, and `test/linear` suites.
- Coding Test Contract criteria:
  - `test-validity-preserved`: existing assertions remain behavioral; test
    doubles were updated only for the new runtime method signature.
  - `verification-scope-discipline`: focused runtime proof and the full Review
    Readiness Command both ran.
  - `reusable-test-state`: runtime tests reuse existing identity, handle,
    provider, terminal, and new event-recorder fixtures.
  - `test-through-owner-surfaces`: event publication is exercised by
    `AgentRuntimeHandle` flows rather than direct publication helper calls.
  - `real-surface-proof-discipline`: tests exercise database-backed inbox
    notifications, terminal metadata, provider status, runtime state, and
    Linear runtime integration surfaces already covered by the command.
  - `public-boundary-proof`: tests import runtime events through the runtime
    package/module and subscribe through CAO's public dispatcher.
  - `given-when-then-test-structure`: new tests keep setup, runtime action,
    and event assertions visible.
  - `setup-invariant-ownership`: existing fixtures own valid identity,
    terminal, provider, and inbox state.
- Proof risks: runtime publication uses a synchronous in-process dispatcher;
  tests prove publication and field semantics but do not add asynchronous or
  external subscriber isolation because that is outside CAO-92.

## Review Readiness Command

```bash
uv run black --check src/cli_agent_orchestrator/runtime src/cli_agent_orchestrator/events test/runtime test/services/test_linear_agent_runtime_service.py test/services/test_inbox_service.py test/integration/test_agent_runtime_provider_state.py && \
uv run isort --check-only src/cli_agent_orchestrator/runtime src/cli_agent_orchestrator/events test/runtime test/services/test_linear_agent_runtime_service.py test/services/test_inbox_service.py test/integration/test_agent_runtime_provider_state.py && \
uv run mypy src/cli_agent_orchestrator/runtime src/cli_agent_orchestrator/events && \
uv run pytest test/events/test_core.py test/runtime test/services/test_inbox_service.py test/services/test_linear_agent_runtime_service.py test/integration/test_agent_runtime_provider_state.py -q --no-cov && \
uv run pytest test/linear -q --no-cov
```

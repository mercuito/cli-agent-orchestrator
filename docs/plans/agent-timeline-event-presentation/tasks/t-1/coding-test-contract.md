# Coding Test Contract — t-1

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-TC-1` | Feature Test Contract | This task owns the core proof that timeline and related-event responses carry `event_data`, untaught events remain visible through frontend fallback, and backend presentation values are unnecessary. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `test-validity-preserved` | Universal criterion; existing route, persistence, API wrapper, and component tests must keep proving their original behavior. |
| `given-when-then-test-structure` | Backend route and frontend component proofs exercise multi-step setup, read/render action, and visible assertions. |
| `public-boundary-proof` | The task changes HTTP JSON responses and frontend API/component boundaries that downstream code consumes. |
| `real-surface-proof-discipline` | Backend confidence depends on real event persistence plus FastAPI route reads; frontend confidence depends on the rendered component surface. |
| `setup-invariant-ownership` | Existing scenario builders and fixtures own valid CAO events, participant roles, and identity setup. |
| `reusable-test-state` | Frontend timeline tests reuse repeated identity/event worlds that should be extended rather than copied. |
| `test-through-owner-surfaces` | Tests that depend on CAO event persistence should use dispatcher/database owner surfaces instead of fabricating route responses from internals. |
| `inspectable-authored-inputs` | The fallback assertions depend on authored `event_data` examples that must remain visible in the test. |
| `test-artifact-containment` | Backend proof creates persisted CAO event rows inside the isolated `runtime_inbox_db_session` SQLite harness. |
| `test-file-organization` | The touched frontend component test covers roster, timeline, relatedness, and fallback behavior and must remain navigable by scenario. |
| `verification-scope-discipline` | Focused backend/frontend tests are required during development, and the exact handoff Verification Command is required before completion. |

## Task-Specific Proof Obligations

- `C-TC-1`: Backend API tests must prove identity timeline responses include `event_data` with typed payload facts from persisted CAO events and still include the selected participant role from the participant index.
- `C-TC-2`: Backend API tests must prove related-event responses include `event_data` on the canonical event and on causation/correlation related event rows without changing relatedness membership.
- `C-TC-3`: Event persistence tests must prove the event-log read record exposes the persisted typed payload as JSON data without losing exact typed event reconstruction.
- `C-TC-4`: Frontend API tests must prove timeline and related-event API wrappers preserve `event_data` in returned typed objects.
- `C-TC-5`: Frontend component tests must prove an untaught event kind on the main timeline is visible through the fallback with event name, envelope facts, participant role, and safely displayable `event_data` facts.
- `C-TC-6`: Frontend component tests must prove untaught related events render through the same fallback path inside the related-events panel.
- `C-TC-7`: Completion requires the exact handoff Verification Command:

```bash
uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py && cd web && npm test -- --run src/test/api.test.ts src/test/agent-identity-timeline-panel.test.tsx && npm run build
```

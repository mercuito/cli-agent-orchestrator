# Coding Test Contract — t-1

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-TC-1` | Feature-level Test Contract | Backend proof must use the existing in-memory SQLite event-log and API test patterns to demonstrate identity timeline membership, broadcast visibility, causation and correlation relatedness, and exclusion of zero-participant events. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| [test-validity-preserved](../../../../planning/methodology/criteria/coding-test-contract/test-validity-preserved.md) | Universal criterion for every code-touching task. |
| [given-when-then-test-structure](../../../../planning/methodology/criteria/coding-test-contract/given-when-then-test-structure.md) | API and event-log tests prove multi-step setup, route invocation, and response assertions. |
| [public-boundary-proof](../../../../planning/methodology/criteria/coding-test-contract/public-boundary-proof.md) | The task changes dashboard HTTP API routes that downstream UI will call. |
| [real-surface-proof-discipline](../../../../planning/methodology/criteria/coding-test-contract/real-surface-proof-discipline.md) | Confidence depends on FastAPI route handling and the real in-memory SQLite event store. |
| [inspectable-authored-inputs](../../../../planning/methodology/criteria/coding-test-contract/inspectable-authored-inputs.md) | Authored event roles, correlation IDs, and zero-participant workspace event inputs directly affect route assertions. |
| [setup-invariant-ownership](../../../../planning/methodology/criteria/coding-test-contract/setup-invariant-ownership.md) | Event fixtures must create valid CAO events and manager-backed identities before route assertions. |
| [reusable-test-state](../../../../planning/methodology/criteria/coding-test-contract/reusable-test-state.md) | Existing event fixtures and manager-backed identity fixtures should be reused or extended for repeated timeline scenarios. |
| [test-through-owner-surfaces](../../../../planning/methodology/criteria/coding-test-contract/test-through-owner-surfaces.md) | Tests should use public identity manager and event-store surfaces instead of duplicating participant-index internals. |
| [test-artifact-containment](../../../../planning/methodology/criteria/coding-test-contract/test-artifact-containment.md) | Tests create persisted in-memory SQLite event-log state through the scoped database fixture. |
| [test-file-organization](../../../../planning/methodology/criteria/coding-test-contract/test-file-organization.md) | The target API and event persistence test files cover multiple route/event behavior families and must remain navigable. |
| [verification-scope-discipline](../../../../planning/methodology/criteria/coding-test-contract/verification-scope-discipline.md) | Focused red/green proof and the exact handoff Verification Command are both required. |

## Task-Specific Proof Obligations

- `C-TC-1`: API tests must prove the identity timeline route resolves identity status through the manager surface and returns timeline rows with the selected identity's participant role.
- `C-TC-2`: API tests must prove broadcast events appear as one canonical event on each participant identity timeline with the participant role for the requested identity.
- `C-TC-3`: API tests must prove zero-participant workspace events do not appear on an identity timeline while still existing in the event log.
- `C-TC-4`: API tests must prove correlation and causation related-event reads return envelope-based related records for a canonical event.
- `C-TC-5`: API tests must prove invalid boundary cases: unknown identities return `404`, unknown related-event IDs return `404`, and missing relatedness returns empty related collections rather than a fabricated thread.
- `C-TC-6`: Event-store tests must prove the participant-index timeline read exposes the selected participant role without deriving membership or role from typed event body fields.
- `C-TC-7`: The exact Verification Command from the handoff must pass before completion: `uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py`.

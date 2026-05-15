# Coding Completion Report — t-3

## Implementation Summary

Completed the final compatibility sweep without production-code changes. The task added focused API characterization proof that `/openapi.json` keeps the public timeline event envelope compatible: `event_type_key` remains a required string property and `event_data` remains an object payload on the shared timeline event response schema used by timeline and related-event routes, including nested related-event causation rows.

The remaining `event_type_key` matches were classified. Active backend storage and reads remain `kind`-based; `event_type_key` survives only as the public API compatibility projection, generated frontend compatibility constants, proof fixtures, or the `F-CC-6` legacy migration backfill/drop input.

## Plan Divergence

The plan expected no production-code changes unless compatibility proof failed; that held. During the caller sweep, `src/cli_agent_orchestrator/clients/database_migrations.py` legacy-column references required a coding-contract and plan revision because the first classification taxonomy did not explicitly include `F-CC-6` migration-only legacy input. The plan reviewer approved the revised taxonomy.

## Slice-Adequacy Self-Check

The assigned slices still fit the finished implementation:

- `F-CC-4`: preserved through unchanged API response construction and new OpenAPI schema characterization.
- `F-CC-12`: satisfied by the final `rg 'event_type_key' src/ test/ web/src/` sweep and classification.
- `F-TC-8`: satisfied by the exact full backend/frontend preservation command passing.
- `F-TC-10`: satisfied by the added OpenAPI public-boundary characterization test.

No assigned feature clause was wrong, infeasible, or missing after implementation evidence was reviewed.

## Contract Boundary And Escalation Check

The task stayed within the assigned pure-refactor preservation boundary. It did not change behavior, production public response construction, storage schema, generated artifacts, developer commands, or frontend rendering behavior. It added one test assertion surface for the already-existing public OpenAPI schema.

No unsupported compatibility scaffolding, dual-shape storage, compatibility re-export, adapter, facade, or long-lived shim was added. The only remaining backend `event_type_key` migration references are the already-authorized `F-CC-6` legacy backfill/drop path; active writes, reads, and serializer deserialization use `kind`. No upstream escalation was required.

## Verification Result

Exact Verification Command from the handoff passed:

```bash
uv run pytest test/events/test_cao_event_persistence.py test/api/test_agent_identity_routes.py test/runtime/test_agent_runtime.py && cd web && npm test -- agent-identity-timeline-panel.test.tsx agent-panel-deeplink.test.tsx api.test.ts
```

Result: 71 backend tests passed; frontend `pretest` passed `check:event-types` and `tsc --noEmit`; 48 Vitest tests passed.

Focused proof also passed:

```bash
uv run pytest test/api/test_agent_identity_routes.py -q -k openapi_preserves_public_event_envelope
```

## Spec Sync

No upstream feature artifact needed amendment. The task-level Coding Code Contract and Coding Implementation Plan were revised to classify `F-CC-6` migration-only legacy input explicitly, and the plan reviewer approved that revision.

## Files Changed

- `docs/plans/cao-event-schema-codegen/tasks/t-3/coding-code-contract.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-3/coding-test-contract.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-3/coding-implementation-plan.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-3/coding-completion-report.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-3/code-contract-defence.md`
- `docs/plans/cao-event-schema-codegen/tasks/t-3/test-contract-defence.md`
- `test/api/test_agent_identity_routes.py`

## Observations

The active compatibility path is narrow and explicit: store/read by `kind`, compute module-qualified `event_type_key` for public timeline responses, and let frontend components dispatch by that public envelope value while generated types narrow known payloads.

## Hiccups

An initial focused `pytest -k openapi` check found no existing OpenAPI test and exited with no selected tests. A direct OpenAPI probe with a plain `TestClient` hit `TrustedHostMiddleware`; using the existing API test client fixture pattern resolved it. The plan-review revision also caught that migration-only legacy references needed their own classification bucket.

## Optimization Opportunities

None identified for this task without reopening storage or frontend codegen ownership.

## Risks And Known Issues

No known unresolved risks in the assigned `t-3` scope.

## Final Review Outcomes

| Reviewer | Contract reviewed | Approval status | Changes made because of review |
|----------|-------------------|-----------------|--------------------------------|
| `coding-code-contract-reviewer` | Code Contract Defence / Coding Code Contract criteria and assigned `F-CC-4`, `F-CC-12` compliance | Approved | Added explicit classification for the generated built web UI asset `src/cli_agent_orchestrator/web_ui/assets/index-DzMk5E1o.js` to the Code Contract Defence. |
| `coding-test-contract-reviewer` | Test Contract Defence / Coding Test Contract criteria and assigned `F-TC-8`, `F-TC-10` compliance | Approved | Extended the OpenAPI characterization test and defences to cover nested related-event causation envelope fields `direct_cause` and `direct_effects`. |

No behavioral contract review was applicable because `t-3` has no behavioral slice. No committed-decision promotion was warranted.

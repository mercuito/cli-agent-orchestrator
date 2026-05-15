# Coding Implementation Plan — t-3

## Research Findings

- The backend store no longer persists `event_type_key`; `src/cli_agent_orchestrator/clients/cao_event_store.py` persists `kind`, deserializes by `kind`, and computes `CaoEventRecord.event_type_key` from the reconstructed event class for public compatibility.
- `src/cli_agent_orchestrator/services/agent_identity_timeline.py` maps the computed record field into `TimelineEventRead`, and `src/cli_agent_orchestrator/api/main.py` maps that read into `AgentIdentityTimelineEventResponse`.
- `web/src/api.ts` still models `event_type_key: string` and `event_data: Record<string, unknown>`. `AgentIdentityTimelinePanel.tsx` dispatches main and related rows through `eventTimelineViewRegistry.viewFor(event.event_type_key)`.
- `web/src/generated/caoEventPayloadTypes.ts` now owns known public event constants and generated payload mappings. Unknown event-key literals in frontend tests remain fallback fixtures.
- Existing API route tests assert response bodies preserve `event_type_key` and `event_data`, but research found no focused proof that `/openapi.json` preserves those fields in the route response schema, which `F-CC-4` explicitly protects.
- Risk is low because the production code already appears compatible; the main risk is incomplete final classification/proof rather than a needed storage or codegen implementation change.

## High-Level Architecture

**Surface shape.** Keep production response construction unchanged unless focused proof or the final verification command exposes a violation. Add a narrow API characterization test under `test/api/test_agent_identity_routes.py` if the OpenAPI schema compatibility proof is absent.

**Data flow.** Storage reads reconstruct typed events from `kind`, compute the public module-qualified `event_type_key`, pass it through the timeline service read DTO, and expose it through API response models. Frontend consumers continue to treat `event_type_key` as an API envelope field while generated payload types narrow known event data internally.

**Reuse points.** Use the existing FastAPI test client for OpenAPI proof, existing backend route tests for response-body proof, existing frontend Vitest suites for registry/API proof, generated `caoEventPayloadTypes.ts` for known constants, and the handoff's exact verification command for final baseline proof.

## Sub-Task List

1. Complete the final caller classification sweep.
   - Clauses satisfied: `F-CC-12`, `C-CC-2`, `C-CC-3`, `C-CC-4`, `C-CC-5`.
   - Done condition: `rg 'event_type_key' src/ test/ web/src/` output is classified with no unremoved contract violations; any backend migration reference is limited to the `F-CC-6` legacy backfill/drop path and is not an active read/write discriminator path.
   - Dependency order: First.

2. Add focused public OpenAPI compatibility characterization if still uncovered.
   - Clauses satisfied: `F-CC-4`, `F-TC-10`, `C-CC-1`, `C-TC-2`, `public-boundary-proof`, `real-surface-proof-discipline`, `test-through-owner-surfaces`.
   - Done condition: A focused API test proves timeline and related-event route schemas expose `event_type_key` and object-shaped `event_data`.
   - Dependency order: After classification confirms this is public-boundary proof, not storage/codegen work.

3. Run focused and full verification.
   - Clauses satisfied: `F-TC-8`, `C-TC-1`, `C-TC-3`, `C-TC-4`, `full-verification-required`, `test-validity-preserved`, `verification-scope-discipline`.
   - Done condition: The focused API proof passes, then the exact handoff Verification Command passes.
   - Dependency order: Last.

## Revision Log

- Revised `C-CC-2`, `C-CC-4`, and the classification sub-task done condition after the final `rg 'event_type_key' src/ test/ web/src/` sweep surfaced `src/cli_agent_orchestrator/clients/database_migrations.py` legacy-column references. Those references are the `F-CC-6` backfill/drop path from `t-1`, not active storage/read-path compatibility, so the coding contract now distinguishes allowed migration-only legacy input from prohibited active discriminator usage.

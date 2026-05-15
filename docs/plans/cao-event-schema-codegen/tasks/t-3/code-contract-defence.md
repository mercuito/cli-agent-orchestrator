# Code Contract Defence — t-3

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Always; every claim below cites concrete code, test, command, or discovery evidence. |

## Feature-Level Code Contract

### Clause: F-CC-4

**Claim:** The public timeline API response envelope remains compatible.

**Evidence:** `AgentIdentityTimelineEventResponse` in `src/cli_agent_orchestrator/api/main.py` still exposes `event_type_key: str` and `event_data: Dict[str, Any]`, and `from_read()` passes `read.event_type_key` and `read.event_data` through unchanged. `test_agent_identity_timeline_openapi_preserves_public_event_envelope` proves `/openapi.json` exposes `event_type_key` as a required string and `event_data` as an object on the shared timeline event response schema used by timeline and related-event route models. Existing API route tests still assert response bodies include module-qualified `event_type_key` values and unchanged `event_data` payload fields. The exact Verification Command passed.

### Clause: F-CC-12

**Claim:** Every remaining `event_type_key` match was classified and no active storage/read-path violation remains.

**Evidence:** Discovery command `rg 'event_type_key' src/ test/ web/src/` produced matches classified as follows:

| Match set | Classification / outcome |
|-----------|--------------------------|
| `src/cli_agent_orchestrator/clients/cao_event_store.py` dataclass field, `_record_from_model()` assignment, `_public_event_type_key()` | Public API compatibility projection computed from reconstructed event class per `CID-1`; not persisted or used for deserialization. |
| `src/cli_agent_orchestrator/services/agent_identity_timeline.py` `TimelineEventRead.event_type_key` and `record.event_type_key` mapping | Public timeline service envelope compatibility. |
| `src/cli_agent_orchestrator/api/main.py` response field and `from_read()` mapping | Public API response envelope compatibility. |
| `src/cli_agent_orchestrator/clients/database_migrations.py` legacy column/index strings | `F-CC-6` migration-only legacy backfill/drop input; not an active storage/read/write discriminator after migration. |
| `web/src/api.ts` `AgentIdentityTimelineEvent.event_type_key` | Public frontend API envelope type. |
| `web/src/components/AgentIdentityTimelinePanel.tsx` registry dispatch reads | Public envelope compatibility caller; view dispatch remains keyed by API `event_type_key`. |
| `web/src/components/timelineEventViews.tsx` known-event type narrowing | Public envelope field narrowed against generated compatibility constants and generated payload types. |
| `web/src/test/*` generated constants and unknown literals | Proof fixtures for known generated compatibility constants and unknown-event fallback/public compatibility behavior. |
| `src/cli_agent_orchestrator/web_ui/assets/index-DzMk5E1o.js` built bundle match | Generated built dashboard asset containing bundled frontend public-envelope reads. It is not an authoritative source, storage/read path, serializer path, or generated typing source; source ownership is classified in `web/src/api.ts`, `AgentIdentityTimelinePanel.tsx`, and `timelineEventViews.tsx`. |
| `test/events/test_cao_event_persistence.py` assertions and legacy DDL | Preservation proof for kind-only table shape, legacy migration backfill, and computed timeline compatibility projection. |
| `test/api/test_agent_identity_routes.py` OpenAPI/body assertions | Public API compatibility characterization and route proof. |

## Coding Code Contract Criteria

### Criterion: full-verification-required

**Claim:** The exact Verification Command succeeded.

**Evidence:** The handoff command passed: 71 backend tests, frontend `check:event-types`, `tsc --noEmit`, and 48 Vitest tests.

### Criterion: semantic-continuity

**Claim:** Existing public timeline semantics continue unchanged.

**Evidence:** No production code changed. Existing backend route tests, frontend API tests, timeline panel tests, deeplink tests, and the new OpenAPI characterization all passed.

### Criterion: respect-ownership-boundaries

**Claim:** Storage, migration, service, API, generated type, and frontend presentation ownership remain coherent.

**Evidence:** The task added only API proof and planning artifacts. It did not move logic between `cao_event_store.py`, `database_migrations.py`, `agent_identity_timeline.py`, `api/main.py`, generated frontend types, or presentation components.

### Criterion: respect-standing-decisions

**Claim:** `CID-1` and `CID-2` remain respected.

**Evidence:** `CID-1`: active storage remains `kind`-only, while `CaoEventRecord.event_type_key` is a computed public projection. `CID-2`: frontend known constants and payload typing still come from `web/src/generated/caoEventPayloadTypes.ts`; no retired generator/module was restored.

### Criterion: readable-and-explicit

**Claim:** Compatibility classification is explicit.

**Evidence:** `coding-code-contract.md` and `coding-implementation-plan.md` now distinguish public API compatibility, generated compatibility constants, proof fixtures, and `F-CC-6` migration-only legacy input from prohibited active discriminator usage.

### Criterion: migration-discipline

**Claim:** Retired surfaces were not reintroduced as bridges.

**Evidence:** The task did not add production compatibility branches. Discovery found no active storage/read query using `event_type_key`; migration references are limited to the legacy backfill/drop path already authorized by `F-CC-6`.

### Criterion: no-assumed-backwards-compatibility

**Claim:** Only explicitly contracted compatibility remains.

**Evidence:** The public `event_type_key` response envelope remains under `F-CC-4`; generated constants remain under `CID-2`; legacy migration input remains under `F-CC-6`. No new alias, shim, dual-write, or frontend codegen compatibility module was added.

## Coding Code Contract Obligations

### Clause: C-CC-1

**Claim:** Timeline and related route schemas expose the public event envelope.

**Evidence:** `test_agent_identity_timeline_openapi_preserves_public_event_envelope` checks the shared `AgentIdentityTimelineEventResponse` schema, the `AgentIdentityTimelineResponse` / `AgentIdentityRelatedEventsResponse` references to it, and the nested `AgentIdentityCausationRelatedEventsResponse` direct-cause/direct-effects references used by related-event responses.

### Clause: C-CC-2

**Claim:** Active backend storage/read paths do not use `event_type_key` as a discriminator.

**Evidence:** `cao_event_store.py` persists `kind`, deserializes by `kind`, and computes `event_type_key` from `type(event)`. `database_migrations.py` references `event_type_key` only as legacy migration input for backfill/drop. The exact backend preservation tests passed.

### Clause: C-CC-3

**Claim:** Frontend production consumers use `event_type_key` only as the public envelope field while generated typing remains authoritative for known payloads.

**Evidence:** `web/src/api.ts` types the envelope as `event_type_key: string`. `AgentIdentityTimelinePanel.tsx` dispatches by `event.event_type_key`. `timelineEventViews.tsx` and `knownCaoEventViews.tsx` use `CaoEventPayloadForTypeKey` and constants from `web/src/generated/caoEventPayloadTypes.ts`.

### Clause: C-CC-4

**Claim:** The final caller sweep was run and every match was classified.

**Evidence:** The `F-CC-12` classification table above records every match category from `rg 'event_type_key' src/ test/ web/src/`, including the generated built web UI asset match when not ignored by local `rg` settings, and identifies no unremoved violation.

### Clause: C-CC-5

**Claim:** Backend storage and frontend codegen implementation were not reopened.

**Evidence:** Production backend/frontend codegen files were not edited by this task. The only non-planning edit is the OpenAPI characterization test in `test/api/test_agent_identity_routes.py`.

## Committed Implementation Decisions

### Decision: CID-1

**Claim:** The task remains compatible with kind-only backend storage.

**Evidence:** Classification confirms `event_type_key` is not an active storage discriminator; it is computed for public response compatibility, while migration-only references serve the legacy backfill/drop path.

### Decision: CID-2

**Claim:** The task remains compatible with generated frontend payload typing and compatibility constants.

**Evidence:** Frontend tests and production views still import known constants and payload mappings from `web/src/generated/caoEventPayloadTypes.ts`; `npm run check:event-types` passed during the exact Verification Command.

## Committed-Decision Promotion Draft

No promotion warranted: this task classified and defended compatibility boundaries but did not settle a new durable implementation decision beyond `CID-1` and `CID-2`.

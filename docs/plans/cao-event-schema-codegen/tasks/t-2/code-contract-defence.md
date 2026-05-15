# Code Contract Defence — t-2

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Always; every claim below cites concrete code, generated artifacts, commands, or discovery output. |
| `promotion-draft-durability` | The task settles the durable frontend generated payload artifact and command/check boundary for later tasks. |

## Feature-Level Code Contract

### Clause: F-CC-5

**Claim:** Frontend event payload types are schema-generated from backend CAO event declarations and consumed by the event-view registry/views.

**Evidence:** `scripts/generate_cao_event_payload_types.py` imports `LINEAR_CAO_EVENTS` and `RUNTIME_CAO_EVENTS`, builds a Pydantic discriminated union schema, validates the `CaoEventPayload` discriminator mapping, and runs `openapi-typescript`. The generated output is `web/src/generated/caoEventPayloadTypes.ts`, which exports `CaoEventPayload`, `CaoEventPayloadByTypeKey`, and `CaoEventPayloadForTypeKey`. `web/src/components/timelineEventViews.tsx` imports those generated types and defines typed known-event view props; `web/src/components/timelineEventViews/knownCaoEventViews.tsx` registers known views through that typed surface.

### Clause: F-CC-10

**Claim:** Retired frontend codegen surfaces are removed with their replacement.

**Evidence:** `scripts/generate_cao_event_type_keys.py` and `web/src/generated/caoEventTypeKeys.ts` are deleted. `web/package.json` points `generate:event-types` to `scripts/generate_cao_event_payload_types.py`; no alias or wrapper for the retired generator/module remains.

### Clause: F-CC-11

**Claim:** Assigned frontend callers and codegen wiring were discovered and migrated or classified.

**Evidence:** Discovery command `rg 'caoEventTypeKeys|event_type_key|cli_agent_orchestrator\.' web/src/` found no `caoEventTypeKeys` imports after migration. Every remaining match is classified below:

| Match | Classification / outcome |
|-------|--------------------------|
| `web/src/api.ts`: `event_type_key: string` | Public timeline API compatibility envelope preserved; not a generated-constant caller. |
| `web/src/components/AgentIdentityTimelinePanel.tsx`: two `event.event_type_key` registry dispatch reads | Public timeline API compatibility caller preserved; registry still dispatches by the public envelope value. |
| `web/src/components/timelineEventViews.tsx`: `event_type_key` omitted/reintroduced in `KnownTimelineEvent<T>` | Migrated to generated payload typing; narrows known event views by `CaoEventTypeKey` while preserving the public envelope field. |
| `web/src/test/agent-panel-deeplink.test.tsx`: legacy literal `LinearAgentMentionedEvent` | Existing baseline fixture for fallback/public compatibility behavior; not a generated constant caller. |
| `web/src/test/agent-panel-deeplink.test.tsx`: `AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT` | Migrated to `web/src/generated/caoEventPayloadTypes.ts`. |
| `web/src/test/api.test.ts`: `LinearAgentMentionedEvent` and `cao.experimental.AuditEvent` literals | Public API compatibility/fallback fixtures; no generated constant import required. |
| `web/src/test/agent-identity-timeline-panel.test.tsx`: helper `event_type_key: event_name` | Existing fixture helper for public envelope baseline; not a generated constant caller. |
| `web/src/test/agent-identity-timeline-panel.test.tsx`: `cao.experimental.AuditEvent` and `cao.experimental.RelatedAuditEvent` literals | Existing unknown-event fallback fixtures; intentionally remain hand-authored unknown public keys. |
| `web/src/test/agent-identity-timeline-panel.test.tsx`: generated constants for Linear mention/runtime events | Migrated to `web/src/generated/caoEventPayloadTypes.ts`. |
| `web/src/generated/caoEventPayloadTypes.ts`: public module-qualified constant values | New generated compatibility constants produced by the schema-driven generator. |
| `web/src/generated/caoEventPayloadTypes.ts`: `CaoEventPayloadByTypeKey` module-qualified keys | New generated event-key-to-payload type map. |

Discovery command `rg 'generate_cao_event_type_keys|generate:event-types|openapi-typescript' web/package.json web/package-lock.json` matches were classified as:

| Match | Classification / outcome |
|-------|--------------------------|
| `web/package.json`: `generate:event-types` | Migrated command name now runs `scripts/generate_cao_event_payload_types.py`; retained command name is workflow continuity, not retired generator compatibility. |
| `web/package.json`: `openapi-typescript` | New schema-codegen dependency. |
| `web/package-lock.json`: root `openapi-typescript` dependency | New dependency lock entry. |
| `web/package-lock.json`: `node_modules/openapi-typescript` package and bin entries | New dependency lock entries. |

The command found no `generate_cao_event_type_keys` match in `web/package.json` or `web/package-lock.json`.

## Coding Code Contract Criteria

### Criterion: full-verification-required

**Claim:** The exact Verification Command succeeded.

**Evidence:** `cd web && npm test -- agent-identity-timeline-panel.test.tsx agent-panel-deeplink.test.tsx api.test.ts` passed, including `pretest`.

### Criterion: red-green-refactor

**Claim:** Focused proof failed before the generated artifact existed, then passed after implementation.

**Evidence:** `npm run check:event-types` first failed with “Generated CAO event payload types are missing.” After implementation, `npm run check:event-types` passed.

### Criterion: semantic-continuity

**Claim:** Existing timeline event dispatch, fallback rendering, known views, and API envelope semantics are preserved.

**Evidence:** `web/src/api.ts` still exposes `event_type_key: string` and `event_data: Record<string, unknown>`. `AgentIdentityTimelinePanel` still dispatches with `event.event_type_key`. The exact Verification Command passed existing known-view, fallback, deep-link, and API tests.

### Criterion: no-unnecessary-duplication

**Claim:** Event schema, kind, and public compatibility vocabulary are generated from backend event declarations.

**Evidence:** The generator uses the exported backend event tuples and `cao_event_kind`; the known views no longer define local payload key dictionaries.

### Criterion: respect-ownership-boundaries

**Claim:** Schema/source ownership, codegen ownership, and frontend presentation ownership remain separated.

**Evidence:** Backend declarations remain read-only inputs; the generator lives under `scripts/`; generated TS lives under `web/src/generated/`; presentation code remains under `web/src/components/timelineEventViews/`.

### Criterion: centralized-vocabulary

**Claim:** Event constants and payload type mapping have one generated frontend source.

**Evidence:** `web/src/generated/caoEventPayloadTypes.ts` exports all public event constants, `CAO_EVENT_TYPE_KEYS`, `CaoEventTypeKey`, and `CaoEventPayloadByTypeKey`.

### Criterion: path-utils-required

**Claim:** Generator path operations use path utilities.

**Evidence:** `scripts/generate_cao_event_payload_types.py` constructs repo, web, output, temp schema, and candidate paths with `pathlib.Path`.

### Criterion: filesystem-boundary-required

**Claim:** Filesystem I/O stays in the generator boundary.

**Evidence:** Only `scripts/generate_cao_event_payload_types.py` writes the generated file and transient schema/candidate files. Frontend consumers import generated output only.

### Criterion: prefer-public-surfaces

**Claim:** Cross-boundary backend consumption goes through exported event tuples and public serializer vocabulary.

**Evidence:** The generator imports `LINEAR_CAO_EVENTS`, `RUNTIME_CAO_EVENTS`, and `cao_event_kind`; it does not import private backend helpers.

### Criterion: respect-standing-decisions

**Claim:** CID-1 remains respected.

**Evidence:** The task does not write or read backend storage discriminators. Generated public constants are derived from class module/name values solely for the preserved timeline API `event_type_key` envelope.

### Criterion: readable-and-explicit

**Claim:** Codegen mode, schema validation, output comparison, and typed payload view dispatch are explicit.

**Evidence:** Generator functions are named for schema emission, branch validation, rendering, and check output. `timelineEventViewRegistration` exposes the typed view registration boundary.

### Criterion: service-export-discipline

**Claim:** Generated module exports are required by current callers or assigned contract.

**Evidence:** Current callers import event constants and payload-map types from `caoEventPayloadTypes.ts`; exported payload declarations and compatibility constants are required by F-CC-5/F-CC-10.

### Criterion: migration-discipline

**Claim:** Existing frontend callers moved to the new shape without keeping the old module.

**Evidence:** Test and component imports now use `caoEventPayloadTypes.ts`; the old generated module is deleted.

### Criterion: no-assumed-backwards-compatibility

**Claim:** No compatibility alias, wrapper, or bridge remains for retired frontend codegen surfaces.

**Evidence:** The retired Python script and generated TS module are deleted; discovery found no `caoEventTypeKeys` imports in `web/src`.

## Coding Code Contract Obligations

### Clause: C-CC-1

**Claim:** The replacement generator emits one schema-generated TypeScript output from backend event declarations.

**Evidence:** `scripts/generate_cao_event_payload_types.py` builds `CaoEventPayload` from `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`, validates branch coverage, runs `openapi-typescript`, and writes `web/src/generated/caoEventPayloadTypes.ts`.

### Clause: C-CC-2

**Claim:** Generated output exports payload declarations, compatibility constants, key union, and event-key-to-payload mapping.

**Evidence:** `caoEventPayloadTypes.ts` exports `components`, `CaoEventPayload`, all public event constants, `CAO_EVENT_TYPE_KEYS`, `CaoEventTypeKey`, `CaoEventPayloadByTypeKey`, and `CaoEventPayloadForTypeKey`.

### Clause: C-CC-3

**Claim:** Known event views consume generated payload typing.

**Evidence:** `timelineEventViews.tsx` defines `KnownTimelineEvent<T>` with `CaoEventPayloadForTypeKey<T>`. `knownCaoEventViews.tsx` declares each known view as `KnownTimelineEventView<typeof ...>` and reads payload fields through `event.event_data`.

### Clause: C-CC-4

**Claim:** Frontend package wiring uses `openapi-typescript` and deterministic generate/check commands.

**Evidence:** `web/package.json` defines `generate:event-types`, `check:event-types`, and `pretest`; `web/package-lock.json` locks `openapi-typescript` 7.13.0.

### Clause: C-CC-5

**Claim:** Retired surfaces are removed and discovered callers are migrated or classified.

**Evidence:** Deleted old script/module. The F-CC-11 evidence table records every matched caller/wiring item from the contracted discovery commands and classifies it as migrated generated artifact use, new command/dependency wiring, generated compatibility output, public timeline API compatibility, or intentional unknown-event fallback fixture. No `caoEventTypeKeys` imports and no `generate_cao_event_type_keys` package-script/lockfile references remain.

### Clause: C-CC-6

**Claim:** Public timeline API envelope is preserved.

**Evidence:** `web/src/api.ts` remains `event_type_key: string` and `event_data: Record<string, unknown>`; no backend API response model or route file was changed by this task.

## Committed Implementation Decisions

### Decision: CID-1

**Claim:** The task remains compatible with kind-only backend storage.

**Evidence:** The generator uses `cao_event_kind` only for schema branch mapping. Public `event_type_key` constants are generated as API compatibility values and are not fed into storage, serializer, or backend read paths.

## Committed-Decision Promotion Draft

### Proposed CID-2 — Frontend Event Payload Codegen Uses Generated Schema Types

Promote after review approval.

Frontend CAO event payload typing is generated by
`scripts/generate_cao_event_payload_types.py` into
`web/src/generated/caoEventPayloadTypes.ts`. The generator derives
`CaoEventPayload` from `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`, validates one
discriminator branch per registered `kind`, runs `openapi-typescript`, and
also emits public timeline `event_type_key` compatibility constants in the same
generated module.

`web/package.json` keeps `generate:event-types` as the regeneration command,
adds `check:event-types` as the freshness check, and runs the freshness check
plus `tsc --noEmit` before frontend tests. The retired
`scripts/generate_cao_event_type_keys.py` and
`web/src/generated/caoEventTypeKeys.ts` surfaces are removed.

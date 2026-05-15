# Coding Code Contract — t-2

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| F-CC-5 | feature-level Code Contract | The task owns replacing the frontend hand-rolled event key artifact with schema-generated CAO event payload declarations consumed by timeline event views. |
| F-CC-10 | feature-level Code Contract | The task owns retiring `scripts/generate_cao_event_type_keys.py`, replacing `web/src/generated/caoEventTypeKeys.ts`, and removing frontend hand-typed Python-style event key strings from the assigned frontend surfaces. |
| F-CC-11 | feature-level Code Contract | The task owns exhaustive frontend caller discovery and migration for retired generated constants, event key strings, and codegen command wiring. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `full-verification-required` | The task produces code changes and must run the exact Verification Command from the handoff before completion. |
| `red-green-refactor` | The codegen freshness seam, generated public constants, and known-view payload typing are testable through a failing codegen/check cycle before replacement. |
| `semantic-continuity` | Existing timeline API envelopes, fallback rendering, known event view registration, and frontend test fixtures must keep their preserved behavior while event payload typing changes. |
| `no-unnecessary-duplication` | Event kinds, public compatibility event keys, and payload schemas must come from the registered backend event declarations instead of duplicated frontend mappings. |
| `respect-ownership-boundaries` | Backend event declarations own schema source data; codegen tooling owns generated artifacts; frontend views own presentation and consume generated types without moving API compatibility into backend schema changes. |
| `centralized-vocabulary` | Event kind strings, public `event_type_key` constants, and payload schema names are named syntax consumed by frontend callers and must have one generated source. |
| `path-utils-required` | The generator constructs repo, schema, temporary, and generated-output paths. |
| `filesystem-boundary-required` | The generator performs filesystem I/O to create transient schema input and write or compare generated TypeScript output. |
| `prefer-public-surfaces` | The generator must consume exported `LINEAR_CAO_EVENTS`, `RUNTIME_CAO_EVENTS`, and public serializer vocabulary rather than private backend helpers. |
| `respect-standing-decisions` | CID-1 makes `kind` the only backend storage discriminator; this task may generate public compatibility constants but must not reintroduce storage/serializer `event_type_key` dependence. |
| `readable-and-explicit` | The codegen boundary, check mode, generated constants, and typed payload narrowing must be understandable from names and control flow. |
| `service-export-discipline` | The generated TypeScript module export surface changes and every exported constant/type must be required by current frontend callers or the assigned feature contract. |
| `migration-discipline` | Existing frontend imports and package scripts move to the new generated artifact and codegen command without compatibility wrappers for retired file names. |
| `no-assumed-backwards-compatibility` | The retired Python generator and `caoEventTypeKeys.ts` module must not remain as aliases or bridge exports unless an in-force contract requires them. |

## Task-Specific Code Obligations

- `C-CC-1`: Replace the retired frontend generator with a schema-driven generator that imports `LINEAR_CAO_EVENTS` and `RUNTIME_CAO_EVENTS`, builds an OpenAPI-compatible schema document with exactly one `CaoEventPayload` branch per registered event `kind`, runs `openapi-typescript` against that repo-local schema document, and writes a single version-controlled TypeScript output under `web/src/generated/`.
- `C-CC-2`: The generated TypeScript output must export CAO event payload declarations, the still-needed public `event_type_key` compatibility constants, a generated event-type-key union, and a generated mapping from public `event_type_key` constants to the corresponding payload type/schema branch.
- `C-CC-3`: Frontend timeline event view typing in `web/src/components/timelineEventViews.tsx` and known event view modules must consume the new generated payload mapping; known view implementations may keep runtime fallback checks for nullable or unknown API payload values, but their handled event payload field names must be typed through generated payload declarations rather than local key dictionaries.
- `C-CC-4`: `web/package.json` and `web/package-lock.json` must wire `openapi-typescript` as the frontend codegen dependency and expose deterministic generate/check command behavior; `pretest` must prove codegen freshness before the assigned frontend tests run.
- `C-CC-5`: Remove `scripts/generate_cao_event_type_keys.py` and `web/src/generated/caoEventTypeKeys.ts`; migrate every assigned caller discovered by `rg 'caoEventTypeKeys|event_type_key|cli_agent_orchestrator\.' web/src/` and `rg 'generate_cao_event_type_keys|generate:event-types|openapi-typescript' web/package.json web/package-lock.json` to the new generated artifact or classify it as public timeline API compatibility.
- `C-CC-6`: The codegen path must preserve the public timeline API envelope: frontend API models continue to expose `event_type_key` and object-shaped `event_data`, and this task must not change backend API response models or route outputs beyond reading backend event declarations for schema generation.

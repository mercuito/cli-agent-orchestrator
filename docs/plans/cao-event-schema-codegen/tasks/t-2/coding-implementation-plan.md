# Coding Implementation Plan — t-2

## Research Findings

Investigated the assigned frontend codegen and event view surfaces:

- `scripts/generate_cao_event_type_keys.py` is the current generator. It imports the legacy `event_type_key` helper, discovers `*_CAO_EVENTS` tuple exports, and writes only `web/src/generated/caoEventTypeKeys.ts`.
- `web/package.json` wires `generate:event-types` into `pretest` and `prebuild`; the current command runs the retired Python generator. `web/package-lock.json` currently has no `openapi-typescript` dependency.
- `web/src/components/timelineEventViews.tsx` owns event view registration and fallback rendering. `knownCaoEventViews.tsx` imports generated constants but currently reads event payload fields through local string-key dictionaries and `Record<string, unknown>`.
- The F-TC-7 baseline tests already cover known Linear/runtime view dispatch, unknown fallback events, terminal focus, deep-link behavior, and frontend API preservation of object-shaped `event_data`.
- Backend t-1 changes expose `LINEAR_CAO_EVENTS` and `RUNTIME_CAO_EVENTS` as Pydantic dataclasses with `kind` literal fields. `pydantic.TypeAdapter` can emit a discriminator mapping for a union of those event classes.
- CID-1 confirms `event_type_key` is no longer a backend storage discriminator. Public frontend constants may still represent module-qualified class-name values because they match the preserved public timeline envelope, not storage.

Risks and unknowns:

- The generated OpenAPI document needs light normalization so Pydantic `$defs` references resolve under OpenAPI `components.schemas` for `openapi-typescript`.
- Vitest alone does not typecheck payload narrowing, so the frontend verification boundary needs an explicit typecheck step if generated payload declarations are to be proven.
- The new check command must compare without rewriting committed files; otherwise `pretest` could mask stale generated output.

## High-Level Architecture

**Surface shape.** Replace the old event-key generator with `scripts/generate_cao_event_payload_types.py`. The script will build a backend-derived OpenAPI document from `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`, run `web/node_modules/.bin/openapi-typescript`, and generate `web/src/generated/caoEventPayloadTypes.ts`. The generated module will contain openapi-typescript declarations plus generated public compatibility constants and type maps. The retired `web/src/generated/caoEventTypeKeys.ts` file is removed.

**Command shape.** `web/package.json` will keep the existing `generate:event-types` command name for developer workflow continuity but point it at the new schema-driven generator. A separate freshness command will run the generator in check mode, validate the schema branch set, create transient schema and candidate TypeScript files under an isolated temporary directory, compare candidate output against the committed file, and clean up the temporary directory before exit. `openapi-typescript` is added as a dev dependency and locked in `web/package-lock.json`.

**Frontend type flow.** `AgentIdentityTimelineEvent` continues to model the public API envelope with `event_type_key: string` and object-shaped `event_data`. `timelineEventViews.tsx` will add typed event-view registration helpers parameterized by generated public event key constants. Known event views will import payload types/constants from `caoEventPayloadTypes.ts`, register the same public event key values as before, and read payload fields through generated payload types while keeping runtime fallbacks for null, missing, or unknown values.

**Reuse points.** The implementation will reuse exported backend event tuples, Pydantic schema emission, the existing timeline event registry, existing known view components, existing frontend test fixtures, and the established `generate:event-types` script entry name.

## Sub-Task List

1. Add failing codegen/check proof for schema emission and generated freshness.
   - Clauses satisfied: F-TC-3, F-TC-4, C-TC-1, C-TC-5, selected real-surface and artifact-containment criteria.
   - Done condition: The new check command initially fails because the repository still lacks the schema-driven generator/output and `openapi-typescript` wiring; the planned check path writes schema and candidate artifacts only under an isolated temporary directory and cleans it up before exit.
   - Dependency order: First.

2. Replace generator and generated artifact.
   - Clauses satisfied: F-CC-5, F-CC-10, C-CC-1, C-CC-2, C-CC-4, C-CC-5.
   - Done condition: `scripts/generate_cao_event_type_keys.py` and `web/src/generated/caoEventTypeKeys.ts` are gone, `caoEventPayloadTypes.ts` is generated from the backend schema through `openapi-typescript`, and the check command compares cleanly.
   - Dependency order: After sub-task 1.

3. Migrate frontend callers and known event views to generated payload typing.
   - Clauses satisfied: F-CC-5, F-CC-11, C-CC-2, C-CC-3, C-CC-5, C-CC-6, C-TC-2, C-TC-3, C-TC-4.
   - Done condition: All assigned imports use `caoEventPayloadTypes.ts`; known views are typed by generated payload mappings; public envelope types remain unchanged; unknown fallback and existing known-view rendering assertions still pass.
   - Dependency order: After sub-task 2.

4. Wire package scripts, dependency lockfile, and typecheck proof.
   - Clauses satisfied: F-CC-10, F-CC-11, F-TC-4, F-TC-7, C-CC-4, C-TC-1, C-TC-4.
   - Done condition: `pretest` runs codegen freshness and TypeScript typecheck before Vitest; `prebuild` regenerates the committed artifact; lockfile includes `openapi-typescript`.
   - Dependency order: After sub-task 2; can be refined alongside sub-task 3.

5. Run caller discovery, focused proof, and the exact Verification Command.
   - Clauses satisfied: F-CC-11, F-TC-7, F-TC-9, C-CC-5, C-TC-2, all selected verification criteria.
   - Done condition: `rg 'caoEventTypeKeys|event_type_key|cli_agent_orchestrator\.' web/src/` and `rg 'generate_cao_event_type_keys|generate:event-types|openapi-typescript' web/package.json web/package-lock.json` have been run; every match is migrated to the new generated artifact/new command or classified as public timeline API compatibility; focused codegen/type proof passes; and `cd web && npm test -- agent-identity-timeline-panel.test.tsx agent-panel-deeplink.test.tsx api.test.ts` succeeds.
   - Dependency order: Last.

## Revision Log

- 2026-05-14: Clarified that check mode uses isolated temporary schema/candidate artifacts and cleans them up before exit, and that final caller discovery must run the exact contracted `rg` commands with every match migrated or classified. Triggered by implementation-plan review findings before implementation began.
- 2026-05-14: During the post-implementation criteria revisit, added `service-export-discipline` to the Coding Code Contract and `public-boundary-proof` to the Coding Test Contract because the finished task changes the generated TypeScript module export surface and the frontend codegen command boundary. The existing implementation plan already covers those obligations through generated exports required by callers, `npm run check:event-types`, `tsc --noEmit`, and the exact Verification Command.

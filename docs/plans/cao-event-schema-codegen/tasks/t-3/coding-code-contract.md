# Coding Code Contract — t-3

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-CC-4` | Feature Code Contract | This task owns final public timeline API response compatibility after backend `kind` storage and frontend generated payload typing have landed. |
| `F-CC-12` | Feature Code Contract | This task owns classification and defence of every remaining `event_type_key` match across backend, tests, and frontend code. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `full-verification-required` | The handoff names an exact backend/frontend preservation command that must pass before completion. |
| `semantic-continuity` | The task preserves an existing public timeline envelope while confirming migrated backend/frontend internals still flow through it. |
| `respect-ownership-boundaries` | Classification spans storage, service, API, frontend API, generated types, and presentation owners without moving ownership between them. |
| `respect-standing-decisions` | `CID-1` and `CID-2` are in force and define the allowed interpretation of remaining public compatibility keys. |
| `readable-and-explicit` | Remaining compatibility reads must be explicit enough to distinguish public envelope compatibility from retired storage/read-path dependence. |
| `migration-discipline` | This final sweep must not keep retired backend storage or frontend generated-code surfaces alive as hidden bridges. |
| `no-assumed-backwards-compatibility` | Only the public timeline API compatibility envelope may retain `event_type_key`; obsolete internal compatibility paths must be removed if found. |

## Task-Specific Code Obligations

- `C-CC-1`: `AgentIdentityTimelineEventResponse` and every timeline/related route response in `src/cli_agent_orchestrator/api/main.py` must continue to expose `event_type_key` and object-shaped `event_data` as public response fields.
- `C-CC-2`: Timeline response construction may read `CaoEventRecord.event_type_key` only as the computed public compatibility projection established by `CID-1`; active backend storage, serializer, and read-query paths must not use `event_type_key` as a discriminator. Legacy migration references are allowed only for the `F-CC-6` backfill/drop path and must not remain in active reads or writes.
- `C-CC-3`: Frontend production consumers may read `event.event_type_key` only from the public API envelope for API typing or registry dispatch; known event payload narrowing and constants must continue to come from `web/src/generated/caoEventPayloadTypes.ts` per `CID-2`.
- `C-CC-4`: The final caller sweep must run `rg 'event_type_key' src/ test/ web/src/` and classify every production, test, generated, and fixture match as public API compatibility, generated compatibility constant usage, `F-CC-6` migration-only legacy backfill/drop input, characterization/proof fixture, or a violation removed before completion.
- `C-CC-5`: This task must not reopen backend storage or frontend codegen implementation unless classification or verification finds a violation of `F-CC-4`, `F-CC-12`, `F-TC-8`, or `F-TC-10`.

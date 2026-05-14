# Coding Code Contract — t-2

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-CC-3` | Feature Code Contract | This task owns the taught frontend views for Linear mention, runtime delivery, workspace context switch, and runtime lifecycle rows. |
| `F-CC-6` | Feature Code Contract | This task must wire taught views through generated TypeScript event type constants and module self-registration. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `full-verification-required` | The handoff names an exact backend/frontend verification command for this code-changing task. |
| `red-green-refactor` | The task adds observable frontend row behavior and generated-key wiring that can be proven before implementation. |
| `boundary-and-failure-testing` | Frontend views consume runtime JSON payloads, and the registry/generator boundary must handle unregistered or incomplete data predictably. |
| `semantic-continuity` | Existing main and related timeline rendering must keep using the `t-1` registry and fallback semantics while adding taught views. |
| `minimal-cohesive-changes` | The task must stop at known event presentations and generated registration, without implementing `t-3` navigation/focus behavior. |
| `no-unnecessary-duplication` | The four taught views need shared payload narrowing and row-detail primitives without copied ad hoc checks. |
| `no-test-only-production-seams` | Generator, registry discovery, and view exports must serve production rendering and build/test freshness, not only tests. |
| `respect-ownership-boundaries` | Backend event classes own event type identity; frontend view modules own presentation; backend timeline reads remain data-only. |
| `centralized-vocabulary` | Event type key strings and taught event constants must have one generated source derived from backend event classes. |
| `path-utils-required` | The generator constructs repository-relative input/output paths and must use path utilities at that host boundary. |
| `filesystem-boundary-required` | The generator performs filesystem I/O and is the build-tool boundary that owns backend source reads and generated TypeScript writes. |
| `prefer-public-surfaces` | Generated constants must use the public backend `event_type_key` function and module-owned CAO event tuples, not serializer internals. |
| `respect-standing-decisions` | `CID-1` and `CID-2` require data-only backend reads and registry dispatch from `web/src/components/timelineEventViews.tsx`. |
| `readable-and-explicit` | Payload narrowing, missing-field fallback, and registration contracts must be visible in names and types. |
| `service-definition-surface` | The frontend registry module is reshaped into the self-registration service surface used by discovered view modules. |
| `service-export-discipline` | The registry module export surface changes to support self-registration and must expose only production-facing types/helpers. |
| `well-defined-service` | The frontend event-view registry becomes a small self-registration service for discovered view modules. |

## Task-Specific Code Obligations

- `C-CC-1`: Generated TypeScript event type constants must be produced from backend module-owned CAO event class tuples by calling `event_type_key`; known views must import those constants and must not hand-type fully qualified Python event type key strings.
- `C-CC-2`: Frontend view modules for Linear mention, runtime delivery, workspace context switch, and runtime lifecycle must declare their handled generated constants and self-register through module discovery initiated by `web/src/components/timelineEventViews.tsx`; adding a new view module must not require editing a central manual registry list.
- `C-CC-3`: The taught views must read only the event envelope, selected participant role, and `event.event_data`; they must not depend on backend-authored display titles, summaries, chips, entity references, or presentation DTOs.
- `C-CC-4`: Each taught view must narrow or validate the payload fields it renders and must degrade to readable fallback text for optional or absent facts without throwing.
- `C-CC-5`: Linear mention rows must surface issue title or identifier context, mentioner context when present, a short mention-text snippet, and issue context from typed payload fields.
- `C-CC-6`: Runtime delivery rows must surface the triggering source kind, delivered message, and receiving terminal identifier from typed payload data; if the delivery event payload lacks source/message facts, the implementation must add minimum backend data plumbing to the runtime delivery event payload without adding backend presentation values.
- `C-CC-7`: Workspace context switch rows must surface both `from_workspace_context_id` and `to_workspace_context_id` and may include terminal/outcome context without adding navigation behavior.
- `C-CC-8`: Runtime lifecycle rows must surface lifecycle phase/action, runtime status or health context, terminal identifier when present, and workspace context.
- `C-CC-9`: Backend changes are allowed only for minimum data plumbing required by `t-2` display; backend presentation values, presenter registries, `TimelineEventPresentation`, and `to_timeline_presentation` remain forbidden.
- `C-CC-10`: The event type key generator must construct repository paths with `pathlib.Path` at the build-tool host boundary and must write only the generated TypeScript event key file under `web/src/generated`.
- `C-CC-11`: Frontend view payload field-name constants may duplicate backend dataclass JSON field names only at the typed view boundary, and that intentional duplicate ownership must be documented next to those constants.

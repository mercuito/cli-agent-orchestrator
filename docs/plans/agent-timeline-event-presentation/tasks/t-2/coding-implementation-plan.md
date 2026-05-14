# Coding Implementation Plan — t-2

## Research Findings

- `t-1` established `web/src/components/timelineEventViews.tsx` as the registry owner. `AgentIdentityTimelinePanel.tsx` already dispatches both main and related rows through `eventTimelineViewRegistry.viewFor(event.event_type_key)`, so `t-2` can extend registration without touching row dispatch.
- The current registry contains only fallback rendering and has no generated event key constants, module discovery, or taught view modules.
- Backend event type keys are stable via `src/cli_agent_orchestrator/events/serialization.py:event_type_key`. Linear and runtime event families already expose module-owned `LINEAR_CAO_EVENTS` and `RUNTIME_CAO_EVENTS` tuples; those are the correct backend-owned source for generated frontend constants.
- Linear mention payloads expose `issue_identifier`, `issue_url`, `issue_title`, `app_user_name`, `message_body`, `message_id`, `thread_url`, and related issue/session facts through `event_data`.
- Runtime delivery payloads currently expose terminal and outcome facts but not the triggering `source_kind` or delivered message body. Because `B-3` requires those facts on the runtime delivery row and main-row rendering only receives the row event, this task needs minimum backend data plumbing to add source/message facts to the runtime delivery event payload. Those additions are event facts, not backend presentation values.
- Runtime workspace context switch payloads expose `from_workspace_context_id`, `to_workspace_context_id`, `terminal_id`, `runtime_status`, `outcome`, and `error`.
- Runtime lifecycle payloads expose `action`, `runtime_status`, `workspace_context_id`, `terminal_id`, `ready`, `fresh`, and `error`.
- Existing frontend component tests use inline authored timeline events and rendered React assertions. Existing backend route, Linear, and runtime tests already prove typed payload data is present and must remain green.

## High-Level Architecture

**Generated constants.** Add a small Python generator that scans backend source files for module-owned `*_CAO_EVENTS` tuples, imports only those modules, calls `event_type_key` for each event class, and writes a deterministic TypeScript constants file under `web/src/generated`. The generated file is checked in and refreshed by `web` pretest/prebuild scripts so tests and build use current backend event identities.

**Registry self-registration.** Keep `eventTimelineViewRegistry` in `web/src/components/timelineEventViews.tsx`. Add a production-facing registration type/helper and eager `import.meta.glob` module discovery for sibling view modules. Each view module exports its own registration declaration with generated event constants and a view component; the registry owner performs discovery and registration without a central manual list of event types.

**Backend data plumbing.** Extend `AgentRuntimeNotificationDeliveryEvent` and `notification_delivery_event` with source/message payload fields already available from the inbox notification delivery path. Update runtime tests and any backend API route fixture assertions needed to prove those facts flow as typed `event_data`. Do not add display labels, summaries, presentation DTOs, or presenter registries.

**Known view modules.** Add frontend-owned Linear and runtime view modules near the registry owner. Views use shared local payload guards/formatters to read `event.event_data` safely and render concise row details. Missing optional facts render readable fallback labels such as `Unknown source`, `No message text recorded`, or `No terminal recorded`; malformed payloads do not throw.

**Data flow.** Generic timeline and related-event reads remain data-only: they carry persisted `event_data` through the existing `TimelineEventRead` and API response path without backend-authored presentation values. For runtime delivery events only, this task expands the typed event payload with source/message facts before persistence so the frontend row can render facts the event actually carries. Frontend timeline rows receive API events, the registry resolves the view by generated event type key, and the view renders facts directly from the envelope and typed payload. Unregistered keys continue through the existing fallback.

**Reuse points.** Reuse the `AgentIdentityTimelineEvent` frontend type, existing registry dispatch from `AgentIdentityTimelinePanel.tsx`, existing fallback behavior, lucide icons, Tailwind row styling conventions, existing frontend test builders, and existing backend `event_type_key`.

## Sub-Task List

1. **Red proof for runtime delivery payload facts.**
   - Clauses satisfied: none; this sub-task creates failing proof for the next sub-task.
   - Done condition: focused runtime/backend assertions fail because delivery event `event_data` lacks source kind and message body.
   - Dependency order: first.

2. **Backend runtime delivery data plumbing.**
   - Clauses satisfied: `B-3`, `F-CC-3`, `C-CC-3`, `C-CC-6`, `C-CC-9`, `C-TC-7`.
   - Done condition: focused runtime/backend tests pass and persisted delivery event payloads carry source/message facts with no backend presentation values.
   - Dependency order: after sub-task 1.

3. **Red proof for known frontend presentations and fallback resilience.**
   - Clauses satisfied: none; this sub-task creates failing frontend proof for the known-view implementation sub-tasks.
   - Done condition: focused frontend tests fail because known rows still render through fallback and generated registration is absent.
   - Dependency order: after sub-task 2.

4. **Generated event constants and registry self-registration.**
   - Clauses satisfied: `F-CC-6`, `C-CC-1`, `C-CC-2`, `C-CC-10`, `C-TC-5`.
   - Done condition: generated constants exist, are produced by the backend `event_type_key` function, and `timelineEventViews.tsx` discovers registration modules without a manual event registry list.
   - Dependency order: after sub-task 3.

5. **Linear mention view.**
   - Clauses satisfied: `B-1`, `B-2`, `F-CC-3`, `C-CC-3`, `C-CC-4`, `C-CC-5`, `C-TC-1`, `C-TC-6`.
   - Done condition: the Linear mention test passes with issue context, mentioner context, snippet text, and readable missing-field fallback.
   - Dependency order: after sub-task 4.

6. **Runtime delivery, workspace switch, and lifecycle views.**
   - Clauses satisfied: `B-1`, `B-3`, `B-4`, `B-5`, `F-CC-3`, `F-TC-2`, `C-CC-3`, `C-CC-4`, `C-CC-6`, `C-CC-7`, `C-CC-8`, `C-TC-2`, `C-TC-3`, `C-TC-4`, `C-TC-6`.
   - Done condition: frontend component tests pass for delivery source/message/terminal detail, workspace from/to movement, lifecycle action/status/terminal/workspace context, and optional missing payload fields.
   - Dependency order: after sub-task 4; may run after or alongside sub-task 5.

7. **Focused verification, refactor, and exact command.**
   - Clauses satisfied: all selected coding-level criteria, `C-TC-8`, and `test-validity-preserved`.
   - Done condition: focused frontend tests pass, backend handoff tests remain green, no backend presentation values were introduced, and the exact handoff Verification Command succeeds.
   - Dependency order: last.

## Revision Log

- Revision 1: During post-implementation criteria revisit, added
  `path-utils-required` and `C-CC-10` to the Coding Code Contract because the
  generator constructs repository-relative paths. The existing generator
  already satisfied the revised obligation by using `pathlib.Path` and writing
  only `web/src/generated/caoEventTypeKeys.ts`.
- Revision 2: Final code review required removing unused `source_id` delivery
  payload plumbing, replacing a hard-coded identity name in the Linear mention
  view, selecting `filesystem-boundary-required` and
  `service-definition-surface`, and documenting intentional payload field-name
  duplication at the typed view boundary. The implementation and contracts were
  updated accordingly.
- Revision 3: Final test review required selecting `test-artifact-containment`
  because backend proof persists CAO/runtime rows inside isolated test
  harnesses. The Coding Test Contract and Test Contract Defence were updated.

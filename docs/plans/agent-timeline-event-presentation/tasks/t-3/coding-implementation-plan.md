# Coding Implementation Plan — t-3

## Research Findings

- `AgentIdentityTimelinePanel.tsx` already renders main rows and all related-event groups through `eventTimelineViewRegistry.viewFor(event.event_type_key)`. Related view continuity should preserve that dispatch and add proof that related taught views keep their taught presentation while untaught events keep fallback.
- `web/src/components/timelineEventViews.tsx` currently passes only `event` and `surface` to typed views. Entity-reference navigation needs a production prop surface so typed views can request external or internal navigation without owning dashboard focus logic.
- `knownCaoEventViews.tsx` already owns frontend typed presentations and reads payload facts directly from `event.event_data`. It currently renders Linear issue and runtime terminal facts as passive pills, so this task should replace those with structured affordances only when navigable target facts exist.
- Linear mention payload fixtures already include `issue_url`; runtime delivery payload fixtures already include `terminal_id`. No backend changes are needed because the required target facts are already available as data.
- `AgentPanel.tsx` owns terminal opening and deep-link focus through `api.getTerminal`, `selectSession`, and `openTerminal`; `AgentIdentityTimelinePanel` sits inside it. The narrow production path is to pass a terminal-focus callback from `AgentPanel` down to the timeline panel and then into typed event views.
- Existing `agent-identity-timeline-panel.test.tsx` has reusable identity/event fixtures for timeline rendering and related-event expansion. Existing `agent-panel-deeplink.test.tsx` mocks the Agents panel store/API/TerminalView boundary and is the right owner-surface proof for internal terminal focus.
- The design mock shows entity references as compact right-side row actions. Exact pixel parity is not required, but the UI should expose clear button/link affordances with icons and accessible names.

## High-Level Architecture

**View prop surface.** Extend `TimelineEventViewProps` with optional navigation callbacks: one for external URLs and one for terminal focus. Define small named types in the registry owner module so both the panel and view modules share target vocabulary.

**Entity-reference affordances.** Add local typed-view primitives in `knownCaoEventViews.tsx` for external and internal entity-reference buttons. Linear mention views read `issue_url` and render an external issue button only when it is a non-empty string. Runtime delivery views read `terminal_id` and render an internal terminal button only when it is a non-empty string. Missing target facts remain visible as non-clickable detail pills.

**External navigation.** `AgentIdentityTimelinePanel` supplies a default external opener that calls `window.open(url, '_blank', 'noopener,noreferrer')`. Tests can pass a production-shaped callback directly to the panel.

**Internal terminal focus.** `AgentPanel` passes `focusTimelineTerminal(terminalId)` to `AgentIdentityTimelinePanel`. That callback uses the same public API and state path as existing terminal deep links: `api.getTerminal`, `selectSession(terminal.session_name)`, then `openTerminal(...)`; failures report a snackbar.

**Related-event continuity.** `TimelineRow` and `RelatedEventList` pass identical navigation callbacks into `EventView`, preserving the same typed-view registry dispatch for main and related rows and avoiding a related-only presentation path.

**Reuse points.** Reuse existing `AgentIdentityTimelineEvent` types, generated CAO event constants, the frontend event-view registry, typed-view payload narrowing helpers, lucide icons, existing AgentPanel terminal focus logic, and existing frontend test fixture builders.

## Sub-Task List

1. **Red proof for related taught-view continuity and external reference behavior.**
   - Clauses satisfied: none; this sub-task creates failing proof for later implementation.
   - Done condition: focused identity timeline tests fail because related runtime delivery lacks the taught view assertions or Linear issue reference cannot be followed.
   - Dependency order: first.

2. **Red proof for internal terminal focus through panel and Agents owner boundary.**
   - Clauses satisfied: none; this sub-task creates failing proof for later implementation.
   - Done condition: focused tests fail because runtime delivery terminal references cannot invoke focus from the panel or through `AgentPanel`.
   - Dependency order: after sub-task 1.

3. **Extend registry/view prop surface and pass callbacks through main and related rows.**
   - Clauses satisfied: `B-6`, `C-2`, `F-CC-5`, `F-TC-3`, `C-CC-1`, `C-CC-7`, `C-TC-1`.
   - Done condition: main and related rows compile with shared navigation props and related-event registry tests pass after view affordances land.
   - Dependency order: after red proofs.

4. **Implement Linear external entity reference affordance.**
   - Clauses satisfied: `B-7`, `C-3`, `F-CC-5`, `F-TC-3`, `C-CC-2`, `C-CC-3`, `C-CC-6`, `C-TC-2`, `C-TC-3`.
   - Done condition: Linear mention tests pass for opening the authored issue URL and for no-button readable fallback when `issue_url` is absent.
   - Dependency order: after sub-task 3.

5. **Implement runtime delivery internal terminal reference and AgentPanel focus callback.**
   - Clauses satisfied: `B-8`, `C-3`, `F-CC-5`, `F-TC-3`, `C-CC-2`, `C-CC-4`, `C-CC-5`, `C-CC-6`, `C-TC-4`, `C-TC-5`.
   - Done condition: panel-level focus callback tests and Agents boundary tests pass, with terminal lookup/session selection/`TerminalView` opening through existing owner logic.
   - Dependency order: after sub-task 3.

6. **Refactor and exact verification.**
   - Clauses satisfied: `F-TC-3`, all selected coding-level criteria, `test-validity-preserved`, `C-TC-6`.
   - Done condition: focused tests pass, production code remains frontend-owned/data-only, and the exact handoff Verification Command succeeds.
   - Dependency order: last.

## Revision Log

- Revision 1: Implementation-plan review required explicit coverage of
  inherited feature-level test slice `F-TC-3` in the sub-task list. Added
  `F-TC-3` to the related-view continuity, external-reference,
  internal-reference, and final verification sub-tasks.
- Revision 2: Post-implementation criteria revisit found that the registry
  owner module exports new production-facing navigation callback types and
  that authored `event_data` values directly drive navigation assertions.
  Added `service-export-discipline`, `C-CC-8`, and
  `inspectable-authored-inputs` to the coding-level contracts.

# Agents Tab Unification Tasks (Draft v1)

This task list derives from `docs/plans/agents-tab-unification/plan.md`.

Policy: any task that changes code requires reviewer gate before it is
considered complete. The page cutover (T04) is atomic — its deliverables
land together or not at all.

Every task includes a criteria-catalog acceptance bullet. Before
completion, the implementer walks the catalog at
`docs/criteria/implementation/` and `docs/criteria/tests/` (browseable
via `python scripts/catalog_criteria.py`), identifies every entry whose
`when` clause applies to the task's changes, and confirms the landed
code satisfies it.

This plan inherits the hard-cutover discipline. Forbidden in any task:
shims, facades, fallback chains, feature flags, deprecation warnings,
function/module aliases preserving old import paths, optional props
preserving old behavior, and runtime translators between old and new
shapes. There are no carve-outs. Legacy call sites are migrated to the
new shape or deleted, never bridged.

## Phase 1 — Build the unified detail panel (parallel)

### T01 — Scaffold `AgentDetailPanel` with header and tab shell

- owner_role: developer
- dispatch_mode: handoff
- depends_on: []
- deliverables:
  - new component `web/src/components/AgentDetailPanel.tsx` accepting a
    selected agent (or its id + status) as props
  - status header sub-section: display name, agent id, running/stopped
    badge, active terminal id when running, Start/Stop button
  - tab control with two tabs: `Config` and `Timeline`; active tab state
    held in the component; default `Config`
  - tab content slots empty (placeholders) at this task — content lands
    in T02/T03
  - unit/component tests covering: header renders all expected fields,
    tab control switches active tab, tab state persists across selected
    agent changes
- acceptance:
  - rendering `AgentDetailPanel` with a running agent shows display
    name, id, status badge "running", terminal id, and a Stop button
  - rendering with a stopped agent shows a Start button; clicking it
    fires the existing start endpoint via the same hook/handler used
    elsewhere today
  - switching tabs is purely client-side; selected agent and tab state
    are independent
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or
    deleted, not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T02 — Move Config tab content into `AgentConfigTab`

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - new component `web/src/components/AgentConfigTab.tsx` that renders
    the read-only `agent.toml` view, the prompt.md view, the Linear
    secrets summary, and the Edit / Save / Cancel flow currently
    living inside `AgentPanel.tsx`
  - internals of the config rendering and editing are NOT changed in
    this task — only the location moves. The structured editor is
    a separate plan.
  - the new component is wired into `AgentDetailPanel`'s Config tab
    slot
  - existing tests for the config view/edit behavior moved or
    duplicated to cover the new component path
- acceptance:
  - selecting an agent and viewing the Config tab shows the same
    content as today's lower panel: agent.toml rendered, prompt.md
    rendered, Linear secrets summary present (mask + reveal toggle)
  - clicking Edit produces the same two textareas (agent.toml and
    prompt.md) as today
  - saving submits to the existing `PUT /agents/{id}` endpoint;
    validation errors surface inline as today
  - switching to the Timeline tab and back preserves the agent
    selection but discards in-progress edit drafts (the existing
    behavior; no regression here)
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or
    deleted, not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T03 — Move Timeline tab content into `AgentTimelineTab`

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - new component `web/src/components/AgentTimelineTab.tsx` that
    renders the timeline contents currently in
    `AgentTimelinePanel.tsx`, but WITHOUT the embedded roster (the
    roster is moving to the page level)
  - the new component takes the selected agent id as a prop and
    fetches/refreshes the timeline using the existing endpoints
    (`/agents/{id}/timeline`, related-events expansion)
  - wired into `AgentDetailPanel`'s Timeline tab slot
  - existing timeline tests moved or duplicated to cover the new
    component path
- acceptance:
  - selecting an agent and viewing the Timeline tab shows the same
    timeline content as today's upper panel
  - related-events expansion still works (Direct Cause / Direct Effects
    / Shared Correlation Thread)
  - timeline auto-refresh still happens at the existing interval
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or
    deleted, not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

## Phase 2 — Page cutover (atomic)

### T04 — Unify the Agents tab page layout

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02, T03]
- deliverables:
  - the Agents tab page (currently in `AgentPanel.tsx` or wherever the
    page-level layout lives) is restructured to render exactly one
    roster on the left and one `AgentDetailPanel` on the right
  - `selectedAgentId` lives at the page level and is passed down to
    both roster and detail panel; only one source of truth
  - the lower duplicate roster + direct `AgentTimelinePanel` usage is
    removed; the page no longer renders the timeline-with-its-own-
    roster section
  - the Spawn Agent button and Create New Agent flow remain unchanged
    (still on the page, unchanged behavior)
  - existing page-level tests updated to reflect the new structure
- acceptance:
  - viewing the Agents tab shows one roster on the left and one detail
    panel on the right with `Config | Timeline` tabs
  - selecting an agent updates the detail panel for that agent;
    switching tabs preserves the selection
  - there is no second roster anywhere on the page
  - all existing roster behaviors still work: search, sorting (if any),
    live/stopped badges, click-to-select
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or
    deleted, not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

## Phase 3 — Cleanup

### T05 — Delete obsolete components and finalize tests

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T04]
- deliverables:
  - `web/src/components/AgentTimelinePanel.tsx` deleted if no remaining
    callers (or its non-timeline responsibilities migrated and the file
    removed)
  - any helper functions or component utilities now unused are removed
  - tests for deleted components removed; tests covering the new
    components retained and passing
  - `grep -rn "AgentTimelinePanel" web/src/` returns no hits in
    production code paths
  - `grep -rn "AgentTimelinePanel" web/src/test/` returns no hits or
    only references explicitly testing the removal
- acceptance:
  - the full web test suite passes (`npm test` or `vitest`, whichever
    is configured for this project)
  - no dead imports remain in `web/src/`
  - no console errors appear in the dev build when navigating the
    Agents tab
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or
    deleted, not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

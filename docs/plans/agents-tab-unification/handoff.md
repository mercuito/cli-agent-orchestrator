# Handoff: Agents Tab Unification

## Goal

Execute the Agents tab unification end to end as specified in
`docs/plans/agents-tab-unification/plan.md` and
`docs/plans/agents-tab-unification/tasks.md`. Land the work in dependency
order across the three phases. Each task lands as its own commit (or PR),
gated by reviewer, with the criteria-catalog acceptance bullet satisfied
against the task's diff.

The current page renders two stacked sections, each with its own agent
roster — one driving the status + timeline view, the other driving the
`agent.toml` editor. The goal is one roster + one detail panel for the
selected agent, with internal `Config | Timeline` tabs.

This plan does NOT touch how the config is rendered or edited inside the
Config tab. The raw-TOML textarea stays. A separate follow-up plan will
replace it with a structured form per field. Do not pre-build any of that
structured editing work in this plan.

## Sources of truth (read these first)

- `docs/plans/agents-tab-unification/plan.md` — locked design, layout
  sketch, component shape, state conventions, phasing.
- `docs/plans/agents-tab-unification/tasks.md` — 5 tasks with deliverables
  and acceptance criteria.
- `docs/criteria/implementation/` and `docs/criteria/tests/` — the
  criteria catalog. Run `python scripts/catalog_criteria.py` to browse.
  Every task has a criteria-catalog acceptance bullet; apply every entry
  whose `when` clause matches the task's diff.

## Operating principles

- **Phase 1 is parallel-safe** (T01–T03 build the new components
  without touching the existing page). **T04 is atomic** — the page
  cutover lands together. **T05 is the cleanup pass** after.
- **Hard cutover, no compatibility layers.** Forbidden: keeping the old
  `AgentTimelinePanel` reachable alongside the new unified panel,
  maintaining both rosters in the codebase, optional props preserving
  old behavior, re-exports keeping old import paths alive, runtime
  branches switching between old and new shapes. Old structure is
  deleted in the same landing that introduces the new one.
- **No structured field editor work.** Out of scope for this plan.
  Resist the temptation to "while we're in here, also do X" — that
  expands scope and bleeds into plan 2.
- **No backend changes.** All HTTP endpoints and response shapes stay
  the same. If a task seems to need an API change, raise back.
- **Selection state is a single source of truth.** `selectedAgentId`
  lives at the page level. Both the roster (highlight) and the detail
  panel (content) read from it. No duplicated selection state.
- **Tab state persists across selections.** Switching agents keeps you
  on the same tab. Default tab on first load: `Config`.
- **Criteria catalog per task, not at the end.** Walk the catalog for
  each task's diff before marking it complete. The plan's "Criteria
  catalog (likely applicable)" section lists criteria identified at
  planning time — start there, but the implementer must run
  `uv run python scripts/catalog_criteria.py` against the actual diff
  to confirm the final applicable set.
- **Reviewer gate per task.** No task is complete without reviewer
  approval.

## What is explicitly out of scope

If you encounter these, flag them but do not address them in this work:

- Replacing the raw-TOML textarea editor with a structured form
- Changes to the Spawn Agent modal or Create New Agent flow
- Changes to the left roster's visual design beyond ensuring there is
  exactly one of it
- Changes to any HTTP endpoint shape or response model
- Changes to the timeline event view registry or related-events
  expansion logic
- Performance optimizations not required by the refactor
- Adding new tabs beyond `Config` and `Timeline` (e.g. an Activity
  tab) — that's deferable

## Definition of done

This work is done when **every item below is true**. Verify each one
explicitly; do not infer.

### Page structure

- Viewing the Agents tab shows exactly one agent roster on the left
  side of the page.
- The right side renders a single `AgentDetailPanel` containing a
  status header and `Config | Timeline` tabs.
- `grep -rn "AgentTimelinePanel" web/src/` returns no hits in
  production code paths (deleted or replaced by `AgentTimelineTab`
  inside the unified panel).
- The page-level component holds exactly one `selectedAgentId` and
  passes it down. No duplicated selection state.

### Behavior

- Selecting an agent updates the detail panel for that agent.
- Switching between `Config` and `Timeline` tabs preserves the
  selected agent.
- Switching between selected agents preserves the active tab.
- The status header shows: display name, agent id, running/stopped
  badge, active terminal id (when running), and a Start or Stop
  button depending on state. Start spawns the instance; Stop
  terminates it.
- The Config tab renders the agent.toml view, prompt.md view, and
  Linear secrets summary (with reveal-on-click for client/webhook
  secrets) — identical content to today's lower panel.
- The Config tab's Edit / Save / Cancel flow still submits to
  `PUT /agents/{id}` and surfaces validation errors inline.
- The Timeline tab renders the same event timeline content as today's
  upper panel, including related-events expansion (Direct Cause /
  Direct Effects / Shared Correlation Thread).
- The timeline auto-refresh still occurs at the existing interval.

### Code surface

- `web/src/components/AgentDetailPanel.tsx` exists and is the only
  component used to render the right-hand detail area.
- `web/src/components/AgentConfigTab.tsx` exists and is rendered
  inside `AgentDetailPanel`'s Config tab slot.
- `web/src/components/AgentTimelineTab.tsx` exists and is rendered
  inside `AgentDetailPanel`'s Timeline tab slot.
- `web/src/components/AgentTimelinePanel.tsx` is deleted (or its
  non-timeline contents migrated and the file removed).
- No backwards-compatibility layers remain:
  - no parallel rendering of old and new components
  - no feature flags toggling layouts
  - no re-exports preserving old import paths
  - no optional props preserving old single-panel behavior
- No dead imports remain in `web/src/`.

### Tests

- The full web test suite passes (`npm test` / `vitest`, confirm with
  operator if unclear).
- Tests cover: tab switching preserves selection; agent switching
  preserves active tab; Config tab edit flow; Timeline tab rendering
  and related-events expansion; status header rendering for running
  and stopped agents.
- Tests for deleted components are removed.

### Process

- All 5 tasks have landed commits referencing the task id (e.g. "T01:
  ...").
- Each commit passed the reviewer gate.
- The criteria-catalog acceptance bullet was applied per task — record
  the applicable criteria in the task's PR description or commit
  message, not only in the task spec.

## When to escalate back to the operator

Raise back rather than improvise if:

- A criterion in the catalog seems to conflict with the plan's locked
  design.
- A task's natural implementation seems to require any of the
  forbidden compatibility patterns.
- The current `AgentTimelinePanel.tsx` turns out to be used by a
  surface outside the Agents tab (e.g. embedded in another component)
  that the plan didn't anticipate.
- Scope-expanding decisions arise (e.g. "should this also add a
  structured form for `display_name` while we're here?" — answer is
  no, but raise back if pressure builds).
- Tests reveal a behavior the plan didn't anticipate.

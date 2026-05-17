# Agents Tab Unification (Draft v1)

Status: draft

This plan cleans up the structural duplication on the web Agents tab. Today
the page renders two stacked sections, each with its own agent roster: the
upper one drives the status header + timeline view, and the lower one drives
the `agent.toml` editor. Two parallel "pick an agent and see something about
it" experiences sharing the page. This plan collapses them into one
selector and one composite detail panel with internal `Config | Timeline`
tabs.

This plan does **not** change how the config is rendered or edited — the
Config tab keeps the existing raw-TOML textarea editing. A separate
follow-up plan will replace that with a structured form per field.

---

## Locked design

**Page layout (Agents tab):**

```
┌─ Roster (left, single) ─┬─ Detail panel (right) ──────────────────────┐
│                         │ ┌─ Header (always visible) ───────────────┐ │
│  - Agent A  [running]   │ │ Display name · agent_id · status badge  │ │
│  - Agent B  [stopped]   │ │ Active terminal · Start/Stop button     │ │
│  - Agent C  [stopped]   │ └─────────────────────────────────────────┘ │
│                         │ ┌─ Tabs ──────────────────────────────────┐ │
│  Search…                │ │ [Config] [Timeline]                     │ │
│                         │ ├─────────────────────────────────────────┤ │
│  Spawn / Create…        │ │                                         │ │
│                         │ │  Active tab content                     │ │
│                         │ │                                         │ │
│                         │ └─────────────────────────────────────────┘ │
└─────────────────────────┴─────────────────────────────────────────────┘
```

**Component shape:** the right side becomes one parent component (e.g.
`AgentDetailPanel.tsx`) owning:
- The status header (always visible across tabs).
- The tab control state (`activeTab: 'config' | 'timeline'`).
- The currently selected agent id (passed down from the page).

Tab content sub-components:
- `AgentConfigTab` — renders the raw `agent.toml` view and edit UI that
  currently lives in `AgentPanel.tsx`. Internals unchanged for this plan.
- `AgentTimelineTab` — renders what `AgentTimelinePanel.tsx` shows today,
  minus the duplicate roster (which moves to the page level).

**State conventions:**
- `selectedAgentId` lives at the page level (one source of truth).
- `activeTab` lives in `AgentDetailPanel`. Persists across agent
  selection changes (switching agents keeps you on the same tab).
- Default tab on first load: `Config` (primary use case is
  inspecting/editing).
- `editingAgentId` and edit drafts live inside `AgentConfigTab` and are
  cleared on agent switch or tab switch.

**What stays the same:**
- The roster's contents (name, id, provider, live/stopped status).
- The raw-TOML edit UX inside the Config tab.
- The timeline rendering, event expansion, and related-event behavior.
- All HTTP endpoints. No backend change in this plan.

## Goals

- One agent selector on the Agents tab. No structural duplication.
- One detail panel for the selected agent with `Config | Timeline` tabs.
- A persistent status header visible regardless of which tab is active.
- The Config tab is well-bounded enough that plan 2 (structured field
  editor) can replace its internals without touching the tab shell,
  header, or timeline.

## Non-goals

- No structured field editor. The Config tab keeps raw-TOML textarea
  editing. The structured editor is a separate plan landing after this
  one.
- No new backend endpoints, no changes to existing endpoint shapes.
- No changes to the Spawn Agent modal or the Create New Agent flow.
- No changes to the left roster's appearance beyond ensuring there is
  exactly one of it.
- No changes to baton, monitoring, or flow surfaces.

## Forbidden compatibility patterns

This plan inherits the hard-cutover discipline from the previous
`agent-model-cleanup` work. Forbidden in any task:

- Keeping the old `AgentTimelinePanel.tsx` reachable alongside the new
  unified panel "for safety."
- Maintaining both rosters in the codebase behind a feature flag.
- Optional props that preserve old behavior when omitted (e.g. an
  `enableTabs` prop defaulting to false).
- Re-exports or aliases keeping the old component import paths working.

Old structure is deleted in the same landing that introduces the new
one. Legacy call sites are migrated to the new shape, not bridged.

## Phasing

Three phases. Phase 1 builds the new structure in parallel (no behavior
change). Phase 2 swaps the page over and deletes the old. Phase 3 cleans
up tests and stragglers.

### Phase 1 — Build the unified detail panel (parallel)

T01 scaffolds the new `AgentDetailPanel` with header and tab shell.
T02 moves the Config tab content over. T03 moves the Timeline tab
content over. The new component is reachable from tests but not yet
wired into the page.

### Phase 2 — Page cutover (atomic)

T04 replaces the page-level layout with the unified shape: one roster,
one `AgentDetailPanel`. The lower duplicate roster and direct
`AgentTimelinePanel` usage are removed.

### Phase 3 — Cleanup

T05 deletes the old components/files now made obsolete and updates
remaining tests. Verifies no dangling imports or stale references.

The full task breakdown lives in `docs/plans/agents-tab-unification/tasks.md`.

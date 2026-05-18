# Agent-Centric Terminal UI Cleanup

## Problem

The Agents tab currently mixes three concepts at the same visual level:

- durable agents and their configuration,
- implementation-level sessions,
- terminal rows nested under selected sessions.

This makes terminals feel like something users reach by navigating through
session internals, even though the product model is agent-centric: users choose
an agent, start it, and open that agent's terminal.

Sessions should remain backend/runtime bookkeeping and emergency diagnostics,
not first-class UI in the Agents tab.

## Product Direction

Use this mental model:

```text
Agent = durable object users manage
Terminal = live surface for a running agent
Session = internal runtime grouping
```

## Visual Definition Of Done

The visual target for this cleanup is:

- `docs/plans/agent-terminal-ui-cleanup/mockup.html`

The implemented Agents tab does not need to copy the static mockup byte-for-byte,
but it must preserve the interaction model and visual hierarchy shown there:

- the first viewport is an agent-centric two-column workspace,
- the left panel is the agent list with per-agent runtime actions,
- the selected agent detail owns the live terminal action,
- `New Agent` is a first-class Agents-page action,
- no standalone Sessions card appears below the selected agent,
- no Terminals-in-session card appears below the selected agent,
- terminal ids appear only as supporting runtime metadata or action targets,
- the UI keeps the existing dark/emerald operational styling and compact
  dashboard density.

During implementation review, compare the running dashboard against the mockup
in the browser and treat meaningful drift from the listed hierarchy as a DoD
failure unless the plan is explicitly amended.

The Agents tab should let users do the main workflow without touching sessions:

1. Select an agent.
2. Start it if stopped.
3. Open its terminal if running.
4. Stop it when needed.
5. Configure or inspect its timeline from the selected agent detail.

Terminals remain visible and important, but only in the context of the agent
that owns the runtime.

## Current Surfaces

Relevant frontend code:

- `web/src/components/AgentPanel.tsx`
  - renders the agent list and selected agent detail,
  - renders the separate Sessions card,
  - renders the Terminals-in-session card,
  - owns the spawn modal and terminal overlays.
- `web/src/components/agents-tab/AgentDetailPanel.tsx`
  - renders selected agent header, Config/Timeline tabs, and Start/Stop.
- `web/src/store.ts`
  - stores session lists/details used by both Agents tab and Dashboard home.
- `web/src/components/DashboardHome.tsx`
  - still uses sessions as an operational overview.

Relevant backend/API code already exists:

- `GET /agents` includes `active`, `active_terminal_id`, and last-active state.
- `POST /agents/{agent_id}/start` starts the selected agent and returns terminal
  plus terminal token.
- `GET /agents/runtime/{agent_id}/terminal` resolves a running agent to the
  current terminal and token.
- Existing `/terminals/...` endpoints provide terminal output, inbox, monitoring,
  delete, and websocket behavior.

## Proposed UX

### Agent List

Each agent row should become a compact control surface:

- display name,
- agent id/provider,
- running/stopped badge,
- when stopped: `Start` icon/button,
- when running: `Open Terminal` icon/button,
- optional secondary `Stop` icon/button for running agents.

Clicking the row still selects the agent. Clicking an action should not change
selection unless that makes the action clearer; if it does select, it should do
so intentionally and consistently.

The global `Spawn Agent` modal should be removed from the Sessions card and
replaced by direct agent-row and detail-header actions:

- existing agents: start from their row or selected detail header,
- creating a new durable agent: a clear `New Agent` action in the Agents list
  header, not inside a spawn modal.

### Agent Detail Header

The selected agent header should remain the primary place for runtime actions:

- stopped agent: `Start`,
- running agent: `Open Terminal` and `Stop`,
- show active terminal id as supporting metadata, not as navigation.

The current `Start` button already lives here. Add an `Open Terminal` action for
running agents using `GET /agents/runtime/{agent_id}/terminal` or the stored
`active_terminal_id` plus a token-bearing endpoint.

### Agent Detail Body

Keep durable-agent content focused:

- `Config`
- `Timeline`

Do not add a Sessions tab. Do not show a session list below config.

Timeline terminal links should continue to open the relevant terminal. If they
need tokens, route through an owner API that returns token-bearing terminal
data rather than depending on session detail rows.

### Session/Terminal Diagnostics

For this cleanup, remove session browsing from the Agents tab. Do not delete the
session APIs or store functionality yet because `DashboardHome` and diagnostics
still use them.

If a later pass needs an operator/debug view, make it explicit:

- Dashboard home can remain an operational overview for now.
- A future `Diagnostics` or `Runtime` view may expose raw sessions/terminals for
  orphan cleanup.
- That future view should not be the primary path for opening an agent's
  terminal.

## Implementation Plan

1. Add agent-owned terminal opening.
   - Add a helper in `AgentPanel` such as `openAgentTerminal(agent)` that:
     - no-ops or shows an error if the agent is not running,
     - calls `api.getAgentRuntimeTerminal(agent.agent_id)`,
     - opens `TerminalView` with the returned terminal id/provider/agent id/token.
   - Keep direct terminal opening for timeline event links.

2. Move start/open/stop actions into the agent list rows.
   - Add compact icon buttons with accessible labels and tooltips/titles.
   - Preserve row selection behavior.
   - Avoid large text-heavy buttons in the dense list; use icons where the
     action is familiar.

3. Update `AgentDetailPanel`.
   - Add an `onOpenTerminal(agentId)` prop.
   - When the selected agent is running, render `Open Terminal` next to `Stop`.
   - Keep `Start` for stopped agents.
   - Remove session-name prominence if it makes the header feel internal; keep
     workdir, provider/model, and active terminal summary.

4. Remove the Agents-tab Sessions card and Terminals-in-session card.
   - Delete the rendered sections from `AgentPanel`.
   - Remove now-unused state and handlers from `AgentPanel`:
     - `sessions`,
     - `activeSession`,
     - `activeSessionDetail`,
     - `selectSession`,
     - `deleteSession`,
     - session polling effects,
     - session-derived terminal status polling.
   - Keep terminal overlays (`TerminalView`, `InboxPanel`, `OutputViewer`) only
     if there is still an agent/timeline path that can open them.

5. Keep runtime indicators working where they are still visible.
   - If monitoring/baton indicators remain in the Agents tab, drive them from
     terminal ids available from active agents or remove them from this tab.
   - Do not introduce per-agent polling loops that multiply API calls
     unnecessarily.

6. Preserve creation flow with a clear `New Agent` action.
   - Either keep the current inline create draft logic and expose it from the
     Agents list header, or split it into a small `CreateAgentDialog` component.
   - Do not keep it hidden behind "Spawn Agent"; creating a durable agent and
     starting an existing one are separate actions.

7. Leave Dashboard home alone unless necessary.
   - It can keep showing an operational session overview for now.
   - If implementation reveals duplicated terminal-row UI worth extracting,
     extract only a small shared terminal action row/component and keep behavior
     unchanged.

## Test Plan

Frontend tests should drive the UI through user-visible surfaces:

1. Agent list actions.
   - Given a stopped agent, clicking its Start action calls
     `api.startAgent`, opens the returned terminal, refreshes agents, and does
     not require the Sessions panel.
   - Given a running agent, clicking Open Terminal calls
     `api.getAgentRuntimeTerminal` and opens `TerminalView` with the returned
     token.
   - Given a running agent, clicking Stop calls `api.stopAgent` and refreshes
     agent state.

2. Agent detail header actions.
   - Stopped agent shows Start.
   - Running agent shows Open Terminal and Stop.
   - Open Terminal uses the agent runtime terminal endpoint, not session detail
     rows.

3. Sessions UI removal.
   - Agents tab no longer renders the Sessions card.
   - Agents tab no longer renders the Terminals-in-session card.
   - Existing terminal deep links still open `TerminalView`.
   - Existing agent deep links still resolve through
     `GET /agents/runtime/{agent_id}/terminal`.

4. Create-agent flow.
   - New Agent action remains reachable from the Agents tab.
   - Creating an agent still selects the created agent and opens config editing.

5. Regression boundaries.
   - Dashboard home session overview tests should still pass unchanged unless
     deliberately scoped into this work.
   - Store tests for sessions remain valid because sessions are still used
     outside the Agents tab.

Suggested verification commands:

```bash
cd web && npm test -- --runInBand
cd web && npm run build
```

If backend response contracts change, also run focused backend route tests for
agent runtime terminal endpoints. The preferred plan is frontend-only plus
existing API usage, so backend changes should not be necessary.

## Criteria Catalog

Criteria catalog was reviewed with:

```bash
uv run python scripts/catalog_criteria.py --format json
```

Criteria likely to shape implementation:

- `docs/criteria/implementation/minimal-cohesive-changes.md`
- `docs/criteria/implementation/system-code-locality.md`
- `docs/criteria/implementation/readable-and-explicit.md`
- `docs/criteria/implementation/no-unnecessary-duplication.md`
- `docs/criteria/implementation/prefer-public-surfaces.md`
- `docs/criteria/tests/all-system-behaviors-are-verified-by-tests.md`
- `docs/criteria/tests/given-when-then-test-structure.md`
- `docs/criteria/tests/target-behavior-must-not-be-mocked.md`
- `docs/criteria/tests/test-through-owner-surfaces.md`

Implementation must also follow the frontend design guidance in the active
developer instructions: dense operational UI, icon buttons for familiar actions,
stable dimensions, no nested cards, and no explanatory in-app text where the UI
itself can be clear.

After implementation, evaluate the pending changes against the criteria
catalog. No criteria applicable to the completed diff may be violated.

## Open Decisions

- Should Dashboard home keep its session-oriented operational overview, or
  should a follow-up also make that page agent-centric?
- Should closing/killing a terminal remain exposed in the Agents tab, or should
  the primary Stop action be the only visible destructive runtime control there?
- Should the selected agent automatically switch to a terminal-focused mode
  after Start/Open, or is the modal `TerminalView` enough?
- If multiple terminals per agent become valid later, should the agent detail
  show an "Active terminals" compact list, or should the runtime contract first
  enforce one active terminal per durable agent?

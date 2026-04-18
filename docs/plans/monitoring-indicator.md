# Web UI: "Being Monitored" Indicator

**Status:** in progress. Small follow-up to the monitoring-sessions feature.

## Goal

At-a-glance visual indicator on the dashboard showing which agents currently
have an active monitoring session targeting them. Read-only. No UI for
starting/stopping monitoring yet — that's a separate, intentional follow-up.

## Scope

- New client-side lookup of active monitoring sessions, keyed by
  `terminal_id`. Single API call, piggybacks on the existing 3-second poll
  loop. No backend changes.
- Small `<Eye>` icon next to a terminal's status badge when that terminal
  has an active monitoring session. Tooltip: "Being monitored".
- Rendered on both `DashboardHome` and `AgentPanel` (where terminals
  appear).

## Non-goals (explicitly deferred)

- Starting / ending / deleting sessions from the UI.
- Session detail drill-in (viewing peers, label, log artifact, etc.).
- Hover previews richer than the simple "Being monitored" tooltip.

These are the scope of a follow-up "operator action surface" change
described at the end of the monitoring-sessions plan doc.

## Design decisions

1. **Separate `MonitoringIndicator` component, not a prop on `StatusBadge`.**
   Keeps `StatusBadge` pure (single-responsibility status display). The
   indicator component reads from the store directly and renders nothing
   when the terminal is not monitored — no prop drilling across 5 call
   sites.

2. **Store shape: `monitoredTerminalIds: Record<string, boolean>`.** Matches
   the existing `terminalStatuses: Record<string, string>` pattern. Simpler
   to reason about than `Set` in Zustand updates.

3. **Single API call per poll cycle, client-side derivation.** Call
   `GET /monitoring/sessions?status=active` once, build the map, broadcast.
   Not N+1. No new backend endpoint.

4. **Piggyback on existing poll loops, not new intervals.** DashboardHome
   and AgentPanel each already poll terminal statuses every 3s. Extend
   those loops to also hit monitoring sessions. One extra request per cycle.

## Files

- Add: `web/src/components/MonitoringIndicator.tsx`
- Modify: `web/src/api.ts` — new `listActiveMonitoringSessions()`
- Modify: `web/src/store.ts` — new `monitoredTerminalIds` field + setter
- Modify: `web/src/components/DashboardHome.tsx` — extend poll, render
  indicator next to each status badge
- Modify: `web/src/components/AgentPanel.tsx` — same
- Add: tests in `web/src/test/` — `MonitoringIndicator`, api method,
  store field

## Acceptance

- A terminal with an active monitoring session shows an eye icon next to
  its status badge within ~3 seconds of session creation.
- Ending the session removes the icon within ~3 seconds.
- No visible indicator for non-monitored terminals.
- Vitest suite passes. Manual browser verification: start a session via
  `cao monitor start`, confirm the dashboard lights up.

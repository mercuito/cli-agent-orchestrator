# Web UI: Start / Stop Monitoring Actions

**Status:** in progress.

## Goal

Let operators start and stop monitoring sessions directly from the dashboard.
Today the indicator reports state but doesn't control it; you need the CLI to
create or end a session. This closes that gap.

## Scope

A single action button in each terminal row's action cluster (alongside
Inbox, Output, Terminal, Exit, Delete). Two visual states driven by the
store's `activeMonitoringByTerminal` map:

- No active session → **"Monitor"** button (starts recording).
- Active session → **"Stop"** button (ends it).

Both actions are single-click and operate on defaults. No modal, no popover.
Under the single-session model there's only one thing to start and one thing
to stop — complexity that would have justified a popover (multiple
concurrent sessions) no longer exists.

### Non-goals

- Delete from UI (the session record stays queryable; delete is CLI-only for now).
- Customize label / peers at start time (not needed — peers moved to query
  time; label defaults are fine).
- Advanced "Monitor with options…" path.

## Design decisions

1. **Button label is text, not an icon.** The eye icon is already the
   indicator — reusing it on a button would be ambiguous. Plain text
   (`Monitor` / `Stop`) makes the verb clear.

2. **Default label: `dashboard-HHmmss`.** Identifies operator-initiated
   sessions at a glance when listing. Seconds (not minutes) in the
   timestamp to avoid same-minute collisions if the operator clicks
   rapidly.

3. **No confirmation on click.** Both actions are cheap and reversible in
   effect:
   - Start is idempotent — a mis-click while already monitoring is a no-op
     server-side.
   - Stop only closes the recording window; the session and its messages
     remain fetchable via `cao monitor log`.
   
   Adding a confirm dialog would be friction without protection against
   anything meaningful.

4. **Store refresh via existing poll.** Don't optimistically mutate the
   store on click. The 3-second poll will pick up the new state and the
   button will flip. Slight UI lag is acceptable (≤3s) and keeps a single
   source of truth.

5. **Error handling: snackbar.** Uses the existing `showSnackbar` utility.
   Connection errors surface as "Failed to start monitoring" / "Failed to
   stop monitoring" with the server's detail string if available. No
   custom error state in the button.

6. **Hit the service, not the CLI.** `api.ts` gains `startMonitoring` and
   `endMonitoring` wrappers around the existing `/monitoring/sessions` and
   `/monitoring/sessions/{id}/end` routes. No subprocess, no shell.

## Files

- Modify: `web/src/api.ts` — add `startMonitoring(terminal_id, label?)` and
  `endMonitoring(session_id)`.
- Add: `web/src/components/MonitoringButton.tsx` — small component that
  reads the store, shows `Monitor` or `Stop`, handles the click.
- Modify: `web/src/components/DashboardHome.tsx` — render
  `<MonitoringButton terminalId={t.id} />` in the action cluster.
- Modify: `web/src/components/AgentPanel.tsx` — same.
- Tests: `web/src/test/components.test.tsx` — new `MonitoringButton` tests
  covering the two states, click behavior, and error-path messaging.
- Tests: `web/src/test/api.test.ts` — new api method tests.

## Acceptance

- Clicking **Monitor** on a non-monitored agent creates a session with a
  `dashboard-HHmmss` label and the indicator lights up within ~3 seconds.
- Clicking **Stop** on a monitored agent ends the session and the indicator
  disappears within ~3 seconds.
- A mis-click on **Monitor** while already monitoring does nothing harmful
  (idempotent start returns the existing session).
- Server errors show up as a snackbar; the button doesn't get stuck in a
  loading state.
- Vitest suite passes. Manual browser verification: click Monitor, see the
  eye appear; click Stop, see it disappear.

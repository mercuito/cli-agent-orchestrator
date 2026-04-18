# Monitoring Sessions — Design Record

**Status:** shipped. Single-session model landed across backend, API, CLI, and UI. This document is the design record; update it only if the feature's model genuinely changes.

## Goal

Retrospective visibility into agent-to-agent conversations. Tag a terminal as "being recorded," let it run, then extract readable artifacts of its inbound/outbound messages — optionally scoped to specific peers or time windows at read time.

Primary use case: capturing the reasoning behind an agent-produced artifact (e.g., a review document) so a reviewer can see what exchange led to it, and so operators can compare workflow variants ("does 3 reviewers beat 1?").

## Model

A **monitoring session** is a recording window over the existing `inbox` table. It has four fields worth storing:

- `terminal_id` — the agent being recorded
- `started_at` — when recording began
- `ended_at` — when recording stopped (NULL while active)
- `label` — free-form operator-facing nickname (nullable)

Sessions don't carry peer sets. They capture all inbox activity involving the terminal for their lifetime. Peer and time-window filtering happens at read time via query parameters on the `/messages` and `/log` endpoints.

### What it is not

- **Not** a chat room or multi-party thread primitive.
- **Not** an agent-facing feature. Agents cannot create, inspect, or end monitoring sessions. The API is operator/procedure-facing only.
- **Not** multiple concurrent captures per terminal. A terminal is "recording" or "not recording" — binary state.

## Design decisions

1. **Sessions scope a query; they do not duplicate messages.** The `inbox` table stays the single source of truth. A session is just metadata (when recording started/stopped, who was being recorded).

2. **Not exposed to agents.** No MCP tools. Monitoring is a procedure/operator concern — something happening *to* an agent, not a tool an agent wields.

3. **Filtering is query-time, not session-config-time.** The `/messages` and `/log` endpoints accept repeated `peer` params and `started_after` / `started_before` datetime params. Same recording yields different artifacts via different queries.

4. **Sessions record everything involving the monitored terminal.** No peer scoping at capture. This was originally an option; simplified away because query-time filtering covers the same use cases without the UI and data-model complexity.

5. **One active session per terminal.** `create_session` is idempotent: if an active session already exists for the target terminal, it's returned unchanged — the label argument is ignored in that case. Clicking "Monitor" when already recording is a no-op, not an error. Ended sessions don't count toward this cap.

6. **Persisted until explicit delete.** Sessions are cheap — a few string columns and two timestamps. No TTL, no archive. `DELETE /monitoring/sessions/{id}` removes the record (but not the captured messages, which have their own retention story via `inbox`).

7. **`SessionAlreadyEnded` applies only to `end_session`.** Double-ending a session returns 409 so the operator knows they raced themselves. Double-starting via `create_session` is fine and returns the existing session.

8. **Artifacts self-describe applied filters.** When the `/log` endpoint is called with a peer or time filter, the rendered Markdown adds a `**Filter:** ...` line (and JSON gets a `filter` key) so a saved artifact can't be mistaken for the whole recording.

9. **Sub-window narrowing composes with session bounds.** `started_after` / `started_before` query params AND with the session's own `started_at` / `ended_at` — a caller can't read past the session window by asking for a broader range.

10. **FK enforcement stays on.** The `monitoring_session_peers` table is gone but the `PRAGMA foreign_keys=ON` connect hook remains; it protects any future schema additions.

## Schema

```
monitoring_sessions
  id           TEXT PRIMARY KEY
  terminal_id  TEXT NOT NULL
  label        TEXT NULL
  started_at   DATETIME NOT NULL
  ended_at     DATETIME NULL        -- NULL = still recording
```

One row per session. Indexed implicitly on `id` (primary key); no other indexes — volume is low.

Migration: a legacy `monitoring_session_peers` table is dropped at startup via `_migrate_drop_monitoring_session_peers`. Idempotent (no-op when the table is absent).

## API surface

All routes under `/monitoring/`. Not registered as MCP tools.

| Verb | Path | Notes |
|---|---|---|
| POST | `/monitoring/sessions` | body: `{terminal_id, label?}` → 201 (idempotent) |
| GET | `/monitoring/sessions` | filters: `terminal_id`, `status` (`active`\|`ended`), `label`, `started_after`, `started_before`, `limit`, `offset` |
| GET | `/monitoring/sessions/{id}` | 404 if missing |
| POST | `/monitoring/sessions/{id}/end` | 409 if already ended |
| GET | `/monitoring/sessions/{id}/messages` | query-time filters: `peer` (repeatable), `started_after`, `started_before` |
| GET | `/monitoring/sessions/{id}/log` | same filters as `/messages`; `?format=markdown\|json` |
| DELETE | `/monitoring/sessions/{id}` | 204 (session metadata only; messages untouched) |

### Message query (`get_session_messages`)

Base predicate (always applied):
```sql
(sender_id = terminal OR receiver_id = terminal)
  AND created_at >= session.started_at
  AND (session.ended_at IS NULL OR created_at <= session.ended_at)
```

Optional query-time filters layer on top:
```sql
  AND (peers IS empty OR sender_id IN peers OR receiver_id IN peers)
  AND (:started_after IS NULL OR created_at >= :started_after)
  AND (:started_before IS NULL OR created_at <= :started_before)
```

`peers=[]` is treated the same as `peers=None` — no filter. Prevents a UI with an empty multi-select from silently returning nothing.

## CLI surface

```
cao monitor start    --terminal T [--label L]
cao monitor end      <session_id>
cao monitor list     [--terminal T] [--active] [--ended] [--label L] [--limit N] [--offset N]
cao monitor show     <session_id>
cao monitor log      <session_id> [--format markdown|json]
                     [--peer P ...] [--since ISO] [--until ISO]
cao monitor delete   <session_id>
```

`CAO_API_HOST` / `CAO_API_PORT` env vars override the server target (defaults: `127.0.0.1:9889`).

## Web UI surface

Indicator (shipped):
- Small sky-blue eye icon with a pulsing red dot next to a terminal's status badge when a session is recording it.
- Hover shows a tooltip with the session's label and age.
- Rendered via React portal with fixed positioning so it escapes the dashboard's `overflow-hidden` session card.

Operator action buttons (separate follow-up, not shipped at time of this record):
- "Monitor" button when no active session. One click starts with defaults (label `dashboard-HHmmss` or similar).
- "Stop" button when an active session exists. One click ends it.
- Single button toggles based on store state. Simple because the model is simple — no popover, no multi-session UI.

## Simplification history

The feature originally shipped with a multi-session, peer-scoped design (overlapping concurrent sessions per terminal, each carrying a peer set; session-level `add_peers`/`remove_peer` mutations; UI popover for disambiguating stop actions).

During post-ship review the operator observed that:
- Every scenario the multi-session model was trying to address (run-level + step-level captures, per-reviewer scoping, etc.) can be satisfied by one session + query-time filters.
- The complexity was real: UI popovers, duplicate storage, retroactive peer filtering semantics, concurrent-mutation edge cases, label-collision disambiguation.
- The value was marginal.

The model was simplified in Phases 1–5:
1. Schema + service (drop `monitoring_session_peers`, make `create_session` idempotent, move peer filter to query time on `get_session_messages`).
2. HTTP API + formatter (drop peer routes, add query-time filter params, artifact self-describes applied filter).
3. CLI (drop peer-related flags on `start`/`list`, add filter flags on `log`).
4. Web UI (flip store shape, simplify tooltip, drop multi-session rendering).
5. Docs (this rewrite).

The capabilities lost: session-level peer scoping as a setup-time option; concurrent captures with different purposes on the same terminal. Both were addressing needs better solved by filtering the unscoped recording at read time.

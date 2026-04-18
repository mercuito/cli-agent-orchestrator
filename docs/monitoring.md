# Monitoring Sessions

Retrospective visibility into agent-to-agent conversations. Start recording an
agent's inbox activity, let it run, extract readable artifacts — filtered by
peer or time window at read time — and optionally stop when you're done.

Primary use case: capturing the reasoning behind an agent-produced artifact
(e.g., a review document) so reviewers can see what exchange led to it, and
so operators can compare workflow variants.

## Model

A **monitoring session** is a recording window over CAO's existing `inbox`
table, scoped to a single agent (terminal). It records everything involving
that terminal from `started_at` until `ended_at` (or until now, if
still active).

Sessions don't carry peer sets or message filters. They capture all inbox
activity involving the monitored terminal. If you only want messages with a
specific peer, or from a specific time sub-window, you ask for that at read
time — one recording, many possible views.

### What it is not

- **Not** a chat room or multi-party thread primitive.
- **Not** an agent-facing feature. Agents cannot create, inspect, or end
  monitoring sessions. The API is operator/procedure-facing only.
- **Not** multiple concurrent captures per terminal. `create_session` is
  idempotent on active state — calling it twice on the same terminal returns
  the same session both times.

## HTTP API

All routes under `/monitoring/`. Full reference in [`api.md`](api.md).

| Verb | Path | Purpose |
|---|---|---|
| POST | `/monitoring/sessions` | Start recording (idempotent) |
| GET | `/monitoring/sessions` | List sessions (filterable) |
| GET | `/monitoring/sessions/{id}` | Show a single session |
| POST | `/monitoring/sessions/{id}/end` | Stop recording |
| GET | `/monitoring/sessions/{id}/messages` | Raw message list (filterable) |
| GET | `/monitoring/sessions/{id}/log` | Rendered artifact (filterable) |
| DELETE | `/monitoring/sessions/{id}` | Delete session metadata (messages untouched) |

The `/messages` and `/log` endpoints accept query-time filters:
`peer=X&peer=Y` (repeatable), `started_after=<iso>`, `started_before=<iso>`.

## CLI

```bash
cao monitor start    --terminal T [--label L]            # prints session id
cao monitor end      <session_id>
cao monitor list     [--terminal T] [--active] [--ended] [--label L]
cao monitor show     <session_id>
cao monitor log      <session_id> [--format markdown|json]
                     [--peer P ...] [--since ISO] [--until ISO]
cao monitor delete   <session_id>
```

Every command talks to the local `cao-server`. Override the server target
with `CAO_API_HOST` / `CAO_API_PORT` (defaults: `127.0.0.1:9889`).

Session rows live in the CAO SQLite database alongside the `inbox` table
(`~/.aws/cli-agent-orchestrator/db/cli-agent-orchestrator.db` by default).

## Typical flow

```bash
# 1. Start recording an implementer terminal
session_id=$(cao monitor start --terminal impl-abc123 --label review-v2)

# 2. (Agents do their work via the usual assign/send_message primitives.)

# 3. Fetch an artifact at any point — active or ended — and optionally scope.
cao monitor log "$session_id" > review-full.md
cao monitor log "$session_id" --peer rev-def456 > review-only-rev.md

# 4. Stop recording when the work is done.
cao monitor end "$session_id"

# 5. The artifact remains fetchable after ending; delete only when you no
#    longer need the session metadata.
cao monitor delete "$session_id"
```

## Query-time filtering

Because the recording captures everything, you can generate multiple
different artifacts from a single session:

```bash
# Full conversation
cao monitor log "$session_id" > transcript-full.md

# Just the exchange with reviewer R1 (sender OR receiver = R1)
cao monitor log "$session_id" --peer R1 > transcript-r1.md

# Just the "step 3" sub-window (messages within an explicit time range)
cao monitor log "$session_id" \
  --since 2026-04-18T10:15:00 \
  --until 2026-04-18T10:22:00 \
  > transcript-step3.md
```

Artifacts self-describe their filter: the Markdown header gets a
`**Filter:** ...` line, and the JSON payload gets a `filter` key, so a saved
file can't be mistaken for the unfiltered recording.

## Idempotent start

Calling `cao monitor start --terminal T` when `T` already has an active
session returns the existing session's id — no duplicate is created, and
no error is raised. The UI uses this directly: clicking "Monitor" when
already monitoring is a safe no-op.

To check whether a terminal is currently being recorded:

```bash
cao monitor list --terminal T --active
```

## Yards procedure integration

The intended orchestration layer is **yards**, an external workflow framework.
A procedure can bracket a review step with monitoring:

```yaml
- blockId: startMonitor
  handler: shell
  properties:
    command: cao monitor start --terminal ${implementerTerminal} --label "review-${runId}"
  outputs:
    - { portId: sessionId, schema: string }

- blockId: runReview
  handler: ...  # the actual review step — agents don't know monitoring exists

- blockId: exportArtifacts
  handler: shell
  properties:
    command: |
      cao monitor log ${sessionId} --format markdown > ${artifactDir}/review-full.md
      cao monitor log ${sessionId} --peer ${reviewerTerminal} > ${artifactDir}/review-r1.md
      cao monitor end ${sessionId}
```

From the agents' perspective: nothing changes. They send messages and receive
replies exactly as before. The session lives entirely in the
procedure/operator layer.

## Design decisions (summary)

See [`plans/monitoring-sessions.md`](plans/monitoring-sessions.md) for the full
design record. Load-bearing choices:

1. **Sessions scope a query; they do not duplicate messages.** The `inbox`
   table remains the single source of truth.
2. **Not exposed to agents.** No new MCP tools. Monitoring is a
   procedure/operator concern.
3. **One active session per terminal.** `create_session` is idempotent on
   active state; double-starting is a no-op.
4. **Filtering is query-time.** Peer and time-window filters live on
   `/messages` and `/log`, not on the session record.
5. **Artifacts self-describe applied filters** so a saved slice can't be
   mistaken for the whole recording.
6. **Persisted until explicit delete.** Ended sessions remain queryable.

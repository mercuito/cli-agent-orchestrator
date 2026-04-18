# Monitoring Sessions

Retrospective visibility into agent-to-agent conversations. Tag a terminal, let
it run, then fetch a readable artifact of its inbound and outbound messages.

Primary use case: capturing the reasoning behind an agent-produced artifact
(e.g., a review document) so reviewers can see what exchange led to it, and
so workflow operators can compare variants ("does 3 reviewers beat 1?").

## Model

A **monitoring session** is a query window over CAO's existing `inbox` table.
It carries:

- a **monitored terminal** (whose inbound/outbound messages are captured)
- an optional **peer set** — if empty, the session captures all peers; if
  populated, only messages involving one of those peers are captured
- a **start time** (set at creation), and an **end time** (null while active)
- an optional free-form **label**

Sessions don't duplicate messages. They just scope a filter. Deleting a
session removes only the session metadata — the underlying inbox messages are
untouched. Session rows live in the CAO SQLite database alongside the
`inbox` table (`~/.aws/cli-agent-orchestrator/db/cli-agent-orchestrator.db`
by default).

### What it is not

- **Not** a chat room or multi-party thread primitive.
- **Not** an agent-facing feature. Agents cannot create, inspect, or end
  monitoring sessions. The API is operator/procedure-facing only. See
  `docs/plans/monitoring-sessions.md` design decision #2.
- **Not** a real-time stream. Sessions are queried on demand.

## HTTP API

All routes are under `/monitoring/`. Full endpoint reference in
`docs/api.md`. Quick tour:

| Verb | Path | Purpose |
|---|---|---|
| POST | `/monitoring/sessions` | Create a session |
| GET | `/monitoring/sessions` | List sessions (filterable) |
| GET | `/monitoring/sessions/{id}` | Show a single session |
| POST | `/monitoring/sessions/{id}/end` | End an active session |
| POST | `/monitoring/sessions/{id}/peers` | Add peers to an active session |
| DELETE | `/monitoring/sessions/{id}/peers/{peer_id}` | Remove a peer |
| GET | `/monitoring/sessions/{id}/messages` | Raw message list |
| GET | `/monitoring/sessions/{id}/log?format=markdown\|json` | Rendered artifact |
| DELETE | `/monitoring/sessions/{id}` | Delete a session (messages untouched) |

## CLI

```bash
cao monitor start    --terminal T [--peer P ...] [--label ...]   # prints session id
cao monitor end      <session_id>
cao monitor add-peer <session_id> <peer_id>
cao monitor remove-peer <session_id> <peer_id>
cao monitor list     [--terminal T] [--peer P] [--involves X] [--active] [--label ...]
cao monitor show     <session_id>
cao monitor log      <session_id> [--format markdown|json]        # stdout
cao monitor delete   <session_id>
```

Every command talks to the local `cao-server`. Most support `--json` for
structured output. Override the server target with `CAO_API_HOST` /
`CAO_API_PORT` environment variables (defaults: `127.0.0.1:9889`).

## Typical flow

```bash
# 1. Start a session around an implementer's terminal, scoped to one reviewer.
session_id=$(cao monitor start --terminal impl-abc123 --peer rev-def456 --label review-v2)

# 2. (The implementer and reviewer do their work via normal assign/send_message.)

# 3. Fetch the markdown artifact at any time (session can be active or ended).
cao monitor log "$session_id" > review-transcript.md

# 4. End the session when the review is done.
cao monitor end "$session_id"
```

## Retroactive peer filter

The peer set is a query-time filter, not a capture-time filter. Adding a peer
mid-session exposes earlier in-window messages involving that peer. Removing
a peer hides them.

If you want "prospective-only" semantics (the peer should only affect
messages going forward), end the session and start a new one with the
expanded peer set. The monitored terminal's ongoing activity is unaffected.

## Yards procedure integration

The intended orchestration layer is **yards**, an external workflow
framework that drives agents through declarative procedures. A procedure can
bracket a review step with monitoring, dropping the artifact next to the
output:

```yaml
- blockId: startMonitor
  handler: shell
  properties:
    command: cao monitor start --terminal ${implementerTerminal} --peer ${reviewerTerminal} --label "review-${runId}"
  outputs:
    - { portId: sessionId, schema: string }

- blockId: runReview
  handler: ...  # the actual review step — agents don't know monitoring exists

- blockId: exportArtifact
  handler: shell
  properties:
    command: |
      cao monitor log ${sessionId} --format markdown > ${artifactDir}/review-transcript.md
      cao monitor end ${sessionId}
```

From the agents' perspective: nothing changes. They send messages and receive
replies exactly as before. The session lives entirely in the
procedure/operator layer.

## Design decisions (summary)

See `docs/plans/monitoring-sessions.md` for the full discussion. Load-bearing
choices:

1. **Sessions scope a query; they do not duplicate messages.** Fewer moving
   parts, no write amplification, the `inbox` table remains the single
   source of truth.
2. **Not exposed to agents.** No new MCP tools. Conversation boundaries are
   the procedure's concern, not the agent's.
3. **Retroactive peer filter by default.** Simpler model; the
   end-and-restart idiom covers the prospective case when needed.
4. **Persisted until explicit delete.** Sessions are cheap — filter a couple
   of strings and a timestamp range. No TTL, no archive.
5. **Ended sessions are immutable w.r.t. peer set.** Mutation on an ended
   session returns `409`. If the window closed, the peer set closed with it.

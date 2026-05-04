# CAO Baton Control Roadmap (Draft v1)

Status: draft

This document proposes a minimal baton primitive for CLI Agent Orchestrator
(CAO): an async control token that identifies which agent currently owes the
next move in a multi-agent workflow.

The motivating workflow is document-driven implementation with direct
author-reviewer conversation. The orchestrator should not have to marshal every
review finding from reviewer to author. Instead, control can move directly:

```text
orchestrator -> implementer -> reviewer -> implementer -> orchestrator
```

The baton makes that control movement observable, persistent, and recoverable
without forcing all work through blocking `handoff`.

---

## Goals

- Add a small tracked async obligation primitive between `assign` and `handoff`.
- Let an orchestrator create work, end its turn, and be reactivated when the
  work returns or completes.
- Let an implementer pass control to a reviewer without the orchestrator
  relaying messages.
- Nudge the current holder if they go idle while still holding unresolved
  control.
- Surface active baton ownership in the dashboard so operators can see who has
  control right now.
- Reuse CAO's existing inbox delivery, terminal status detection, monitoring,
  and dashboard concepts where possible.

## Non-goals (v1)

- No full workflow engine or scheduler.
- No parallel fanout/fanin batons in the MVP.
- No automatic semantic judgment of whether an agent's work is correct.
- No automatic baton completion from idle/completed terminal status.
- No replacement for monitoring sessions. Monitoring records message history;
  batons record current obligation ownership.

---

## Core Model

A baton has exactly one current holder while active.

```text
originator: terminal that created the baton
current_holder: terminal currently responsible for the next move
return_stack: terminals that should receive the baton when it returns
status: active | completed | blocked | canceled | orphaned
```

The baton is transferable. The transfer operation both updates state and sends
the message to the next holder.

```text
create_baton(holder=implementer)
pass_baton(to=reviewer)
return_baton()      # reviewer -> implementer
complete_baton()    # implementer -> originator or resolved
```

The current holder is the only normal actor allowed to pass, return, block, or
complete the baton. The originator or an operator may force-cancel or
force-reassign as a recovery action.

## Baton vs Monitoring

Monitoring is operator-facing recording over the inbox table. It answers:

> What messages happened involving this terminal during this time window?

Batons are agent-facing control obligations. They answer:

> Who currently owes the next move for this workflow?

The dashboard can show both. A monitored terminal may or may not hold a baton,
and a baton holder may or may not be actively monitored.

---

## MVP Behavior

### Create

An orchestrator creates a baton for an assigned implementer:

```text
create_baton(
  title="t-1 implementation",
  holder_id="<implementer-terminal>",
  message="Implement task t-1. Pass this baton to review before returning."
)
```

CAO persists the baton, appends an event, and queues the message to the holder's
inbox.

### Pass

The holder passes control to another agent:

```text
pass_baton(
  baton_id="...",
  receiver_id="<reviewer-terminal>",
  message="Review these artifacts and return findings."
)
```

CAO pushes the current holder onto the return stack, sets the reviewer as
current holder, appends an event, and queues the message to the reviewer.

### Return

The reviewer returns control:

```text
return_baton(
  baton_id="...",
  message="Changes requested: ..."
)
```

CAO pops the previous holder from the stack, sets that terminal as current
holder, appends an event, and queues the return message.

### Complete

The current holder completes the baton:

```text
complete_baton(
  baton_id="...",
  message="Approved implementation complete. Artifacts: ..."
)
```

CAO marks the baton completed, appends an event, and notifies the originator.
If the originator terminal is idle/completed, the message is delivered through
the existing inbox delivery path and can kick the orchestrator into its next
turn.

### Block

The current holder can block the baton:

```text
block_baton(
  baton_id="...",
  reason="Reviewer found an upstream contract mismatch."
)
```

CAO marks the baton blocked and notifies the originator and previous return
target, if any.

---

## Idle Nudge Policy

A lightweight watchdog checks active batons.

For each active baton:

1. Look up `current_holder`.
2. Check terminal status.
3. If holder is `idle` or `completed` and the baton has had no event for the
   configured grace period, send a reminder to the holder.
4. Rate-limit reminders per baton.

Reminder text should be gentle and mechanical:

```text
You are holding baton <id>: <title>.
Expected next action: <expected_next_action>.
If you are done, call complete_baton, return_baton, pass_baton, or block_baton.
```

Idle detection is advisory. It never completes or transfers a baton by itself.

If the current holder terminal no longer exists, the baton becomes `orphaned`
and the originator is notified.

---

## Data Model Sketch

```text
batons
  id                  TEXT PRIMARY KEY
  title               TEXT NOT NULL
  status              TEXT NOT NULL
  originator_id        TEXT NOT NULL
  current_holder_id    TEXT NULL
  return_stack_json    TEXT NOT NULL
  expected_next_action TEXT NULL
  created_at           DATETIME NOT NULL
  updated_at           DATETIME NOT NULL
  last_nudged_at       DATETIME NULL
  completed_at         DATETIME NULL

baton_events
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  baton_id         TEXT NOT NULL
  event_type       TEXT NOT NULL
  actor_id         TEXT NOT NULL
  from_holder_id   TEXT NULL
  to_holder_id     TEXT NULL
  message          TEXT NULL
  created_at       DATETIME NOT NULL
```

The event table is the audit trail. It is also the best source for a future UI
timeline.

---

## MCP Surface

Agent-facing tools:

- `create_baton(title, holder_id, message, expected_next_action?, artifact_paths?)`
- `pass_baton(baton_id, receiver_id, message, expected_next_action?, artifact_paths?)`
- `return_baton(baton_id, message, expected_next_action?, artifact_paths?)`
- `complete_baton(baton_id, message, artifact_paths?)`
- `block_baton(baton_id, reason, artifact_paths?)`
- `get_my_batons(status?)`
- `get_baton(baton_id)`

Operator/admin-facing recovery can start as HTTP/CLI only:

- cancel baton
- force reassign baton

Design rule: a transfer tool sends the inbox message as part of the same
service operation. Avoid separate `send_message` + `pass_baton` calls that can
drift out of sync.

---

## API and UI Surface

HTTP API:

- `GET /batons`
- `GET /batons/{id}`
- `GET /batons/{id}/events`
- `POST /batons/{id}/cancel`
- `POST /batons/{id}/reassign`

Dashboard:

- Show a baton indicator on terminal rows/cards when the terminal is current
  holder.
- Show active baton count and the most recent baton title.
- Add a baton panel or popover with:
  - title
  - status
  - current holder
  - originator
  - return chain
  - last movement age
  - expected next action
  - recent events

The first UI can be read-only. Recovery actions can remain CLI/API until the
model proves itself.

---

## Open Questions

- Should `complete_baton` always notify the originator, or notify the previous
  return target when a return stack remains?
- Should baton creation be combined with `assign`, or stay explicit as
  `assign` plus `create_baton` for v1?
- Should active baton indicators appear next to monitoring indicators or in a
  separate control column?
- What grace period and nudge interval feel useful without being noisy?
- How should a baton link to persisted planning artifacts: free-form paths,
  structured artifact list, or both?

## Recommendation

Start with one-holder, no-fanout batons. Implement the backend service, MCP
tools, a nudge loop, and read-only dashboard visibility. Use it to run one
linear implementation-review loop before adding child batons or richer workflow
automation.

---
id: 0008
status: ready
type: AFK
title: AgentReady event drives inbox delivery
parent: 0003
blocked_by: [0004]
labels: [inbox-refactor]
github_origin: 8
---

## Parent

[#0003](0003-inbox-collapse-umbrella.md)

## What to build

Replace the explicit runtime → inbox poll with an event subscription.

- Define `AgentReady` `CaoEvent` in `events/` carrying `agent_id`. Register it with the default dispatcher.
- `runtime/agent.py` publishes `AgentReady` after `ensure_fresh_started` whenever a terminal lands in a ready state (initial boot completion, post-restart, post-rehome, post-workspace-switch).
- `inbox/readiness.py` (created in [#0005](0005-inbox-plain-send.md)) subscribes to `AgentReady` at package init. On the event, it attempts delivery of any pending notifications for that agent.
- `runtime/agent.py` `try_deliver_pending` removes its `inbox_service.check_and_send_pending_messages` call. The runtime no longer imports inbox.
- The watchdog file observer remains as a parallel trigger; restarts that produce an idle prompt will fire the file watcher. `AgentReady` covers the cases where the file content is unchanged at the readiness moment.

Tracer test:

> Given agent A with a pending notification queued for a not-yet-live terminal,
> when the runtime brings A's terminal up and `ensure_fresh_started` completes,
> then `AgentReady` is published with `agent_id=A`,
> and the inbox readiness subscriber sees the event,
> and delivery is attempted (tmux `send_keys` recorded; notification marked DELIVERED).

## Acceptance criteria

- [ ] `AgentReady` CaoEvent defined and registered.
- [ ] `runtime/agent.py` publishes `AgentReady` after `ensure_fresh_started`.
- [ ] `inbox/readiness.py` subscribes to `AgentReady`.
- [ ] `runtime/agent.py` no longer imports inbox modules for delivery purposes.
- [ ] Tracer test passes.
- [ ] All applicable criteria from `docs/criteria/` applied.
- [ ] PR opens as draft with sparse orientation comments.

## Review Gate

After implementing this task, run a review loop. The reviewer compares the landed implementation against each item in Acceptance criteria above plus all applicable entries in the `docs/criteria` catalog (run `uv run python scripts/catalog_criteria.py` and load any criterion whose `when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the review loop restarts with a fresh reviewer. For every review finding that requires an implementation change, the implementer updates [../completion-report.md](../completion-report.md) under this task's heading, recording what the reviewer found, why it was accepted as valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero valid findings for this task, and those two clean review passes are recorded in the completion report.

## Blocked by

- [#0004](0004-inbox-schema-cutover.md) — schema must be in place. Can run in parallel with [#0005](0005-inbox-plain-send.md) – [#0007](0007-inbox-source-registry-reply.md) once the package skeleton exists; if [#0005](0005-inbox-plain-send.md) hasn't landed yet, add a minimal `inbox/readiness.py` here to host the subscriber.

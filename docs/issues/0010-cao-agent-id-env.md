---
id: 0010
status: ready
type: AFK
title: CAO_TERMINAL_ID → CAO_AGENT_ID in tmux env + agent prompts
parent: 0003
blocked_by: [0005]
labels: [inbox-refactor]
github_origin: 10
---

## Parent

[#0003](0003-inbox-collapse-umbrella.md)

## What to build

Finish the agent-commitment external surface.

- `clients/tmux.py` sets `CAO_AGENT_ID` env var when creating a terminal session, replacing `CAO_TERMINAL_ID`.
- Agent prompt templates (under `agent_store/`, `examples/`, and any in-repo agent definition files) updated to reference `CAO_AGENT_ID` and to use `send_message(receiver_agent_id=...)` in their inline guidance.
- All `CAO_TERMINAL_ID` references removed from source and prompts.
- Existing tests for tmux env-var setting and agent prompts updated.

Tracer:

> Given a newly created terminal,
> the tmux pane's environment contains `CAO_AGENT_ID=<agent_id>` and not `CAO_TERMINAL_ID`,
> and the agent's rendered prompt instructs use of `CAO_AGENT_ID` for `send_message` routing.

## Acceptance criteria

- [ ] tmux client sets `CAO_AGENT_ID`; no `CAO_TERMINAL_ID` emitted.
- [ ] Agent prompt templates updated across all in-repo provider definitions.
- [ ] No references to `CAO_TERMINAL_ID` remain in source or prompts.
- [ ] Tests updated.
- [ ] All applicable criteria from `docs/criteria/` applied.
- [ ] PR opens as draft with sparse orientation comments.

## Review Gate

After implementing this task, run a review loop. The reviewer compares the landed implementation against each item in Acceptance criteria above plus all applicable entries in the `docs/criteria` catalog (run `uv run python scripts/catalog_criteria.py` and load any criterion whose `when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the review loop restarts with a fresh reviewer. For every review finding that requires an implementation change, the implementer updates [../completion-report.md](../completion-report.md) under this task's heading, recording what the reviewer found, why it was accepted as valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero valid findings for this task, and those two clean review passes are recorded in the completion report.

## Blocked by

- [#0005](0005-inbox-plain-send.md) — the MCP `send_message` parameter rename lands in 0005; this slice finishes the picture in agent-visible env + prompts.

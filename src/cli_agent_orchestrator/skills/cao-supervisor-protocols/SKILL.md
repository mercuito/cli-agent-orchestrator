---
name: cao-supervisor-protocols
description: Supervisor-side orchestration patterns for assign, handoff, baton control, and idle inbox delivery in CAO
---

# CAO Supervisor Protocols

Use this skill when supervising worker agents through CLI Agent Orchestrator.

This skill covers how supervisors should dispatch work, decide between `assign`, `handoff`, and baton-controlled work, and receive worker results without blocking inbox delivery.

## Core MCP Tools

From `cao-mcp-server`, supervisors orchestrate work with:

- `assign(agent_profile, message)` for asynchronous work that returns immediately
- `handoff(agent_profile, message)` for synchronous work that blocks until the worker finishes
- `send_message(receiver_id, message)` for direct messages to an existing terminal

Some CAO deployments may also expose baton tools while baton control is being
implemented:

- `create_baton(title, holder_id, message, expected_next_action?, artifact_paths?)`
- `pass_baton(baton_id, receiver_id, message, expected_next_action?, artifact_paths?)`
- `return_baton(baton_id, message, expected_next_action?, artifact_paths?)`
- `complete_baton(baton_id, message, artifact_paths?)`
- `block_baton(baton_id, reason, artifact_paths?)`
- `get_my_batons(status?)`
- `get_baton(baton_id)`

Baton tools are the planned transfer surface for tracked async control. Use
them when they are available and the workflow asks for baton control.

Your own terminal ID is available in the `CAO_TERMINAL_ID` environment variable. Use it when you need workers to send results back to you.

## Choosing Between Assign, Handoff, and Baton

Use `assign` when the worker should continue independently and report back later. This is the normal pattern for fan-out work or parallel execution.

Use `handoff` when the next step is blocked on the worker result. The orchestrator waits for completion, captures the worker output, and returns it directly to the supervisor.

Baton control sits between `assign` and `handoff`. Use a baton when work should
continue asynchronously, but there must be a persistent answer to "who owes the
next move?" A baton has one current holder, records transfers, and can return
control to the originator when the work completes or blocks.

Typical pattern:

- Use `assign` for analysis, research, or code changes that can run in parallel.
- Use `handoff` for report generation, blocking review steps, or any task where you need the result before you can continue.
- Use `create_baton` for async workflows that need tracked control transfer, such as implementer-reviewer-implementer loops.

## Baton Protocol

When baton tools are available, create a baton after you have an assigned or
existing worker terminal that should own the next move:

```text
create_baton(
  title="T08 docs/protocol update",
  holder_id="<implementer-terminal>",
  message="Implement the docs slice. Pass this baton to review before returning.",
  expected_next_action="Update protocol docs, then pass to reviewer."
)
```

The baton message should be self-contained. Include the task, the expected next
action, any artifact paths, and the rule that transfer tools move both control
and the message.

Do not use a separate `send_message` to simulate a baton transfer. Planned
transfer tools such as `pass_baton`, `return_baton`, `complete_baton`, and
`block_baton` update baton state and deliver the inbox message as one
operation. A separate message can notify an agent, but it does not change who
holds the baton.

In a review loop, expect this shape:

```text
supervisor:  create_baton(holder=implementer)
implementer: pass_baton(to=reviewer)
reviewer:    return_baton()
implementer: complete_baton()
```

The return stack is part of the baton. When an implementer passes a baton to a
reviewer, CAO records the implementer as the return target. When the reviewer
calls `return_baton`, control goes back to that implementer rather than the
originator. The current holder completes or blocks the baton when the tracked
obligation is resolved or cannot continue.

## Idle-Based Message Delivery

Assigned workers usually return results through `send_message`. Those inbox messages are delivered to the supervisor automatically when the supervisor terminal becomes idle.

This means supervisors should:

- Dispatch all planned worker tasks first
- Finish the turn after dispatching work
- Avoid running placeholder shell commands just to wait

Do not keep the terminal busy with `sleep`, `echo`, or similar commands while waiting. A busy terminal delays inbox delivery.

If you need multiple worker results, dispatch them all first, then end the turn. Do not poll manually in a loop.

## Callback Pattern

When you use `assign`, include the callback terminal ID in the task message. Tell the worker exactly which terminal should receive the result and instruct the worker to use `send_message`.

Example pattern:

```text
Analyze dataset A. Send results back to terminal abc123 using send_message.
```

Some CAO deployments also append an automatic callback suffix to assigned messages. Treat that appended context as helpful reinforcement, but still write task messages that are explicit and self-contained.

For baton-controlled assignments, include the baton expectation instead of a
plain callback expectation. Tell the worker to use `pass_baton`,
`return_baton`, `complete_baton`, or `block_baton` once the tools are available.
Use `send_message` only for side-channel status or communication that should
not transfer baton ownership.

## Direct Supervisor Communication

Use `send_message` when you need to contact an existing terminal directly rather than spawning a new worker.

Examples:

- Relay follow-up instructions to a worker you already created.
- Forward a worker result to another coordinator terminal.
- Send a concise status update to a collaborating supervisor.

When sending direct messages, include enough context that the receiver can act without re-reading the full original task.

## Practical Workflow

1. Read or determine your terminal ID.
2. Dispatch asynchronous workers with `assign` and include callback instructions.
3. If baton control is available and useful, create batons for async work that needs tracked ownership.
4. Use `handoff` only for steps that must finish before you can continue.
5. End the turn so asynchronous worker messages can be delivered.
6. When messages arrive or batons return, synthesize the results and continue the workflow.

## Reliability Guidelines

- Tell workers exactly what deliverable they should return.
- When workers create files, ask them to return absolute paths in their callback message.
- Do not assume results will be delivered while your terminal is still busy.
- Keep orchestration instructions separate from domain requirements so workers can parse both cleanly.
- For baton-controlled work, make the expected next action explicit and remind holders to use baton transfer tools rather than standalone messages for ownership changes.

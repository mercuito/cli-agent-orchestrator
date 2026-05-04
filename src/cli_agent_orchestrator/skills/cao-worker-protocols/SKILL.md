---
name: cao-worker-protocols
description: Worker-side callback, baton holder, and completion rules for assigned and handed-off tasks in CAO
---

# CAO Worker Protocols

Use this skill when acting as a worker agent inside CLI Agent Orchestrator.

This skill explains how workers should interpret assigned, handed-off, and baton-controlled work, when to call `send_message`, and how to report results back cleanly.

## Understand the Dispatch Mode

Workers receive tasks through one of two orchestration modes:

- `handoff`: blocking work where the orchestrator captures your final output automatically
- `assign`: non-blocking work where you must actively return results to the requesting terminal

Baton-controlled work may arrive through `assign` or through a direct message
from another worker. In that mode, the task text should identify a baton and
tell you that you are the current holder. Baton tools are planned/in-progress
in CAO and may not exist in every deployment yet:

- `create_baton(title, holder_id, message, expected_next_action?, artifact_paths?)`
- `pass_baton(baton_id, receiver_id, message, expected_next_action?, artifact_paths?)`
- `return_baton(baton_id, message, expected_next_action?, artifact_paths?)`
- `complete_baton(baton_id, message, artifact_paths?)`
- `block_baton(baton_id, reason, artifact_paths?)`
- `get_my_batons(status?)`
- `get_baton(baton_id)`

When these tools are available and the task says you hold a baton, use the baton
transfer tools for control changes.

Depending on provider and CAO behavior, a handoff may be made explicit in the task text. For example, Codex workers currently receive a `[CAO Handoff]` prefix for blocking handoffs. Other providers may rely on the task wording and orchestration context instead.

## Rules for Handoff Tasks

When the task is a blocking handoff, complete the work and present the result in your normal response. The orchestrator captures that response automatically.

Do not call `send_message` for ordinary handoff completion unless the task explicitly asks for additional side-channel communication.

## Rules for Assigned Tasks

When the task came through `assign`, the task message should include a callback terminal ID. After you finish the work:

1. Extract the callback terminal ID from the task message.
2. Format the result clearly and concisely.
3. Call `send_message(receiver_id=..., message=...)` with the completed result.

Do not stop after writing a normal response if the assignment explicitly requires a callback. The requesting terminal depends on `send_message` to receive the result.

Assigned tasks may include callback instructions directly in the main message or in an appended suffix such as `[Assigned by terminal ...]`. Treat that callback terminal ID as authoritative.

Your own `CAO_TERMINAL_ID` identifies your terminal, not the callback target. Send results to the receiver specified in the task.

## Rules for Baton-Controlled Tasks

If the task says you are holding a baton, you own the next move for that
workflow until you transfer, complete, or block the baton. A baton has exactly
one current holder while active. The current holder is responsible for choosing
the next baton action.

Use the planned baton tools this way when they are available:

- `pass_baton`: send control to another agent for their next move.
- `return_baton`: send control back to the previous holder on the return stack.
- `complete_baton`: mark the tracked obligation done and notify the originator.
- `block_baton`: mark the tracked obligation blocked when you cannot continue.
- `get_my_batons`: inspect batons currently assigned to your terminal.
- `get_baton`: inspect the baton state, holder, return stack, or recent context.

Do not transfer baton ownership with a standalone `send_message`. Baton transfer
tools are expected to update baton state and queue the message together. A
separate `send_message` can leave CAO showing the wrong current holder, which
makes the workflow harder to recover and can trigger misleading nudges.

### Pass, Return, Complete, or Block

Pass the baton when another agent owes the next move. Include a self-contained
message with the baton id, task context, artifacts to inspect, and the expected
next action.

```text
pass_baton(
  baton_id="...",
  receiver_id="<reviewer-terminal>",
  message="Review the docs/protocol update and return findings or approval.",
  expected_next_action="Review artifacts and return this baton to the implementer."
)
```

Return the baton when you received it from another holder and they need to act
again. For example, reviewers should return findings or approval to the
implementer instead of messaging the supervisor directly.

Complete the baton when the tracked workflow is done from your side and no
other worker owes a next move. Include the final result and artifact paths.

Block the baton when you cannot proceed without outside intervention. State the
blocking reason, what was already done, and what decision or input is needed.

If baton tools are not available in the current CAO deployment, follow the task
instructions for fallback reporting. Be explicit in your final callback that
baton transfer could not be performed because the tool surface was unavailable.

## Message Formatting

Return results that are easy for the supervisor to merge into a larger workflow:

- Identify what task or dataset the result belongs to
- Include the requested output or deliverable
- Keep the message specific enough to act on without re-reading the whole task

If the task asks for progress updates, use `send_message` for those updates too. Otherwise prefer one final callback with the completed deliverable.

## Filesystem and Reporting Discipline

If the task asks you to create files, write them before reporting completion. When sending results back to a supervisor, include absolute file paths so the supervisor can continue the workflow without ambiguity.

## Reliability Guidelines

- Parse the callback terminal ID before you start expensive work.
- If `send_message` is available and the task requires a callback, call it directly rather than ending with prose alone.
- If you are holding a baton and baton tools are available, use the baton transfer tool instead of `send_message` for pass, return, complete, or block.
- Keep callback messages structured so the supervisor can merge them into a larger workflow.
- For handoff tasks, return the completed output directly and let the orchestrator handle delivery.

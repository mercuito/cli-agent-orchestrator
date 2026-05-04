# Baton Control

Baton control is a planned CAO protocol for tracked asynchronous ownership. It
does not replace `assign`, `handoff`, or monitoring. It answers one narrow
question for multi-agent workflows:

> Who currently owes the next move?

The baton tool surface is planned/in-progress and may not be available in every
deployment yet:

- `create_baton(title, holder_id, message, expected_next_action?, artifact_paths?)`
- `pass_baton(baton_id, receiver_id, message, expected_next_action?, artifact_paths?)`
- `return_baton(baton_id, message, expected_next_action?, artifact_paths?)`
- `complete_baton(baton_id, message, artifact_paths?)`
- `block_baton(baton_id, reason, artifact_paths?)`
- `get_my_batons(status?)`
- `get_baton(baton_id)`

## Assign vs Handoff vs Baton

Use `assign` for async work where the worker can report back later with
`send_message`.

Use `handoff` for blocking work where the caller needs the result before it can
continue.

Use a baton for async work that needs a persistent current holder and a visible
return path. The baton holder is responsible for transferring, completing, or
blocking the baton.

## Review Loop Example

```text
supervisor:  create_baton(holder=implementer)
implementer: pass_baton(to=reviewer)
reviewer:    return_baton()
implementer: complete_baton()
```

When the implementer passes the baton to the reviewer, CAO records the
implementer on the return stack. When the reviewer returns the baton, control
goes back to the implementer, not directly to the supervisor. The implementer
then either completes the baton or passes it again for another review.

Use baton transfer tools instead of a separate `send_message` when ownership
changes. Transfer tools are expected to update baton state and queue the inbox
message together; a standalone message does not change the current holder.

## Blocking

The current holder should call `block_baton` when the workflow cannot continue
without outside input. The block message should include what was attempted, why
the work is blocked, and what decision or resource is needed.

Monitoring remains separate. Monitoring records message history for operators;
batons record current workflow ownership for agents.

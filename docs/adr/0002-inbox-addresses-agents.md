# Inbox addresses agents, not terminals

The Inbox addresses agents (`receiver_agent_id`, `sender_agent_id`); delivery
resolves to the agent's live terminal at delivery time. If no live terminal
exists, the notification stays pending until one does — there is no rehoming.
The schema migrates `inbox_notifications.receiver_id` (terminal_id) to
`receiver_agent_id`, backfilling from `terminals.agent_id`. External surfaces
follow: HTTP routes move under `/agents/{agent_id}/inbox/`, MCP `send_message`
takes `receiver_agent_id`, and the `CAO_TERMINAL_ID` env var is replaced by
`CAO_AGENT_ID` in agent prompts. Considered keeping terminal-id addressing
inside Inbox with a translation shim at the edge and rejected — the seam still
leaks the terminal concept, defeating the depth this refactor is meant to buy,
and conflicting with the stated agent → instance mental model where the
terminal is an implementation detail of an agent's liveness.

Date: 2026-05-20.

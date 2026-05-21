# Aggressive inbox schema collapse

Superseded by [ADR 0005](0005-inbox-agent-to-agent-only.md).

The inbox schema has collapsed further than this record proposed. The final
shape keeps one `inbox_notifications` table with `sender_agent_id`,
`receiver_agent_id`, and `body`; it does not keep source metadata or provider
conversation joins.

Date: 2026-05-21.

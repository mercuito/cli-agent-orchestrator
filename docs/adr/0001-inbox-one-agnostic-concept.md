# Inbox is agent-to-agent only

Superseded by [ADR 0005](0005-inbox-agent-to-agent-only.md).

The inbox no longer carries provider-routed messages, reply handlers, or
source metadata. It is now a direct agent-to-agent notification channel with
`sender_agent_id`, `receiver_agent_id`, and `body`.

Date: 2026-05-21.

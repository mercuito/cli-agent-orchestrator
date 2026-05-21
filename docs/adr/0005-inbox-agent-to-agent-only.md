# Inbox is agent-to-agent only

The inbox is a CAO-owned notification channel between agents. Inbox rows store
`sender_agent_id`, `receiver_agent_id`, `body`, delivery status, timestamps,
and failure detail. Provider reply routing, source registries, provider
conversation caches, Linear-specific inbox presentation, and the earlier
source-metadata schema from ADR 0003 are removed.

Runtime notifications may still keep their own idempotency key outside the
inbox table. That key is a runtime contract, not inbox addressing.

Date: 2026-05-21.

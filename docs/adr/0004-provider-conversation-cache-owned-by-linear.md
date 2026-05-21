# Provider-conversation cache owned by the provider integration

`provider_conversations/` package is deleted. The four cache tables it owns —
`provider_work_items`, `provider_conversation_threads`,
`provider_conversation_messages`, `processed_provider_events` — are all
Linear's local cache of remote provider state, used only by `linear/`. They
move under Linear's ownership. The Inbox refers to provider-side rows only by
opaque `source_id` strings (no cross-package FKs). When the MCP
`read_inbox_message` tool needs richer context (thread breadcrumb, work item),
it calls a Linear-internal helper after `inbox.read()` returns the metadata.
Considered keeping `provider_conversations/` as a thin generic domain package
in anticipation of future providers (GitHub, Slack) and rejected — there is
one tenant today; a future provider can extract its own cache or, if a
genuinely cross-provider abstraction emerges, the package can be reintroduced
informed by the actual second use case.

Date: 2026-05-20.

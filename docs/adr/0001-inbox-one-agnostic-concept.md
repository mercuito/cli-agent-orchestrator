# Inbox is one agnostic concept

Agent-to-agent messages and provider-routed messages (e.g., Linear) share one
[[Inbox]] concept with a single interface — `send · read · reply` — and one
persistence table. The Inbox is **source-agnostic**: it stores body and opaque
metadata, dispatches replies through a source-kind registry, and never imports
any provider-specific code. Provider integrations (e.g., `linear/`) own their
own formatting, their own reply round-trip, and register a reply handler with
the Inbox at startup. Considered splitting plain vs provider into two packages
and rejected — the persistence is shared, the readiness/delivery pipeline is
shared, and one symmetric interface makes future source kinds (baton idle nudges,
system reminders) drop into the same shape without API growth.

Date: 2026-05-20.

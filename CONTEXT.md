# Glossary

## System

Anything with an interface and an implementation. Scale-agnostic — a function,
a class, a package, or a feature-area service is each a system. Systems
compose into bigger systems; subsystems are systems too.

(The architecture skill `improve-codebase-architecture` calls this concept
"module"; in this codebase, the word is **system**.)

## Interface

Everything a caller must know to use a [[System]] correctly: types, invariants,
ordering constraints, error modes, required configuration, performance
characteristics. Not just the type signature.

## Inbox

The single concept that owns agent-to-agent messaging in CAO. One Inbox spans both
paths that share the `inbox_notifications` table:

- **Agent-to-agent path** — agent A calls `send_message`; the [[Notification]]
  delivers into agent B's live terminal via tmux once B is idle.
- **Provider-conversation path** — an external provider event (today, Linear) lands
  via that provider's integration calling `inbox.send`; the notification carries
  a preview pushed into the terminal; the agent fetches the full body via
  `read_inbox_message` and may `reply_to_inbox_message`, which round-trips through
  the registered reply handler back to the provider.

They are **one Inbox** because they share the notification model and the
push-into-terminal delivery pipeline.

The Inbox is **provider-agnostic**: it stores message body and opaque metadata, and
exposes only `send · read · reply`. Provider-specific formatting (e.g., Linear
breadcrumb, reply guidance text) lives outside the Inbox in each provider's
integration package, which calls `inbox.send(body=preformatted_text, source=...)`.

The Inbox addresses **agents**, not terminals. `inbox.send(receiver_agent_id=...,
sender_agent_id=...)`. Delivery resolves to the receiver agent's live terminal at
the moment of delivery; if the agent has no live terminal, the notification stays
pending until one becomes ready. Terminal IDs are not part of the Inbox seam.

## Source

The origin of an Inbox message. Two kinds:

- **PlainSource** — `{sender_agent_id}`. Reply is just another agent-to-agent send.
- **ProviderSource** — `{source_kind, source_id, sender_label, metadata}`. Reply
  round-trips to the external provider via that provider's integration code; Inbox
  does not know how.

## AgentReady

A framework-wide [[CaoEvent]] published by the agent runtime when an agent's live
terminal becomes ready to receive (restart, first-boot completion, return from a
workspace switch). Carries the agent_id. The Inbox subscribes during package init
and uses this signal to attempt delivery of any pending notifications for that
agent. No module other than the agent runtime publishes this event, and no module
other than the Inbox is expected to care about it today.

## Notification

The unit of Inbox communication. One row carries the body, sender agent,
receiver agent, source, status, and timestamps. Identified by `notification_id`.
There is no separate `Message` entity — body lives on the notification row.
(Historical: an earlier model split a durable `Message` from per-recipient
`Notifications`; that split was collapsed per ADR-0003 because broadcast was
never wired and the agent-id addressing removed the only other use case,
rehoming.)

## Replyability

A notification is **replyable** iff its [[Source]] kind has a registered reply
handler in the Inbox's source registry. Plain `agent` and `provider_conversation`
sources are replyable today. System-generated sources (e.g. `baton` idle nudges) are
not replyable. The `replyable` flag is derived at runtime, not stored; `inbox.read`
surfaces it on the response so agents know whether `inbox.reply` will succeed.

## Source registry

A process-local map of `source_kind → reply_handler`. Each source's owning package
registers its kind at app init (plain by `inbox/`, `provider_conversation` by
`linear/`, future kinds by their owners). `inbox.reply` dispatches through this
registry; `inbox.send` does not consult it.

Decision: 2026-05-20.

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

The CAO-owned concept for agent-to-agent notifications. An agent calls
`send_message`; the Inbox stores one [[Notification]] with `sender_agent_id`,
`receiver_agent_id`, `body`, status, timestamps, and optional failure detail.
Delivery resolves to the receiver agent's live terminal via tmux when that
agent is idle.

The Inbox addresses **agents**, not terminals or providers. If the receiver has
no live terminal, the notification stays pending until one becomes ready.
Terminal IDs are not part of the Inbox seam.

The Inbox exposes direct send and read behavior only. Agents respond by calling
`send_message` to the original sender. External provider replies, if a future
provider needs them, belong to provider-specific tools rather than Inbox reply
dispatch.

## AgentReady

A framework-wide [[CaoEvent]] published by the agent runtime when an agent's live
terminal becomes ready to receive (restart, first-boot completion, return from a
workspace switch). Carries the agent_id. The Inbox subscribes during package init
and uses this signal to attempt delivery of any pending notifications for that
agent. No module other than the agent runtime publishes this event, and no module
other than the Inbox is expected to care about it today.

## Notification

The unit of Inbox communication. One row carries the body, sender agent,
receiver agent, status, timestamps, and failure detail. Identified by
`notification_id`.
There is no separate `Message` entity — body lives on the notification row.
(Historical: an earlier model split a durable `Message` from per-recipient
`Notifications`; that split was collapsed per ADR-0003 because broadcast was
never wired and the agent-id addressing removed the only other use case,
rehoming.)

Decision: 2026-05-20.

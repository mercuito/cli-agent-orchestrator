# Aggressive inbox schema collapse

Drop `inbox_messages` and `inbox_notification_targets` tables in the same hard
cutover as ADR-0002. The `inbox_notifications` row already carries body,
source_kind, source_id, and metadata_json (denormalized today); the message and
target tables existed to support broadcast (one message → N notifications) and
rehoming (re-targeting a pending notification to a new terminal). Neither use
case survives: broadcast was never wired, and rehoming dies with the agent-id
addressing decision. Also drop `provider_conversation_inbox_notifications`
(the join table to provider conversation messages) — opaque source_id in
notification metadata replaces the FK. Considered keeping the
message/notification distinction for hypothetical future broadcast and
rejected — when broadcast becomes a real use case it will warrant its own
`inbox_batches` table designed for the actual shape, not a generic split kept
on speculation.

Date: 2026-05-20.

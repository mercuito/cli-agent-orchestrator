# Behavioral Contract Defence

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| claim-evidence-verifiability | Every assigned behavior and invariant needs concrete evidence from tests or observable code paths. |
| broad-claim-coverage | The slice depends on ordering, visibility, partitioning, idempotency, and canonicality semantics. |

## Behavior: B-1

**Claim:** Database initialization and migration create the durable event-log
tables and participant index for workspaces.
**Evidence:** `test_cao_event_migration_creates_event_log_tables` and
`test_cao_event_migration_updates_legacy_participant_occurrence_index` in
`test/events/test_cao_event_persistence.py`.

## Behavior: B-2

**Claim:** A Linear mention published through a persistent dispatcher is stored
with envelope, typed body, and the mentioned participant.
**Evidence:** `test_persistent_dispatcher_persists_and_reconstructs_linear_event`.

## Behavior: B-3

**Claim:** A runtime delivery event can be recorded with its own envelope,
typed body, delivery participant, causation id, and shared correlation id.
**Evidence:** `test_agent_history_orders_linear_mention_and_runtime_delivery_by_occurrence`.

## Behavior: B-4

**Claim:** A broadcast mention stores one canonical event and separate
participant-index rows for Aria/Cael-equivalent identities.
**Evidence:** `test_agent_participant_queries_support_broadcasts_without_duplicate_payload_rows`.

## Behavior: B-5

**Claim:** A workspace-wide runtime event with no agent participants is
persisted without participant-index matches.
**Evidence:** `RuntimeWorkspaceEvent` plus
`test_events_without_participants_persist_but_do_not_match_participant_queries`.

## Behavior: B-6

**Claim:** Retrieval by event identifier reconstructs the original concrete
typed Linear mention event.
**Evidence:** `test_persistent_dispatcher_persists_and_reconstructs_linear_event`.

## Behavior: B-7

**Claim:** Unknown event identifiers return no event.
**Evidence:** `test_event_log_queries_return_empty_results_for_unknown_facts`.

## Behavior: B-8

**Claim:** Agent-scoped history returns Linear mention and runtime delivery
participant events in occurrence order, independent of publication order.
**Evidence:** `test_agent_history_orders_linear_mention_and_runtime_delivery_by_occurrence`.

## Behavior: B-9

**Claim:** Agent-scoped history excludes events that do not declare the agent
as a participant.
**Evidence:** `test_events_without_participants_persist_but_do_not_match_participant_queries`
and `test_agent_history_uses_participant_index_not_typed_body_mentions`.

## Behavior: B-10

**Claim:** Each participant history sees the same canonical broadcast event,
not duplicated typed bodies.
**Evidence:** `test_agent_participant_queries_support_broadcasts_without_duplicate_payload_rows`.

## Behavior: B-11

**Claim:** Agent history can return an empty result for an unknown or
nonparticipant identity.
**Evidence:** `test_event_log_queries_return_empty_results_for_unknown_facts`
and `test_events_without_participants_persist_but_do_not_match_participant_queries`.

## Behavior: B-12

**Claim:** Correlation queries return related Linear and runtime events from
stored envelope facts.
**Evidence:** `test_agent_history_orders_linear_mention_and_runtime_delivery_by_occurrence`
and `test_event_log_queries_common_metadata_paths`.

## Behavior: B-13

**Claim:** Causation queries return direct children and exclude events with
other causation identifiers.
**Evidence:** `test_agent_history_orders_linear_mention_and_runtime_delivery_by_occurrence`
and `test_event_log_queries_common_metadata_paths`.

## Behavior: B-14

**Claim:** Envelope queries by event name, source, and correlation can find a
participantless workspace runtime event.
**Evidence:** `test_events_without_participants_persist_but_do_not_match_participant_queries`.

## Behavior: B-15

**Claim:** Unknown envelope facts return empty event-log query results.
**Evidence:** `test_event_log_queries_return_empty_results_for_unknown_facts`.

## Behavior: B-16

**Claim:** Republishing the same event identifier preserves one canonical event
and one canonical participant set.
**Evidence:** `test_agent_participant_queries_support_broadcasts_without_duplicate_payload_rows`
and `test_duplicate_event_id_does_not_add_participants_from_conflicting_replay`.

## Constraint: C-1

**Claim:** One event identifier resolves to at most one canonical event after
same-identifier publications.
**Evidence:** `test_duplicate_event_id_does_not_add_participants_from_conflicting_replay`.

## Constraint: C-2

**Claim:** Recorded events preserve concrete typed event type, envelope, typed
body, and participants through reconstruction.
**Evidence:** `test_persistent_dispatcher_persists_and_reconstructs_linear_event`,
`test_persisted_event_reconstructs_after_serializer_registry_restart`, and
`test_runtime_event_persists_and_reconstructs_as_exact_type`.

## Constraint: C-3

**Claim:** The participant index mirrors declared participants only.
**Evidence:** `test_agent_participant_queries_support_broadcasts_without_duplicate_payload_rows`,
`test_events_without_participants_persist_but_do_not_match_participant_queries`,
and `test_duplicate_event_id_does_not_add_participants_from_conflicting_replay`.

## Constraint: C-4

**Claim:** Event identifier, event name, source, correlation, and causation
queries are answerable from stored envelope facts.
**Evidence:** `test_event_log_queries_common_metadata_paths`,
`test_agent_history_orders_linear_mention_and_runtime_delivery_by_occurrence`,
and `test_events_without_participants_persist_but_do_not_match_participant_queries`.

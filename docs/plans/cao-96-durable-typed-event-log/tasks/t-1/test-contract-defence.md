# Test Contract Defence

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| claim-evidence-verifiability | Every feature-level and coding-level test claim needs direct evidence from test files, fixtures, or verification output. |

## Feature-Level Test Contract

### Clause: F-TC-1

**Claim:** Publication, retrieval by identifier, and exact reconstruction are
proved through the central dispatcher with registered concrete event types,
including after serializer registry replacement.
**Evidence:** `test_persistent_dispatcher_persists_and_reconstructs_linear_event`
and `test_persisted_event_reconstructs_after_serializer_registry_restart`.

### Clause: F-TC-2

**Claim:** Public event-log operations prove identity, event-name, source,
correlation, causation, ordering, empty-result, broadcast, and participantless
query behavior.
**Evidence:** `test_agent_history_orders_linear_mention_and_runtime_delivery_by_occurrence`,
`test_event_log_queries_common_metadata_paths`,
`test_agent_participant_queries_support_broadcasts_without_duplicate_payload_rows`,
`test_events_without_participants_persist_but_do_not_match_participant_queries`,
and `test_event_log_queries_return_empty_results_for_unknown_facts`.

### Clause: F-TC-3

**Claim:** Migration-readiness proof exercises existing databases gaining the
event-log tables and participant occurrence index through the migration path.
**Evidence:** `test_cao_event_migration_creates_event_log_tables` and
`test_cao_event_migration_updates_legacy_participant_occurrence_index`.

### Clause: F-TC-4

**Claim:** Retry idempotency and local non-persistent dispatcher behavior are
proved separately.
**Evidence:** `test_duplicate_event_id_does_not_add_participants_from_conflicting_replay`,
`test_agent_participant_queries_support_broadcasts_without_duplicate_payload_rows`,
and `test_local_dispatchers_remain_non_persistent_by_default`.

### Clause: F-TC-5

**Claim:** The proof set includes real Linear mention and runtime event
families, not only anonymous test event classes.
**Evidence:** Tests use `LinearAgentMentionedEvent`,
`AgentRuntimeLifecycleEvent`, `AgentRuntimeNotificationDeliveryEvent`, and
`RuntimeWorkspaceEvent` in `test/events/test_cao_event_persistence.py`.

## Coding Test Contract Criteria

### Criterion: test-validity-preserved

**Claim:** Existing event-core behavior remains intact while event-log proof is
expanded.
**Evidence:** The exact Verification Command includes `test/events/test_core.py`
and passed with 19 tests.

### Criterion: given-when-then-test-structure

**Claim:** Persistence tests expose setup, publication/query action, and
assertions clearly enough to audit behavior.
**Evidence:** Event-log tests build typed events, publish through a dispatcher,
then assert database facade query/reconstruction results in separate blocks.

### Criterion: public-boundary-proof

**Claim:** Tests use public dispatcher and event-log query operations.
**Evidence:** Tests call `CaoEventDispatcher.publish` and
`db_module.get_cao_event` / `db_module.list_cao_events_by_*`.

### Criterion: real-surface-proof-discipline

**Claim:** Persistence and migration risk is proven through real SQLite and
SQLAlchemy surfaces.
**Evidence:** `runtime_inbox_db_session` creates real in-memory SQLite tables;
migration tests use file-backed SQLite databases under `tmp_path`.

### Criterion: inspectable-authored-inputs

**Claim:** Authored event facts that affect assertions are visible from leaf
tests or explicit builder inputs.
**Evidence:** Tests that assert source, correlation, and causation values pass
`source_id`, `correlation_id`, and `causation_id` to `_linear_mentioned_event`;
participant-role assertions construct `AgentParticipant` values inline.

### Criterion: setup-invariant-ownership

**Claim:** Reusable setup owns valid Linear event fixture construction while
leaf tests assert behavior.
**Evidence:** `_linear_mentioned_event` centralizes valid Linear event setup;
leaf tests publish/query and assert outcomes.

### Criterion: reusable-test-state

**Claim:** Repeated Linear source, occurrence time, and event construction are
centralized rather than copied across scenarios.
**Evidence:** `OCCURRED_AT` and `_linear_mentioned_event` in
`test/events/test_cao_event_persistence.py`; source IDs are passed through the
builder's explicit `source_id` input when they affect assertions.

### Criterion: test-through-owner-surfaces

**Claim:** Tests depend on Linear and runtime owner surfaces for real event
families.
**Evidence:** Tests import event classes/builders from
`linear.workspace_events` and `runtime.events`; they do not recreate those
production event families locally.

### Criterion: test-artifact-containment

**Claim:** Real database artifacts are isolated.
**Evidence:** Migration tests create `tmp_path / "existing.db"` and
`tmp_path / "legacy-event-log.db"`; runtime tests use in-memory SQLite via the
pytest fixture.

### Criterion: test-file-organization

**Claim:** The persistence test file remains organized by behavior families:
publication/reconstruction, queries, idempotency, dispatcher mode, and
migration.
**Evidence:** Test order and names in `test/events/test_cao_event_persistence.py`.

### Criterion: verification-scope-discipline

**Claim:** Focused proof and broad required verification are both named.
**Evidence:** Focused proof lives in `test/events/test_cao_event_persistence.py`;
the completion report records the exact handoff Verification Command result.

## Coding Test Contract Obligations

### Clause: C-TC-1

**Claim:** A real Linear mention is published, retrieved by id, and
reconstructed exactly.
**Evidence:** `test_persistent_dispatcher_persists_and_reconstructs_linear_event`.

### Clause: C-TC-2

**Claim:** Reconstruction works after replacing the default serializer registry.
**Evidence:** `test_persisted_event_reconstructs_after_serializer_registry_restart`.

### Clause: C-TC-3

**Claim:** A runtime-owned CAO event reconstructs as its exact runtime class.
**Evidence:** `test_runtime_event_persists_and_reconstructs_as_exact_type`.

### Clause: C-TC-4

**Claim:** Identity-scoped queries return a Linear mention and runtime delivery
in occurrence order.
**Evidence:** `test_agent_history_orders_linear_mention_and_runtime_delivery_by_occurrence`.

### Clause: C-TC-5

**Claim:** Envelope queries prove event-name, source, correlation, causation,
ordering, and exclusion behavior.
**Evidence:** `test_event_log_queries_common_metadata_paths` and
`test_agent_history_orders_linear_mention_and_runtime_delivery_by_occurrence`.

### Clause: C-TC-6

**Claim:** Participantless events are retrievable by identifier and envelope
queries while excluded from identity histories.
**Evidence:** `test_events_without_participants_persist_but_do_not_match_participant_queries`.

### Clause: C-TC-7

**Claim:** Unknown identifier, agent, event-name, source, correlation, and
causation queries return empty outcomes.
**Evidence:** `test_event_log_queries_return_empty_results_for_unknown_facts`.

### Clause: C-TC-8

**Claim:** Broadcast proof shows one canonical event body and one
participant-index row per participant.
**Evidence:** `test_agent_participant_queries_support_broadcasts_without_duplicate_payload_rows`.

### Clause: C-TC-9

**Claim:** Same-identifier republication preserves one canonical event and does
not add conflicting replay participants.
**Evidence:** `test_duplicate_event_id_does_not_add_participants_from_conflicting_replay`.

### Clause: C-TC-10

**Claim:** A non-persistent dispatcher leaves durable storage untouched.
**Evidence:** `test_local_dispatchers_remain_non_persistent_by_default`.

### Clause: C-TC-11

**Claim:** Migration proof covers idempotent creation and legacy participant
occurrence index repair.
**Evidence:** `test_cao_event_migration_creates_event_log_tables` and
`test_cao_event_migration_updates_legacy_participant_occurrence_index`.

### Clause: C-TC-12

**Claim:** The exact handoff Verification Command passed.
**Evidence:** `coding-completion-report.md` records
`uv run pytest test/events/test_cao_event_persistence.py test/events/test_core.py`
passing with 19 tests.

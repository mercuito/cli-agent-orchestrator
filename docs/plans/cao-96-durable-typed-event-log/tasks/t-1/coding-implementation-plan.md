# Coding Implementation Plan - t-1

## Research Findings

Inspected the handoff, `tasks.md`, the full CAO-96 narrative, capability,
behavioral, code, and test contracts, the committed implementation decisions
artifact, and the candidate implementation from `c623eb4`. The current
implementation introduces `clients.cao_event_store`, `events.serialization`,
dispatcher persistence mode in `events.__init__`, database facade exports, and
event-log migration support. Existing tests in `test/events/test_cao_event_persistence.py`
already exercise publication, reconstruction, metadata queries, broadcasts,
idempotency, local non-persistent dispatchers, and migration creation.

Key implementation conventions:

- CAO event publication is owned by `CaoEventDispatcher`; Linear and runtime
  publishers register their event families then call the dispatcher.
- Durable event persistence is owned by `clients.cao_event_store`; the historic
  `clients.database` module remains the public database facade.
- Typed event reconstruction is centralized in `events.serialization` and uses
  event type keys to import event classes when the in-memory registry is empty.
- Tests use `runtime_inbox_db_session` for contained in-memory SQLite and
  `tmp_path` plus monkeypatched engines for file-backed migration proof.

Risks and gaps found:

- The proof set needs stronger direct coverage for identity-scoped occurrence
  ordering across a Linear event and a runtime child event.
- The proof set needs direct coverage that participantless events can still be
  found through envelope queries.
- The proof set needs direct coverage for empty event-log query outcomes.
- No upstream feature-contract, slice, or committed-decision flaw was found.

## High-Level Architecture

**Surface shape.** Keep the candidate architecture: `CaoEventDispatcher` owns
publication and explicit persistence mode; `clients.cao_event_store` owns
`CaoEventModel`, `CaoEventAgentParticipantModel`, `CaoEventRecord`,
`persist_cao_event`, and list/get query functions; `events.serialization` owns
event type registration, serialization, and reconstruction; database migration
helpers create and repair event-log tables through `init_db()` and the scoped
`_migrate_ensure_cao_event_tables()` path.

**Data flow.** Production publishers create typed CAO event dataclasses and
publish through the dispatcher. A persistent dispatcher serializes the typed
event at the central publication path, writes a canonical event row, writes
participant-index rows only on the first canonical insert, then invokes
subscribers. Query APIs read rows through the event-log API boundary and
reconstruct the concrete event via the serializer before returning
`CaoEventRecord`.

**Reuse points.** Reuse `agent_participants_for` for participant extraction,
`register_cao_event_serializers` for event-family registration, SQLAlchemy
model metadata for schema creation, `runtime_inbox_db_session` for contained
database tests, Linear event fixtures for real Linear typed events, and runtime
event builders for real runtime typed events.

## Sub-Task List

1. Draft task-level coding contracts and plan prerequisites.
   - Clauses satisfied: None directly; this sub-task creates the required
     task-level planning artifacts that later sub-tasks use for implementation
     and proof coverage.
   - Done condition: `coding-code-contract.md`, `coding-test-contract.md`, and
     this plan are persisted with selected criteria and task-specific clauses.
   - Dependency order: First.

2. Validate and revise the candidate publication, reconstruction, and
   dispatcher-mode implementation.
   - Clauses satisfied: B-1, B-2, B-3, B-6, B-7, C-1, C-2, F-CC-1, F-CC-2,
     F-CC-6, F-CC-7, F-TC-1, F-TC-4, F-TC-5, C-CC-1, C-CC-2, C-CC-3,
     C-CC-5, C-TC-1, C-TC-2, C-TC-3, C-TC-7, C-TC-9, C-TC-10.
   - Done condition: Candidate code is inspected and, if needed, revised so
     persistent publication happens only through dispatcher persistence mode,
     subscriber delivery remains after persistence, non-persistent dispatchers
     leave storage untouched, typed reconstruction uses the serializer boundary,
     unknown event identifiers return no event, and same-identifier replays
     preserve the first canonical event and participant set. Existing or revised
     tests prove these outcomes with a real Linear event and runtime event.
   - Dependency order: After plan approval.

3. Validate and strengthen event-log query proof around assigned behavioral
   slices.
   - Clauses satisfied: B-4, B-5, B-8, B-9, B-10, B-11, B-12, B-13, B-14,
     B-15, B-16, C-3, C-4, F-CC-3, F-CC-4, F-TC-2, F-TC-5, C-CC-4, C-CC-6,
     C-TC-4, C-TC-5, C-TC-6, C-TC-7, C-TC-8, C-TC-9.
   - Done condition: `test/events/test_cao_event_persistence.py` proves
     broadcast canonicality, participant-index row shape, identity-scoped
     occurrence ordering across a Linear event and runtime child event,
     participantless event exclusion from identity histories, participantless
     envelope lookup, envelope query ordering/exclusion, and empty event-log
     query outcomes. Because this is a retrofit of an already-committed
     candidate implementation, newly added proof may pass immediately; if so,
     record the red-green exception in completion.
   - Dependency order: After sub-task 2.

4. Validate and revise schema initialization and migration support.
   - Clauses satisfied: B-1, F-CC-5, F-TC-3, C-CC-7, C-TC-11.
   - Done condition: Candidate migration code is inspected and, if needed,
     revised so `init_db()` and `_migrate_ensure_cao_event_tables()` create the
     event-log tables idempotently and repair the participant occurrence index
     for legacy event-log schemas; tests prove both current-table creation and
     legacy index repair through real SQLite databases under pytest temp paths.
   - Dependency order: After sub-task 3.

5. Run verification and complete workflow artifacts.
   - Clauses satisfied: C-TC-12, full-verification-required,
     verification-scope-discipline, plus final evidence for all assigned
     behavioral, feature-code, feature-test, coding-code, and coding-test
     clauses covered by sub-tasks 2 through 4.
   - Done condition: The exact handoff Verification Command passes, completion
     report and behavioral/code/test defences are drafted, final reviewer
     approvals are recorded, and promoted committed decisions are applied if
     any are approved.
   - Dependency order: Last.

## Revision Log

- Initial plan review revision: corrected the sub-task list so planning
  artifacts no longer claim to satisfy implementation/proof clauses directly;
  added explicit candidate validation/revision sub-tasks for the full assigned
  behavioral, code, and test slices; and gave every coding-test proof
  obligation a real preservation or strengthening done condition.
- Final review revision: strengthened behavioral proof for runtime delivery
  reconstruction, participant roles, participantless index rows, and
  typed-body/nonparticipant exclusion; added `centralized-vocabulary` to the
  Coding Code Contract; removed inapplicable `respect-standing-decisions`;
  narrowed `clients.database` event-log exports; and added
  `inspectable-authored-inputs` to the Coding Test Contract.

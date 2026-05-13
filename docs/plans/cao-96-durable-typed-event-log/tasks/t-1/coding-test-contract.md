# Coding Test Contract - t-1

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| F-TC-1 | Feature Test Contract | The task owns publication, retrieval by identifier, and typed reconstruction proof. |
| F-TC-2 | Feature Test Contract | The task owns identity, event-name, source, correlation, causation, ordering, empty-result, broadcast, and participantless query proof. |
| F-TC-3 | Feature Test Contract | The task owns migration-readiness proof for existing databases. |
| F-TC-4 | Feature Test Contract | The task owns retry idempotency and local non-persistent dispatcher proof. |
| F-TC-5 | Feature Test Contract | The task owns proof using real Linear mention and runtime event families. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| test-validity-preserved | Universal criterion; existing event, Linear, runtime, and database tests must retain their target behavior. |
| given-when-then-test-structure | Persistence scenarios have clear setup, publication/query action, and observable assertions. |
| public-boundary-proof | The task changes public dispatcher, serializer registration, event-log query, and database facade surfaces. |
| real-surface-proof-discipline | Confidence depends on real SQLite persistence, SQLAlchemy models, dispatcher publication, and event reconstruction. |
| inspectable-authored-inputs | Persistence assertions depend on authored event identifiers, source IDs, correlation IDs, causation IDs, and participant roles. |
| setup-invariant-ownership | Tests depend on valid typed event fixtures and isolated database setup that are not the behavior under test. |
| reusable-test-state | Multiple scenarios need the same Linear mention event, runtime event, dispatcher, source, and occurrence setup. |
| test-through-owner-surfaces | Tests must publish through CAO dispatcher/event publishers and query through event-log APIs instead of duplicating subsystem internals. |
| test-artifact-containment | Migration tests create real temporary SQLite databases and must keep them under pytest-managed temp paths. |
| test-file-organization | The persistence test file covers publication, reconstruction, queries, idempotency, dispatcher mode, and migration behavior. |
| verification-scope-discipline | Focused event-log tests and the handoff's exact verification command both apply before completion. |

## Task-Specific Proof Obligations

- `C-TC-1`: Proof must publish a real `LinearAgentMentionedEvent` through a persistent `CaoEventDispatcher`, retrieve it by event identifier, and assert exact concrete typed reconstruction.
- `C-TC-2`: Proof must reconstruct a stored event after replacing the process-local serializer registry, demonstrating type-key import fallback rather than in-memory registration dependence.
- `C-TC-3`: Proof must include at least one runtime-owned CAO event reconstructed as its exact runtime event class.
- `C-TC-4`: Proof must show identity-scoped queries returning participant events in occurrence order across a Linear mention and a runtime event linked by correlation/causation.
- `C-TC-5`: Proof must show event-name, source, correlation, and causation queries returning occurrence-ordered results and excluding unrelated events.
- `C-TC-6`: Proof must show participantless events remain retrievable by event identifier and envelope queries while identity-scoped histories exclude them.
- `C-TC-7`: Proof must show empty results for unknown event identifiers, agent identities, and envelope facts.
- `C-TC-8`: Proof must show a broadcast event writes one canonical event body and one participant-index row per participant, and appears as the same event in each participant history.
- `C-TC-9`: Proof must show same-identifier republication preserves one canonical event and does not absorb conflicting replay participants.
- `C-TC-10`: Proof must show a non-persistent local dispatcher leaves the durable event log untouched.
- `C-TC-11`: Proof must show the migration path idempotently creates the event-log tables and updates the participant occurrence index on a legacy event-log schema.
- `C-TC-12`: The exact handoff Verification Command, `uv run pytest test/events/test_cao_event_persistence.py test/events/test_core.py`, must pass before completion.

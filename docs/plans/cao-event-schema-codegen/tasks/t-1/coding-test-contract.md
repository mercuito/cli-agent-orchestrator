# Coding Test Contract — t-1

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| F-TC-1 | feature-level Test Contract | The assigned backend persistence baseline is exactly the handoff Verification Command test set. |
| F-TC-2 | feature-level Test Contract | The task owns end-to-end proof that every Linear and runtime CAO event persists and reconstructs through the production write/read path by `kind`. |
| F-TC-5 | feature-level Test Contract | The task owns proof that legacy rows migrate to `kind` and reconstruct through production read paths. |
| F-TC-6 | feature-level Test Contract | The task must add characterization where research finds preserved backend/storage behavior not already covered by the baseline. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `test-validity-preserved` | Universal; existing assertions in the assigned baseline must keep validating the same target behavior. |
| `given-when-then-test-structure` | New persistence and migration proofs are multi-step setup/action/assertion scenarios. |
| `public-boundary-proof` | The task changes the event persistence file format and storage facade consumed through `cli_agent_orchestrator.clients.database`. |
| `real-surface-proof-discipline` | Confidence depends on real serializer, SQLAlchemy/SQLite storage, migration, and read-path surfaces. |
| `inspectable-authored-inputs` | Legacy migration proofs author pre-migration table SQL and payload examples whose content affects assertions. |
| `setup-invariant-ownership` | Event fixtures and seeded legacy rows have validity requirements that should fail near setup rather than be repeated in leaf assertions. |
| `reusable-test-state` | The all-event round-trip and legacy migration scenarios need repeated event instances and should reuse named fixture builders. |
| `test-through-owner-surfaces` | Tests that depend on persistence and timeline behavior must use dispatcher/store/service owner surfaces rather than hand-reconstructing events. |
| `test-artifact-containment` | Migration and persistence proofs create SQLite files, rows, and tables that must stay contained in `tmp_path` or the test database fixture. |
| `test-file-organization` | `test/events/test_cao_event_persistence.py` covers persistence, participant queries, and migrations, so added tests must remain grouped by behavior. |
| `verification-scope-discipline` | Focused proof must be named separately from the full handoff Verification Command. |

## Task-Specific Proof Obligations

- `C-TC-1`: Add or update focused persistence proof so every event class in `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS` is instantiated, persisted through the production write path, read through `get_cao_event`, and equality-asserted against the original typed instance.
- `C-TC-2`: Assert the new persisted table shape directly: new writes populate `kind`, the legacy `event_type_key` column is absent after migration, and the serialized payload remains object-shaped.
- `C-TC-3`: Add legacy migration proof that seeds pre-migration rows with legacy module-qualified `event_type_key`, runs `_migrate_ensure_cao_event_tables`, and verifies reconstruction through `get_cao_event`, `list_cao_events_by_agent_identity`, `list_cao_events_by_event_name`, `list_cao_events_by_source`, `list_cao_events_by_correlation_id`, `list_cao_events_by_causation_id`, and `AgentIdentityTimelineService` against the equivalent control event.
- `C-TC-4`: Add serializer proof that a fresh registry cannot reconstruct a persisted event until the concrete event class has been explicitly registered by the normal registration entry point; no dynamic import fallback may satisfy that path.
- `C-TC-5`: Preserve existing participant index, ordering, duplicate replay, non-persistent dispatcher, and API/runtime baseline assertions while adapting only discriminator-specific expectations to the new storage shape.

# Feature Test Contract - CAO-96 Durable Typed Event Log

## Applicable Feature-Level Test Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [stable-test-clause-ids](../../planning/methodology/criteria/feature-test-contract/stable-test-clause-ids.md) | Every feature-level test clause is sliced through `tasks.md`, handoffs, implementation plans, and defences by stable `F-TC-<n>` ID. |

## Standing Proof Shapes

- `F-TC-1`: Publication and reconstruction proof must exercise the
  central CAO event publication path with registered concrete event
  types. Feature-complete compliance means proof covers persistent
  publication, event retrieval by identifier, and exact concrete typed
  event reconstruction after the default serializer registry is no longer
  holding the original registration in memory.
- `F-TC-2`: Query proof must demonstrate durable event-log lookup through
  public event-log operations. Feature-complete compliance means proof
  covers identity-scoped lookup, event-name lookup, source lookup,
  correlation lookup, causation lookup, occurrence ordering, empty
  results, broadcast participants sharing one canonical event, and events
  with no agent participants.
- `F-TC-3`: Migration-readiness proof must exercise an existing database
  gaining the durable event log through the established initialization or
  migration path. Feature-complete compliance means proof covers
  idempotent creation of the event-log tables and the participant index
  needed for occurrence-ordered identity queries.
- `F-TC-4`: Retry and local-dispatcher proof must distinguish durable
  production publication from isolated local publication. Feature-complete
  compliance means proof covers same-identifier republication preserving
  one canonical event and a non-persistent dispatcher leaving the durable
  event log untouched.

## Feature-Specific Proof Obligations

- `F-TC-5`: The broad event-log proof set must include at least one real
  Linear mention event and one runtime event family so typed
  reconstruction is not proven only with anonymous test-only event
  classes.

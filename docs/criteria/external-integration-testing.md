# External Integration Testing Criteria

These criteria apply when a change integrates CAO with an external system such as Linear,
Jira, Discord, GitHub, OAuth providers, webhooks, SDKs, GraphQL APIs, or custom presence
services.

The goal is not just to prove that our code works against our own mocks. The goal is to
prove that our code matches the external contract closely enough that a passing test means
something in production.

## Implementation Criteria

External integration implementations should keep provider-specific behavior local to the
provider adapter or integration package. Generic CAO modules may depend on provider-neutral
contracts, models, and refs, but should not know external-system vocabulary unless the module
itself is explicitly provider-specific.

When adding or changing an external API query, mutation, webhook parser, SDK call, or payload
translator, the implementer must identify the external source of truth used for the contract.
Examples include a live schema introspection query, official docs, checked-in schema file,
recorded webhook payload, SDK type definition, or another primary source.

Mocked tests should mirror the verified external shape. A mock that only mirrors the local
implementation is not enough.

Provider adapters should fail clearly when asked to handle refs, events, or payloads for the
wrong provider. If a normalized event has nested refs, validate the provider identity of every
persisted ref before writing generic state.

## Required Test Coverage

For external integration slices, tests should cover more than the happy path:

1. The expected real provider payload shape.
2. Any alternate payload shape already observed in smoke tests or production.
3. Missing optional fields.
4. Missing required refs or IDs, without inventing replacements.
5. Unknown enum/type/kind values.
6. Duplicate deliveries or repeated events.
7. Wrong-provider refs at every relevant layer.
8. External API error propagation.
9. Webhook verification or authorization failure when applicable.
10. Locality: generic modules do not import provider-specific code.

If the integration uses GraphQL, tests should also assert that new query selections use fields
validated against the real schema. When practical, completion notes should mention how the
schema or payload shape was verified.

## Reviewer Criteria

Reviewers should ask:

1. Do the tests prove compatibility with the external system, or only compatibility with local
   mocks?
2. Are mocked responses shaped like the verified provider response?
3. Is provider vocabulary contained in the provider-specific package?
4. Are wrong-provider refs rejected before persistence or side effects?
5. Are duplicate deliveries idempotent and free of repeated side effects?
6. Is the integration reusable by other entrypoints, such as both webhook handlers and future
   polling monitors?
7. Are residual risks explicitly named when a provider behavior is intentionally deferred?

Reviewer findings should call out missing contract realism as a correctness issue, not as a
test-polish issue.

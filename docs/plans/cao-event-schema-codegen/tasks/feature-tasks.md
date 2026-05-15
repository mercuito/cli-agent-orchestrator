# Feature Tasks — CAO Event Schema Codegen

Feature Tasks for the CAO Event Schema Codegen refactor. This is pure
refactor work with no Feature Narrative, Feature Capability Contract, or
Feature Behavioral Contract. See `../feature-code-contract.md` and
`../feature-test-contract.md` for the slice IDs referenced below.

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-acknowledgment-completeness](../../../planning/methodology/criteria/feature-tasks/slice-acknowledgment-completeness.md) | Every task must explicitly name or explain the absence of Behavioral, Code, and Test slices. |
| [slice-coverage-uniqueness](../../../planning/methodology/criteria/feature-tasks/slice-coverage-uniqueness.md) | Each feature-level Code and Test Contract clause must have exactly one owning task. |
| [scope-handoffability](../../../planning/methodology/criteria/feature-tasks/scope-handoffability.md) | Each task scope must be specific enough to draft a self-sufficient handoff. |
| [supporting-reference-acknowledgment](../../../planning/methodology/criteria/feature-tasks/supporting-reference-acknowledgment.md) | Each task must state whether its handoff needs UI, product, domain, design, or existing-code references. |
| [explicit-dependencies](../../../planning/methodology/criteria/feature-tasks/explicit-dependencies.md) | The generated payload typing and final compatibility sweep depend on the kinded event persistence foundation. |
| [acyclic-dependencies](../../../planning/methodology/criteria/feature-tasks/acyclic-dependencies.md) | The task dependencies, including slice-implied dependencies, must remain acyclic. |

## t-1 — Kinded Event Persistence Foundation

Convert CAO event declarations and persistence internals to the stable
`kind` discriminator while preserving reconstruction equality and protocol
attribute compatibility.

- Behavioral slice: no Behavioral Contract slice for this task: pure
  refactor work.
- Code slice: `F-CC-1`, `F-CC-2`, `F-CC-3`, `F-CC-6`, `F-CC-7`, `F-CC-8`, `F-CC-9`
- Test slice: `F-TC-1`, `F-TC-2`, `F-TC-5`, `F-TC-6`
- Supporting references: required for existing backend event declaration,
  serializer, storage migration, and persistence proof patterns.

## t-2 — Generated Event Payload Types

Replace the hand-rolled frontend event type artifact with schema-generated
event payload declarations and wire known event views to the generated
payload typing without changing the public timeline API response envelope.

- Behavioral slice: no Behavioral Contract slice for this task: pure
  refactor work.
- Code slice: `F-CC-5`, `F-CC-10`, `F-CC-11`
- Test slice: `F-TC-3`, `F-TC-4`, `F-TC-7`, `F-TC-9`
- Supporting references: required for existing backend event schema
  generation patterns, frontend event-view typing, and frontend codegen
  proof patterns.
- Depends on: `t-1`

## t-3 — Compatibility And Replacement Sweep

Preserve the public timeline API response shape while completing caller
migration classification after the backend persistence and frontend
codegen replacement paths have landed.

- Behavioral slice: no Behavioral Contract slice for this task: pure
  refactor work.
- Code slice: `F-CC-4`, `F-CC-12`
- Test slice: `F-TC-8`, `F-TC-10`
- Supporting references: required for existing timeline API/frontend
  compatibility expectations, caller discovery results, and preservation
  baseline proof patterns.
- Depends on: `t-1`, `t-2`

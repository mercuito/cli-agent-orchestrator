# Test Contract — Agent Timeline Event Presentation

## Applicable Feature-Level Test Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [stable-test-clause-ids](../../planning/methodology/criteria/feature-test-contract/stable-test-clause-ids.md) | Cross-task proof obligations need stable `F-TC-<n>` identifiers for task slicing and defences. |

## Standing Proof Shapes

- `F-TC-1`: Core presentation-framework proof uses the existing backend
  identity timeline API tests and frontend identity timeline component
  tests to demonstrate that timeline and related-event responses carry a
  presentation value, untaught event kinds receive the generic fallback
  presentation, and the dashboard renders presentation values without
  concrete event-kind branching.
- `F-TC-2`: Known-presenter proof uses authored CAO event examples for
  Linear mention, runtime delivery, workspace context switch, and runtime
  lifecycle events to demonstrate their kind-specific titles, details,
  snippets, workspace context values, runtime phase values, and entity
  references.
- `F-TC-3`: Related-event and entity-reference proof uses frontend
  dashboard tests with mocked API responses to demonstrate that the
  related events panel renders the same presentation values as the main
  timeline, external entity references open their external context, and
  internal entity references focus the referenced CAO dashboard context.

## Feature-Specific Proof Obligations

No additional feature-specific proof obligations are created beyond the
standing proof shapes above. Task-level Coding Test Contracts will add
task-local proof obligations after code and test research.

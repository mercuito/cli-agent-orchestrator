# Feature Test Contract — Agent Timeline Event Presentation

## Applicable Feature-Level Test Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [stable-test-clause-ids](../../planning/methodology/criteria/feature-test-contract/stable-test-clause-ids.md) | Cross-task proof obligations need stable `F-TC-<n>` identifiers for task slicing and defences. |

## Standing Proof Shapes

- `F-TC-1`: Core typed-payload and fallback proof uses the existing
  backend identity timeline API tests and frontend identity timeline
  component tests to demonstrate that timeline and related-event
  responses carry `event_data`, untaught event kinds remain visible
  through the frontend fallback view, and no backend-authored
  presentation value is required.
- `F-TC-2`: Known frontend-view proof uses authored CAO event examples
  for Linear mention, runtime delivery, workspace context switch, and
  runtime lifecycle events to demonstrate their kind-specific issue,
  mention, delivery, terminal, workspace context, and runtime lifecycle
  details from typed event data.
- `F-TC-3`: Related-event and entity-reference proof uses frontend
  dashboard tests with mocked API responses to demonstrate that the
  related events panel renders through the same frontend event-view
  registry as the main timeline, external entity references open their
  external context, and internal entity references focus the referenced
  CAO dashboard context.

## Feature-Specific Proof Obligations

No additional feature-specific proof obligations are created beyond the
standing proof shapes above. Task-level Coding Test Contracts will add
task-local proof obligations after code and test research.

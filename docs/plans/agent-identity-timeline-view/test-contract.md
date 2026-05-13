# Feature-Level Test Contract — Agent Identity Timeline View

## Applicable Feature-Level Test Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [stable-test-clause-ids](../../planning/methodology/criteria/feature-test-contract/stable-test-clause-ids.md) | Cross-task proof obligations need stable `F-TC-<n>` identifiers for task slicing and defences. |

## Standing Proof Shapes

- `F-TC-1`: Backend proof uses the existing in-memory SQLite event-log and
  API test patterns to demonstrate identity timeline membership, canonical
  broadcast visibility, causation relatedness, correlation relatedness, and
  exclusion of zero-participant workspace events.
- `F-TC-2`: Frontend proof uses the existing Vitest and React Testing
  Library dashboard patterns with mocked API responses to demonstrate the
  roster, identity view, timeline rows, related-event interactions,
  broadcast viewpoints, and empty timeline state.
- `F-TC-3`: Live-refresh proof demonstrates that a newly recorded
  Aria-involving event appears in the watched identity timeline without
  reloading the dashboard, and that a newly recorded non-participant
  workspace event does not appear in that watched identity timeline.

## Feature-Specific Proof Obligations

No additional feature-specific proof obligations are created beyond the
standing proof shapes above. Task-level Coding Test Contracts will add
task-local proof obligations after code and test research.

# Coding Test Contract — t-3

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-TC-8` | Feature Test Contract | This task owns the final full backend/frontend preservation baseline after `t-1` and `t-2` have landed. |
| `F-TC-10` | Feature Test Contract | This task owns public compatibility characterization for uncovered preserved timeline envelope behavior. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `test-validity-preserved` | Universal; existing backend and frontend preservation tests must retain their original assertion targets. |
| `public-boundary-proof` | The assigned compatibility surface is an HTTP API response envelope and OpenAPI schema consumed by frontend clients. |
| `real-surface-proof-discipline` | Confidence depends on real API route/OpenAPI behavior and real frontend tests, not helper-only checks. |
| `test-through-owner-surfaces` | Public timeline proof must use FastAPI/TestClient and frontend API/component owners rather than duplicating response construction internals. |
| `verification-scope-discipline` | The task needs focused compatibility characterization plus the exact full preservation command from the handoff. |

## Task-Specific Proof Obligations

- `C-TC-1`: Preserve all existing assertions in the full `F-TC-8` backend/frontend baseline; any test edit must add characterization or update imports without weakening target behavior.
- `C-TC-2`: Add or identify focused public-boundary proof that the timeline event response schema exposes `event_type_key` and object-shaped `event_data` for both timeline and related-event route models.
- `C-TC-3`: Treat unknown/public `event_type_key` fixture values in frontend tests as compatibility/fallback characterization, not as generated known-event constants.
- `C-TC-4`: Run the exact Verification Command from `feature-task-handoff.md` after any implementation or test change; if it is unavailable or fails for reasons outside this task, report blocked with the concrete command evidence.

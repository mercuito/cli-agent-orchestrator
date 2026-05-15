# Coding Test Contract — t-2

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| F-TC-3 | feature-level Test Contract | The task owns proof that schema emission includes exactly one branch for every registered Linear and runtime CAO event `kind`. |
| F-TC-4 | feature-level Test Contract | The task owns proof that generated TypeScript declarations are fresh against the schema-generated OpenAPI document. |
| F-TC-7 | feature-level Test Contract | The assigned frontend preservation baseline is exactly the handoff Verification Command test set. |
| F-TC-9 | feature-level Test Contract | The task must add characterization where research finds preserved frontend/codegen behavior not already covered by the F-TC-7 baseline. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `test-validity-preserved` | Universal; existing assertions in the assigned frontend baseline must keep validating the same target behavior. |
| `given-when-then-test-structure` | Codegen freshness and known-view rendering proof are multi-step setup/action/assertion scenarios. |
| `public-boundary-proof` | The task changes the generated TypeScript module export surface and frontend codegen command wiring, so proof must exercise the command and import boundary consumed by frontend callers. |
| `real-surface-proof-discipline` | Confidence depends on the real backend event declarations, schema generation path, `openapi-typescript` CLI, generated TypeScript module, and Vitest-rendered frontend views. |
| `inspectable-authored-inputs` | Frontend fixture payloads and expected generated event key/kind facts affect assertions and must remain visible from tests or narrowly named helpers. |
| `setup-invariant-ownership` | Codegen checks must fail at the generator/check boundary when backend registration/schema invariants are invalid, rather than hiding those checks in leaf UI assertions. |
| `test-through-owner-surfaces` | Tests and check commands that depend on event schemas must go through the codegen owner surface and exported backend event tuples, not duplicate discovery logic in frontend tests. |
| `test-artifact-containment` | Codegen freshness proof creates transient schema and candidate TypeScript artifacts that must stay in isolated temporary paths and clean up after the check. |
| `verification-scope-discipline` | The focused codegen freshness/type proof and the exact handoff Verification Command must both be run before completion. |

## Task-Specific Proof Obligations

- `C-TC-1`: Add or update focused codegen proof so the check command builds the backend-derived schema document, verifies exactly one `CaoEventPayload` discriminator mapping for every member of `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`, re-runs `openapi-typescript`, and compares the result against the committed generated TypeScript file without rewriting it in check mode.
- `C-TC-2`: Preserve the F-TC-7 frontend baseline tests while migrating imports from the retired generated event key artifact to the new generated payload artifact; existing assertions for fallback events, known event rendering, terminal focus, URL construction, and typed API `event_data` return values must not be weakened.
- `C-TC-3`: Add characterization for the newly generated compatibility surface if the F-TC-7 baseline does not already assert it: known public event key constants must still resolve timeline event registry dispatch for handled Linear mention and runtime event views, while unknown public event keys continue through fallback rendering.
- `C-TC-4`: Type-level proof must run as part of the frontend verification boundary so known event views are checked against generated payload declarations, not only against runtime `Record<string, unknown>` access.
- `C-TC-5`: Transient schema/candidate artifacts used by freshness checks must be created under an isolated temporary location and removed before the command exits.

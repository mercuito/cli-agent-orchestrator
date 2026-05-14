# Coding Test Contract — t-2

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-TC-2` | Feature Test Contract | This task owns known frontend-view proof for Linear mention, runtime delivery, workspace context switch, and runtime lifecycle details from typed event data. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `test-validity-preserved` | Universal criterion; existing timeline fallback, related-event, API wrapper, backend route, Linear, and runtime tests must keep validating their original behavior. |
| `given-when-then-test-structure` | Frontend component proof exercises authored event setup, rendered timeline action, and visible row assertions. |
| `public-boundary-proof` | The task changes the dashboard component surface and build/test generated constant boundary consumed by production code. |
| `real-surface-proof-discipline` | Confidence depends on rendered React timeline rows and actual TypeScript/build imports rather than isolated helper calls alone. |
| `inspectable-authored-inputs` | The Linear/runtime authored payload facts that drive visible assertions must remain visible in the leaf tests. |
| `setup-invariant-ownership` | Existing frontend identity/event builders own valid timeline row setup while leaf tests assert presentation behavior. |
| `reusable-test-state` | Known-view tests should extend the existing shared identity/timeline helpers rather than rebuilding duplicate worlds. |
| `test-through-owner-surfaces` | Generated-key proof should use the generator output and registry owner surface instead of duplicating event type strings in tests. |
| `test-artifact-containment` | Backend proof creates persisted CAO event and runtime database rows inside isolated SQLite/tmp-path test harnesses. |
| `test-file-organization` | `agent-identity-timeline-panel.test.tsx` covers multiple identity timeline behavior families and must keep known-view proof grouped and navigable. |
| `verification-scope-discipline` | Focused frontend/backend checks are useful during development, and the exact handoff Verification Command is required before completion. |

## Task-Specific Proof Obligations

- `C-TC-1`: Frontend component tests must prove the Linear mention row renders issue title or identifier context, mentioner context when present, mention text snippet, and issue context from authored `event_data`.
- `C-TC-2`: Frontend component tests must prove the runtime delivery row renders source kind when present, delivered message when present, and receiving terminal identifier from authored `event_data`.
- `C-TC-3`: Frontend component tests must prove the workspace context switch row renders both from-context and to-context from authored `event_data`.
- `C-TC-4`: Frontend component tests must prove the runtime lifecycle row renders lifecycle action/phase, runtime status or health context, terminal identifier when present, and workspace context from authored `event_data`.
- `C-TC-5`: Frontend proof must demonstrate known views are reached through generated event type constants and module self-registration, while an unregistered event type still renders through the existing fallback.
- `C-TC-6`: Focused proof must cover missing optional payload facts for at least one taught view and show readable fallback content rather than a render failure.
- `C-TC-7`: Runtime/backend tests must prove the runtime delivery event payload carries the source kind and delivered message data required for the frontend delivery row, without asserting backend-authored presentation values.
- `C-TC-8`: Completion requires the exact handoff Verification Command:

```bash
uv run pytest test/api/test_agent_identity_routes.py test/linear/test_webhook_ingestion.py test/runtime/test_agent_runtime.py && cd web && npm test -- --run src/test/api.test.ts src/test/agent-identity-timeline-panel.test.tsx && npm run build
```

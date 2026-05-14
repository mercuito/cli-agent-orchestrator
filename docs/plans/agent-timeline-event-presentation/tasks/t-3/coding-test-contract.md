# Coding Test Contract — t-3

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-TC-3` | Feature Test Contract | This task owns proof that related events use the same frontend registry views and that external/internal entity references navigate to their targets. |

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `test-validity-preserved` | Universal criterion; existing identity timeline, related-event caching, dashboard deep-link, and API wrapper tests must keep validating their original behavior. |
| `given-when-then-test-structure` | Entity-reference proof uses authored event setup, user follow actions, and observable external-open/internal-focus assertions. |
| `public-boundary-proof` | The task changes dashboard user interaction boundaries: clicking a Linear issue reference and clicking a terminal reference. |
| `real-surface-proof-discipline` | Confidence depends on rendered React components and the Agents panel boundary, not isolated helper calls. |
| `inspectable-authored-inputs` | Authored `event_data` payload facts such as `issue_url`, `issue_identifier`, and `terminal_id` directly determine the navigation assertions. |
| `setup-invariant-ownership` | Existing identity/event builders and AgentPanel store mocks own valid setup while leaf tests assert navigation behavior. |
| `reusable-test-state` | New tests should extend existing authored CAO timeline event fixtures instead of duplicating full identity/timeline worlds. |
| `test-through-owner-surfaces` | Internal terminal focus proof must exercise the `AgentPanel` owner surface rather than invoking private focus helpers. |
| `test-file-organization` | `agent-identity-timeline-panel.test.tsx` and `agent-panel-deeplink.test.tsx` already cover multiple behavior families and must keep new tests grouped by related-event/navigation behavior. |
| `verification-scope-discipline` | Focused frontend tests prove local behavior, and the exact handoff Verification Command is required before completion. |

## Task-Specific Proof Obligations

- `C-TC-1`: Frontend component tests must prove a related runtime delivery renders through the taught runtime delivery view, including source/message/terminal presentation, while an untaught related event still renders through fallback.
- `C-TC-2`: Frontend component tests must prove the Linear mention external entity reference opens the authored `issue_url` with `_blank` and `noopener,noreferrer`.
- `C-TC-3`: Frontend component tests must prove a Linear mention without `issue_url` remains readable and does not render an external-open affordance.
- `C-TC-4`: Frontend component tests must prove the runtime delivery internal terminal reference invokes the supplied terminal-focus callback with the authored `terminal_id`.
- `C-TC-5`: Agents panel boundary tests must prove following the runtime delivery terminal reference opens/focuses the referenced terminal through the existing terminal lookup/session selection/`TerminalView` flow.
- `C-TC-6`: Completion requires the exact handoff Verification Command:

```bash
cd web && npm test -- --run src/test/api.test.ts src/test/agent-identity-timeline-panel.test.tsx src/test/agent-panel-deeplink.test.tsx && npm run build
```

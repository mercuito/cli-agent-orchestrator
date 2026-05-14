# Test Contract Defence — t-3

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Every proof-quality claim is tied to concrete tests or the exact verification run. |

## Feature-Level Test Contract

### Clause: `F-TC-3`

**Claim:** Frontend dashboard tests prove related registry rendering, external entity references, and internal terminal focus.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:462` proves related taught runtime delivery and fallback rendering. `web/src/test/agent-identity-timeline-panel.test.tsx:488` proves external Linear issue opening. `web/src/test/agent-panel-deeplink.test.tsx:231` proves internal terminal focus through `AgentPanel`. Exact Verification Command passed.

## Coding Test Contract

### Criteria

**Claim:** The selected coding-level test criteria are satisfied, including preserved existing tests, inspectable authored payloads, owner-surface proof, and exact verification.

**Evidence:** Existing API, identity timeline, and deep-link tests still pass in the exact Verification Command. New tests keep authored `event_data` inline in `web/src/test/agent-identity-timeline-panel.test.tsx` and `web/src/test/agent-panel-deeplink.test.tsx`. Internal focus is proven through rendered `AgentPanel`, not a private helper.

### Clause: `C-TC-1`

**Claim:** Related runtime delivery uses the taught delivery view, and untaught related events use fallback.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:462` asserts related delivery title/source/message and related `Experimental Audit Event` fallback content.

### Clause: `C-TC-2`

**Claim:** Linear mention external reference opens the authored URL with the required outside-context arguments.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:488` spies on `window.open`, clicks `Open Linear issue OPS-417`, and asserts the exact URL, `_blank`, and `noopener,noreferrer`.

### Clause: `C-TC-3`

**Claim:** Linear mentions without `issue_url` remain readable and do not render a broken external-open affordance.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:506` uses authored payload without `issue_url`, asserts issue/title text remains visible, and asserts the open button is absent.

### Clause: `C-TC-4`

**Claim:** Runtime delivery internal terminal reference invokes the supplied focus callback with the authored terminal id.

**Evidence:** `web/src/test/agent-identity-timeline-panel.test.tsx:520` renders a runtime delivery with `terminal_id: 'term-aria-main'`, clicks the terminal reference, and asserts callback invocation with `term-aria-main`.

### Clause: `C-TC-5`

**Claim:** Agents panel boundary proof opens/focuses the referenced terminal through existing terminal lookup/session selection/`TerminalView` behavior.

**Evidence:** `web/src/test/agent-panel-deeplink.test.tsx:231` renders `AgentPanel`, clicks the runtime delivery terminal reference, asserts `getTerminal('term-aria-main')`, asserts `selectSession('cao-linear-discovery-partner')`, and asserts `TerminalView` receives `terminalId: 'term-aria-main'`.

### Clause: `C-TC-6`

**Claim:** The exact handoff Verification Command succeeded.

**Evidence:** Exact command run after implementation:

```bash
cd web && npm test -- --run src/test/api.test.ts src/test/agent-identity-timeline-panel.test.tsx src/test/agent-panel-deeplink.test.tsx && npm run build
```

Vitest reported 3 files and 48 tests passing; `tsc && vite build` completed successfully.

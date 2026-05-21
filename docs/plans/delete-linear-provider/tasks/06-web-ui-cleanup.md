# Task 06 — Strip Linear from the Web UI and Rebuild the Bundle

## Goal

Remove all Linear-specific code paths from the web dashboard sources and
rebuild the backend-served bundle. After this task, the dashboard has no
Linear configuration forms, no Linear timeline event views, no Linear API
calls.

## Preconditions

- Task 03 complete (Python suite passes). UI cleanup can run in parallel
  with Tasks 04/05 because the dashboard does not depend on the inbox
  collapse shape changes — it only consumes `/agents` and similar
  endpoints whose Linear fields were removed in Task 01.

## Scope

Source files to delete:

- `web/src/components/timelineEventViews/linearCaoEventViews.tsx`

Source files to edit (strip Linear-only sections, keep the rest):

- `web/src/api.ts` — drop the response/request types that mirrored the
  `LinearConfigResponse` / `LinearWriteRequest` shapes; drop any function
  that hit a Linear-specific endpoint (Linear OAuth, Linear webhook).
- `web/src/generated/caoEventPayloadTypes.ts` — regenerate from the
  backend after Task 01's API surface changes. Do not hand-edit; use the
  project's existing codegen step.
- `web/src/components/agents-tab/AgentConfigTab.tsx` — drop the Linear
  section of the agent config form. The form should no longer surface
  Linear tokens, OAuth fields, or tool_access policy editing.
- `web/src/components/agents-tab/agentTomlSerialization.ts` — drop the
  Linear branch of the TOML serializer; the agent TOML no longer has a
  `[linear]` block.

Test files to update:

- `web/src/test/agent-timeline-tab.test.tsx`
- `web/src/test/agent-panel-deeplink.test.tsx`
- `web/src/test/agent-detail-panel.test.tsx`
- `web/src/test/workspace-teams-panel.test.tsx`
- `web/src/test/app-deeplink.test.tsx`
- `web/src/test/agent-config-tab.test.tsx`
- `web/src/test/api.test.ts`

For each, remove the Linear-specific test scenarios. Apply
`test-validity-preserved`: do not weaken assertions or skip whole tests
to make them green. Tests of Linear-only flows should be deleted; tests
of generic flows that happened to use Linear fixtures should be rewritten
to use non-Linear fixtures.

Rebuild step:

```bash
cd web
npm install   # if not already
npm run build
```

The build writes into `src/cli_agent_orchestrator/web_ui/assets/`. Verify:

- The new `index-*.js` is committed.
- The old `index-fZHYKtgT.js` (if still present) is removed.
- `grep -i linear src/cli_agent_orchestrator/web_ui/assets/index-*.js`
  returns no matches (or only unrelated word fragments).

## Out of Scope

- Backend changes. The backend's Linear endpoints are already gone after
  Task 01.
- New UI features. This is pure cleanup.

## Acceptance Criteria

1. `grep -ln "linear\|Linear" web/src/` returns no matches outside
   intentional, unrelated contexts.
2. `npm test` (or `npm run test:run`, whichever is the project default)
   exits 0.
3. `npm run build` exits 0 and produces a fresh bundle.
4. `git diff --stat` shows the asset file replaced.
5. **Real-browser verification.** Per
   `docs/criteria/tests/ui-changes-require-real-browser-verification.md`,
   verification must include a real browser pass against the backend-served
   dashboard, not just unit tests:
   - Start the CAO backend (`uv run cao serve` or equivalent).
   - Open the backend-served dashboard URL in a real browser (the URL
     class real users use — Tailscale / remote, not just localhost if the
     project ships remote).
   - Open the Agents tab. Confirm: no Linear section in the agent config
     form; no Linear-specific timeline event views; agent list renders
     normally.
   - Open the Workspace Teams tab. Confirm it loads and renders without
     500s or console errors.
   - Capture the URL exercised, the steps taken, and the observed result
     in the completion notes for this task.

## Criteria to Consult

- `ui-changes-require-real-browser-verification` — Read the full markdown.
  This is the load-bearing criterion for UI work.
- `do-not-assume-backwards-compatibility` — No commented-out Linear React
  components left behind.
- `test-validity-preserved` — Always.
- `readable-and-explicit` — Component names and props should not retain
  Linear-shaped naming after the cleanup.

## Notes for the Implementing Agent

- The codegen step for `caoEventPayloadTypes.ts` likely runs against the
  backend's emitted JSON schema or pydantic models. Check
  `docs/plans/cao-event-schema-codegen/` for how this codegen is run; do
  not hand-edit the generated file.
- If `AgentConfigTab.tsx` has been split into subcomponents, search for
  any `LinearConfigSection` / `LinearToolAccessSection` / similar
  components and delete them entirely.
- The asset filename in `web_ui/assets/` is hash-based; the old hash
  (e.g. `index-fZHYKtgT.js`) will be replaced by a new hash on rebuild.
  Make sure git tracks the replacement (`git add web_ui/assets/`).

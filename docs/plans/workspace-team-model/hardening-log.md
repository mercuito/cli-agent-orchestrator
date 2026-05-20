# Workspace Team Model Hardening Log

Status: implementation-ready

This log tracks fresh no-context explorer audits for
`docs/plans/workspace-team-model/plan.md`. The plan is implementation-ready only
after three consecutive fresh audits return no valid findings.

## Current State

- Consecutive zero-valid-finding audits: 3
- Last reset reason: Harvey found a valid active baton state classification
  omission.
- Clean audits since last reset: Goodall, Popper, Beauvoir.
- Post-hardening amendments: dashboard Teams tab and read-only team-derived
  workspace setup controls, explicit criteria-compliance guardrails, and Safari
  end-to-end UI acceptance criteria were added after the three clean audits.
- Latest criteria audit: Hegel found a valid conflict between code-owned team
  definitions and dashboard-managed teams; the plan now requires a localized
  persisted team-definition owner surface.
- Follow-up criteria audit: Aristotle reported no valid findings after the
  persisted team-definition correction.

## Valid Findings Integrated

### Russell

1. Direct inbox REST/CLI writes could bypass MCP-only message policy.
   - Disposition: valid.
   - Plan coverage: message policy applies at inbox delivery owner boundaries,
     including REST and CLI inbox writes.

2. Provider conversation bridge could route by explicit receiver terminal.
   - Disposition: valid.
   - Plan coverage: provider-conversation receiver routing must be retired,
     constrained as admin-only, or use team-authorized event selection.

3. Runtime/provider event payloads and timeline views lacked team context.
   - Disposition: valid.
   - Plan coverage: relevant runtime/provider events and timeline views must
     include team and derived setup context, or document context-only payloads.

4. MCP descriptions and bundled skills taught terminal-id collaboration.
   - Disposition: valid.
   - Plan coverage: agent-facing protocol text must describe same-team message
     policy and avoid presenting terminal id possession as authority.

5. Provider-mediated MCP freshness/fingerprints could remain setup/agent-only.
   - Disposition: valid.
   - Plan coverage: MCP surface descriptors and runtime fingerprints must
     include team-bound provider policy material.

6. Existing terminals and pending inbox notifications needed classification
   under team changes.
   - Disposition: valid.
   - Plan coverage: active terminal, pending inbox, and runtime context switch
     behavior must be explicitly defined and tested.

7. Baton HTTP/CLI recovery endpoints needed explicit exemption or guard.
   - Disposition: valid.
   - Plan coverage: baton recovery is classified as guarded collaboration or
     operator/admin recovery, with tests and wording.

### Ptolemy

1. Linear monitor/reconciliation is a separate provider-event ingress path.
   - Disposition: valid.
   - Plan coverage: Linear monitor presence iteration, synthetic events,
     pending delivery retry, and watermark advancement must use team-authorized
     provider views.

2. Provider-conversation inbox read/reply by notification id needed current
   authorization.
   - Disposition: valid.
   - Plan coverage: `read_inbox_message` and `reply_to_inbox_message` require
     current caller/receiver ownership and current team/provider-view
     authorization.

### Faraday

1. Workspace context identity/scoping was unspecified under team/setup model.
   - Disposition: valid.
   - Plan coverage: workspace context identity is setup/resolver scoped, not
     team scoped; different setup/resolver namespaces cannot silently collide.

2. Global Linear identity uniqueness conflicted with ambiguity semantics.
   - Disposition: valid.
   - Plan coverage: Linear identity uniqueness must be explicitly classified;
     generic ambiguity coverage must not depend on Linear allowing duplicates.

### Noether

1. CLI agent management surfaces were omitted.
   - Disposition: valid.
   - Plan coverage: `cao agent create/show/list/edit/start` must reflect team
     membership, derived setup metadata, diagnostics, and standalone no-team
     behavior.

2. Legacy workspace tool provider registry/event protocols could preserve global
   routing.
   - Disposition: valid.
   - Plan coverage: legacy provider registry protocols and event dispatchers
     must be retired, telemetry-only, or routed through team-authorized provider
     views before addressing agents.

3. Repo-root `skills/cao-provider` taught terminal-id collaboration.
   - Disposition: valid.
   - Plan coverage: repo-root skills and references are included in protocol
     text updates and static verification.

### Sartre

1. Linear OAuth/webhook source surfaces could stamp global recipient metadata.
   - Disposition: valid.
   - Plan coverage: OAuth state validation, token lookup, webhook secret
     verification, and webhook metadata stamping are source-authentication only
     and cannot bypass team-authorized recipient selection.

2. Scheduled/manual flow execution is a separate runtime start path.
   - Disposition: valid.
   - Plan coverage: flow execution is classified as operator runtime start,
     default-context behavior and diagnostics are required, and stale active
     terminal reuse after team changes must be tested.

### McClintock

1. Diagnostics provider runs are a separate runtime start path.
   - Disposition: valid.
   - Plan coverage: diagnostics runs are classified as operator runtime starts
     with default-context behavior, team diagnostics, and active-terminal
     behavior covered by tests.

2. Provider conversation persistence/idempotency needed team-safe semantics.
   - Disposition: valid.
   - Plan coverage: processed-event markers, conversation records, and runtime
     notifications must only be written as successful after team authorization
     succeeds and must carry enough team/setup metadata to avoid stale
     recipient state.

3. Monitoring sessions needed diagnostic-only classification.
   - Disposition: valid.
   - Plan coverage: monitoring is terminal/operator diagnostics over
   historical inbox records, does not authorize collaboration, and must cover
   team changes, context switches, peer filters, and rejected cross-team
   messages.

### Harvey

1. Active baton records can preserve stale terminal participants across team
   changes.
   - Disposition: valid.
   - Plan coverage: durable baton fields such as `originator_id`,
     `current_holder_id`, and `return_stack` must have explicit behavior after
     team changes or removal, with tests for pass, return, complete, block,
     reassign, watchdog nudge, and watchdog orphan paths.

## Post-Hardening Amendments

1. Dashboard team management and agent setup foot-gun prevention.
   - Source: operator design request after the three clean audits.
   - Plan coverage: Task 6 now requires a first-class Teams tab for creating
     and managing teams, showing team setup/diagnostics/members, changing setup
     through the team owner surface, and rendering team-derived setup as
     read-only/disabled in agent configuration so no agent-level setup override
     can be saved for a teamed agent.

2. Criteria-compliance guardrails.
   - Source: planning-discipline review against `docs/criteria/`.
   - Plan coverage: the Definition of Done now explicitly requires
     authoritative shared definitions, boundary-only global-state reads,
     parallel-safe execution, no test-only production seams, tests through owner
     surfaces, and contained Given/When/Then tests. The Criteria Catalog now
     names all currently likely implementation and test criteria for this work.

3. Safari end-to-end UI acceptance.
   - Source: operator criteria review after dashboard requirements were added.
   - Plan coverage: the verification matrix, required verification commands,
     and Definition of Done now require Safari verification against the
     backend-served dashboard for Teams tab creation/editing, team setup
     selection, member rendering, read-only teamed-agent setup controls,
     save/reload persistence, and observed results in the completion report.

4. Persisted team-definition owner surface.
   - Source: fresh no-context criteria audit by Hegel.
   - Disposition: valid.
   - Plan coverage: workspace setup definitions remain code-owned, but
     dashboard-managed team definitions must persist through one localized
     `WorkspaceTeamService`/store owner surface. Bootstrap teams seed the same
     owner surface, and dashboard/API/UI code must not keep team definitions in
     process-global mutable registries, API-local state, or frontend-only
     state.

5. Follow-up criteria audit.
   - Source: fresh no-context criteria audit by Aristotle after the
     team-definition owner correction.
   - Disposition: no valid findings.

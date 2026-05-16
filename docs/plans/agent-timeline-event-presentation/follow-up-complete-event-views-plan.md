# Follow-Up Plan — Complete CAO Timeline Event Views

## Summary

Complete the frontend CAO timeline event presentation set by adding
purpose-built views for the currently generated CAO event types that still
fall back to the generic renderer.

This is a frontend presentation follow-up to the existing Agent Timeline
Event Presentation plan. It must not change backend API response shapes,
CAO event schemas, event persistence, generated payload type generation, or
the fallback behavior for unknown event types.

## Current State

Generated frontend event payload types currently include 11 CAO event type
constants. Custom timeline views exist for 4 of them:

- `LinearAgentMentionedEvent`
- `AgentRuntimeNotificationDeliveryEvent`
- `AgentRuntimeWorkspaceContextSwitchEvent`
- `AgentRuntimeLifecycleEvent`

The following 7 event types still render through the fallback view and need
typed frontend views:

- `AgentRuntimeNotificationAcceptedEvent`
- `RuntimeWorkspaceEvent`
- `LinearIssueDelegatedToAgentEvent`
- `LinearAgentSessionPromptedEvent`
- `LinearAgentSessionLifecycleActivityEvent`
- `LinearAgentSessionStopRequestedEvent`
- `LinearIssueCreatedEvent`

## Implementation Plan

- Add the missing views in the existing timeline-view system, with the code
  located near the existing known CAO event views.
- Register each new view with the generated event type constant from
  `caoEventPayloadTypes.ts`; do not hand-type fully qualified event type key
  strings.
- Reuse existing presentation primitives such as the view shell, detail pills,
  entity-reference buttons, and snippets. Add only small local helper
  functions where repeated Linear issue/session extraction would otherwise
  duplicate logic.
- Preserve the generic fallback for unknown or unregistered event types.
- Do not add production props, routes, fixture endpoints, public exports, or
  backend seams solely to make tests easier.

Expected useful content by event kind:

- Runtime notification accepted: notification id, receiver, sender, source
  kind/source id, workspace context.
- Runtime workspace: workspace context, action, runtime status, and error when
  present.
- Linear issue delegated: issue identifier/title/state, target agent, actor,
  message or prompt context, and Linear issue link when present.
- Linear agent session prompted: issue, session/thread identifiers, prompt or
  message body, actor, and thread/issue link when present.
- Linear session lifecycle activity: session, issue, action, message kind,
  notify/suppression state.
- Linear stop requested: session, issue, requester, stop action/reason/message.
- Linear issue created: created issue identifier/title/state/url, terminal,
  agent identity, and tool name.

## Test Plan

- Expand the frontend identity timeline tests through the owning
  `AgentIdentityTimelinePanel` surface. API responses may be mocked as the
  external data seam, but the timeline registry and event view components must
  be the real implementation.
- Add reusable authored event fixtures for all 11 generated event type
  constants, keeping Given/When/Then structure and assertions in the Then
  portion of each test.
- Add a coverage assertion that every value in `CAO_EVENT_TYPE_KEYS` has a
  registered taught view, while separate fallback tests continue to prove
  unregistered event kinds remain visible.
- Prove each new view renders distinctive useful facts from event data and
  degrades cleanly when optional URLs, messages, errors, terminal ids, or
  nested issue fields are absent.
- Prove related-event panels render the same taught views as the main timeline.
- Run:

  ```bash
  npm test -- agent-identity-timeline-panel.test.tsx
  npm test
  ```

## Browser Acceptance

- Open the dashboard in a browser after implementation.
- Use an isolated temporary runtime/data environment for browser verification
  so synthetic events do not pollute the user's normal CAO database.
- Seed synthetic CAO events through public event constructors and the existing
  dispatcher/event persistence path rather than direct SQL or a test-only
  frontend seam.
- Verify the Agents timeline renders all 11 event kinds with custom titles,
  useful fact chips/snippets, and working Linear/terminal actions where the
  event data provides those targets.
- Use non-conflicting ports or existing running dev-server ports so the
  verification remains safe alongside other local runs.

## Criteria Catalog

Criteria catalog command run before drafting this plan:

```bash
uv run python scripts/catalog_criteria.py
```

Likely implementation criteria that shape this plan:

- `do-not-assume-backwards-compatibility`
- `minimal-cohesive-changes`
- `no-test-only-production-seams`
- `no-unnecessary-duplication`
- `parallel-safe-execution`
- `prefer-public-surfaces`
- `properly-designed-shared-code`
- `readable-and-explicit`
- `simple-systems`
- `system-code-locality`

Likely test criteria that shape this plan:

- `all-system-interactions-are-verified-by-tests`
- `assertions-occur-in-the-then-clause`
- `given-when-then-test-structure`
- `reusable-given-state`
- `seams-must-be-tested`
- `target-behavior-must-not-be-mocked`
- `test-artifact-containment`
- `test-file-organization`
- `test-through-owner-surfaces`
- `test-validity-preserved`

The planner must not certify this as the final applicable criteria set.
The implementer must consult the catalog and load any criteria whose `when`
clauses match the completed production and test diff.

## Acceptance Criteria

- Every currently generated CAO event type key has a purpose-built frontend
  timeline view.
- Unknown event types still render through the fallback view.
- Main timeline and related-event timeline surfaces both use the taught views.
- Focused and full frontend test verification pass.
- Browser verification confirms the custom views are readable and useful with
  representative seeded event data.
- After implementation, evaluate the pending changes against the criteria
  catalog. No criteria applicable to the completed diff may be violated.

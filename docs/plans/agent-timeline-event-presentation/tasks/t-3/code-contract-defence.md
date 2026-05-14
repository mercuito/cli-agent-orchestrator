# Code Contract Defence — t-3

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Every code-shape claim is tied to concrete code paths or verification output. |

## Feature-Level Code Contract

### Clause: `F-CC-5`

**Claim:** Entity references are frontend-owned structured affordances with explicit external/internal navigation discrimination.

**Evidence:** Linear issue references are rendered in `web/src/components/timelineEventViews/knownCaoEventViews.tsx:171` from `event.event_data.issue_url` and call `onOpenExternalReference`. Runtime terminal references are rendered in `web/src/components/timelineEventViews/knownCaoEventViews.tsx:204` from `event.event_data.terminal_id` and call `onFocusTerminal`. Backend timeline code was not changed, and no backend presenter or UI presentation value was introduced.

## Coding Code Contract

### Criteria

**Claim:** The selected coding-level criteria are satisfied: exact verification ran, behavior started with failing focused tests, changes stayed scoped, existing registry semantics were preserved, exported surfaces are production-facing, and standing decisions remain respected.

**Evidence:** Red run failed on missing entity-reference buttons before implementation; exact Verification Command later passed. `web/src/components/timelineEventViews.tsx:6` exports only production navigation callback types used by `AgentIdentityTimelinePanel`. `web/src/components/AgentIdentityTimelinePanel.tsx:121` and `web/src/components/AgentIdentityTimelinePanel.tsx:159` preserve registry dispatch for related and main rows. No backend files changed.

### Clause: `C-CC-1`

**Claim:** Event-view props carry production navigation callbacks shared by main and related rows.

**Evidence:** `web/src/components/timelineEventViews.tsx:9` includes `onOpenExternalReference` and `onFocusTerminal`. Main rows pass them at `web/src/components/AgentIdentityTimelinePanel.tsx:164`; related rows pass them at `web/src/components/AgentIdentityTimelinePanel.tsx:125`.

### Clause: `C-CC-2`

**Claim:** Entity-reference UI is authored by frontend typed views from `event.event_data`, with no backend presentation values.

**Evidence:** `web/src/components/timelineEventViews/knownCaoEventViews.tsx:154` reads `issue_url`; `web/src/components/timelineEventViews/knownCaoEventViews.tsx:192` reads `terminal_id`. `git diff --name-only` for production scope shows only frontend files changed.

### Clause: `C-CC-3`

**Claim:** Linear mention external references render only for string `issue_url` values and open outside the dashboard.

**Evidence:** `stringFact` gates non-empty strings at `web/src/components/timelineEventViews/knownCaoEventViews.tsx:49`; `issueUrl` is read at line 154 and button rendering is conditional at line 171. `web/src/components/AgentIdentityTimelinePanel.tsx:238` opens with `_blank` and `noopener,noreferrer`.

### Clause: `C-CC-4`

**Claim:** Runtime delivery terminal references render only for string `terminal_id` values and request dashboard terminal focus.

**Evidence:** `terminalTarget` is read with `stringFact` at `web/src/components/timelineEventViews/knownCaoEventViews.tsx:192`; rendering is conditional at line 204; click handling calls `onFocusTerminal(terminalTarget)` at line 209.

### Clause: `C-CC-5`

**Claim:** `AgentPanel` remains the owner of terminal lookup, session selection, and `TerminalView` opening.

**Evidence:** `AgentIdentityTimelinePanel` only accepts `onFocusTerminal` at `web/src/components/AgentIdentityTimelinePanel.tsx:233`; `AgentPanel` implements lookup/session/open logic at `web/src/components/AgentPanel.tsx:183` and passes the callback at line 265.

### Clause: `C-CC-6`

**Claim:** Missing target facts degrade to readable non-clickable content.

**Evidence:** Linear issue context remains a `DetailPill` at `web/src/components/timelineEventViews/knownCaoEventViews.tsx:168`; external button rendering requires `issueUrl` at line 171. Runtime terminal text falls back to `No terminal recorded` at line 193; internal button rendering requires `terminalTarget` at line 204.

### Clause: `C-CC-7`

**Claim:** Related rows continue to dispatch every related event group through the registry and receive the same navigation callbacks as main rows.

**Evidence:** `RelatedEventList` calls `eventTimelineViewRegistry.viewFor(event.event_type_key)` at `web/src/components/AgentIdentityTimelinePanel.tsx:122`, renders the selected view at line 125, and each related group passes the shared callbacks at lines 206, 213, and 221.

### Clause: `C-CC-8`

**Claim:** New registry-module exports are limited to production-facing navigation callback types.

**Evidence:** `web/src/components/timelineEventViews.tsx:6` exports `OpenExternalReference` and `FocusTerminalReference`; both are imported by the production timeline panel at `web/src/components/AgentIdentityTimelinePanel.tsx:6`.

## Committed Implementation Decisions

### Decision: `CID-1`

**Claim:** Backend timeline reads remain data-only.

**Evidence:** No backend files changed; views read existing `event_data` fields.

### Decision: `CID-2`

**Claim:** Main and related rows dispatch through `eventTimelineViewRegistry.viewFor(event_type_key)`.

**Evidence:** Main dispatch is at `web/src/components/AgentIdentityTimelinePanel.tsx:159`; related dispatch is at line 122.

### Decision: `CID-3`

**Claim:** Generated frontend CAO event type constants remain the source for known view registration.

**Evidence:** `web/src/components/timelineEventViews/knownCaoEventViews.tsx:3` imports generated constants; no generated constant workflow changed.

### Decision: `CID-4`

**Claim:** Known event views continue self-registering through `timelineEventViewRegistrations`.

**Evidence:** `web/src/components/timelineEventViews/knownCaoEventViews.tsx` still exports registrations, and `web/src/components/timelineEventViews.tsx` still discovers modules with `import.meta.glob`.

## Committed-Decision Promotion Draft

No promotion warranted: this task applied existing committed decisions and did not settle a new durable cross-task implementation fact beyond the task-local navigation callback shape.

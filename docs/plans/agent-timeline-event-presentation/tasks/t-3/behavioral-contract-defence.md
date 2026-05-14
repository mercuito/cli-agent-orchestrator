# Behavioral Contract Defence — t-3

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Every assigned behavior and invariant needs concrete test or implementation evidence. |
| `broad-claim-coverage` | Related-event continuity depends on composition across related-event groups and registry selection. |

## Behavior: `B-6`

**Claim:** Related events render through the same frontend typed views and fallback view used by main timeline rows.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:121` and `web/src/components/AgentIdentityTimelinePanel.tsx:159` both resolve views through `eventTimelineViewRegistry.viewFor(event.event_type_key)`. `web/src/test/agent-identity-timeline-panel.test.tsx:462` proves a related runtime delivery renders taught delivery content and an untaught related audit event renders fallback content. Exact Verification Command passed.

## Behavior: `B-7`

**Claim:** A Linear mention external entity reference opens the authored Linear issue URL without requiring copy/search.

**Evidence:** `web/src/components/timelineEventViews/knownCaoEventViews.tsx:154` reads `issue_url` from `event.event_data`, and `web/src/components/timelineEventViews/knownCaoEventViews.tsx:171` renders the external reference button only when that target exists. `web/src/components/AgentIdentityTimelinePanel.tsx:238` opens external references with `_blank` and `noopener,noreferrer`. `web/src/test/agent-identity-timeline-panel.test.tsx:488` proves the authored Linear issue URL is opened with those browser-target arguments. Exact Verification Command passed.

## Behavior: `B-8`

**Claim:** A runtime delivery internal entity reference focuses the referenced dashboard terminal.

**Evidence:** `web/src/components/timelineEventViews/knownCaoEventViews.tsx:192` reads `terminal_id` from `event.event_data`, and `web/src/components/timelineEventViews/knownCaoEventViews.tsx:204` renders the internal terminal button only when that target exists. `web/src/components/AgentPanel.tsx:183` resolves the terminal and opens it through the dashboard flow. `web/src/test/agent-panel-deeplink.test.tsx:231` proves following the reference calls `getTerminal('term-aria-main')`, selects that terminal's session, and opens `TerminalView` for `term-aria-main`. Exact Verification Command passed.

## Constraint: `C-2`

**Claim:** The same event presentation path is used in the main row and related-event row for one watched identity context, aside from the existing `surface` layout prop.

**Evidence:** `web/src/components/AgentIdentityTimelinePanel.tsx:164` and `web/src/components/AgentIdentityTimelinePanel.tsx:125` both render the registry-selected `EventView` with the same event and navigation props, differing only by `surface="main"` or `surface="related"`. `web/src/test/agent-identity-timeline-panel.test.tsx:462` proves the related runtime delivery keeps its taught runtime presentation. Exact Verification Command passed.

## Constraint: `C-3`

**Claim:** Entity references preserve target kind: Linear issue references are external URL opens, and runtime delivery terminal references are internal dashboard terminal focus requests.

**Evidence:** `web/src/components/timelineEventViews/knownCaoEventViews.tsx:171` wires Linear issue references to `onOpenExternalReference(issueUrl)`. `web/src/components/timelineEventViews/knownCaoEventViews.tsx:204` wires terminal references to `onFocusTerminal(terminalTarget)`. `web/src/test/agent-identity-timeline-panel.test.tsx:488` proves external browser opening, while `web/src/test/agent-identity-timeline-panel.test.tsx:520` and `web/src/test/agent-panel-deeplink.test.tsx:231` prove internal terminal focus. Exact Verification Command passed.

# Code Contract Defence — t-2

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| `claim-evidence-verifiability` | Every feature and coding code contract claim needs concrete code or verification evidence. |
| `promotion-draft-durability` | This task settles generated event-key and self-registration surfaces future event-view tasks should inherit. |

## Feature-Level Code Contract

### Clause: `F-CC-3`

**Claim:** Known event views are frontend-owned, typed, and read event facts
from the envelope plus `event_data`.

**Evidence:** `web/src/components/timelineEventViews/knownCaoEventViews.tsx`
contains the Linear mention, runtime delivery, workspace context switch, and
runtime lifecycle views. Each view reads `event.event_data` through
`stringFact`/`booleanFact` narrowing and renders readable fallback values for
missing optional facts. Backend changes are limited to runtime delivery event
data fields in `src/cli_agent_orchestrator/runtime/events.py` and
`src/cli_agent_orchestrator/runtime/agent.py`.

### Clause: `F-CC-6`

**Claim:** Known views use generated event type constants and module
self-registration.

**Evidence:** `scripts/generate_cao_event_type_keys.py` discovers backend
`*_CAO_EVENTS` tuples and calls `event_type_key` to generate
`web/src/generated/caoEventTypeKeys.ts`. `knownCaoEventViews.tsx` imports
generated constants and exports `timelineEventViewRegistrations`.
`web/src/components/timelineEventViews.tsx` discovers view modules with
`import.meta.glob('./timelineEventViews/*.tsx', { eager: true })` and registers
their declarations. No known view code hand-types fully qualified backend
event type key strings.

## Coding Code Contract

### Selected Criteria

**Claim:** The selected coding-level criteria are satisfied.

**Evidence:** Red-green proof was used for backend runtime payload facts and
frontend known views. The exact Verification Command succeeded. Changes stayed
inside runtime event data plumbing, frontend timeline event views, generated
event-key wiring, focused tests, and task artifacts. The generator owns the
build-tool filesystem boundary, uses `pathlib.Path`, and writes only the
generated event-key file. Generated constants centralize event-key vocabulary;
payload field-name constants intentionally duplicate backend JSON field names
at the typed view boundary with an adjacent ownership comment. Registry
discovery keeps concrete matching inside the registry owner surface.

### Clause: `C-CC-1`

**Claim:** Generated TypeScript event constants come from backend CAO event
classes via `event_type_key`.

**Evidence:** `scripts/generate_cao_event_type_keys.py` imports only modules
with discovered `*_CAO_EVENTS` tuples and calls `event_type_key(event_type)`;
generated constants live in `web/src/generated/caoEventTypeKeys.ts`.

### Clause: `C-CC-2`

**Claim:** View modules self-register through module discovery without a
central manual registry list.

**Evidence:** `timelineEventViews.tsx` eagerly discovers
`./timelineEventViews/*.tsx` modules and registers each exported
`timelineEventViewRegistrations` entry. `knownCaoEventViews.tsx` declares the
four handled generated constants locally.

### Clause: `C-CC-3`

**Claim:** Taught views read only envelope and `event_data` facts, not backend
presentation values.

**Evidence:** `knownCaoEventViews.tsx` receives `TimelineEventViewProps` with
`event`, reads `event.event_data`, and does not consume any backend
presentation DTO. The Linear mention title is generic to the watched agent
rather than hard-coding an identity name. No backend presentation surface was
added.

### Clause: `C-CC-4`

**Claim:** Taught views narrow payload fields and degrade for missing optional
facts.

**Evidence:** `stringFact` and `booleanFact` guard payload reads. Delivery
fallback strings include `Unknown source`, `No message text recorded`, and
`No terminal recorded`; the frontend known-view test asserts those missing
optional fact fallbacks render.

### Clause: `C-CC-5`

**Claim:** Linear mention rows surface issue, mentioner, snippet, and issue
context.

**Evidence:** `LinearMentionTimelineEventView` renders issue identifier/title,
mentioner, and message snippet from `event_data`; the frontend test asserts
the `OPS-417`, title, `Nia`, mention text, and `Linear issue` content.

### Clause: `C-CC-6`

**Claim:** Runtime delivery rows surface source kind, message, and terminal,
with minimum backend data plumbing for source/message facts.

**Evidence:** `AgentRuntimeNotificationDeliveryEvent` now includes
`source_kind` and `message_body`; `AgentRuntimeHandle` populates them from the
durable notification delivery. `RuntimeDeliveryTimelineEventView` renders
source, terminal, outcome, and message. Runtime, API, and frontend tests assert
these facts.

### Clause: `C-CC-7`

**Claim:** Workspace switch rows surface from-context and to-context without
navigation behavior.

**Evidence:** `WorkspaceContextSwitchTimelineEventView` renders
`from_workspace_context_id` and `to_workspace_context_id` as text pills. It
does not create buttons, links, or focus handlers.

### Clause: `C-CC-8`

**Claim:** Runtime lifecycle rows surface phase, runtime status/health,
terminal, and workspace context.

**Evidence:** `RuntimeLifecycleTimelineEventView` renders `action`,
`runtime_status` or `attention needed`, `terminal_id`, and
`workspace_context_id`; the frontend test asserts `restarted`, `idle`,
`term-aria-main`, and `yards`.

### Clause: `C-CC-9`

**Claim:** Backend changes are limited to required data plumbing and do not add
presentation values.

**Evidence:** Backend changes only add typed runtime delivery event fields and
populate them from existing durable notification data. `rg` finds no new
backend `TimelineEventPresentation`, `to_timeline_presentation`, or presenter
registry in the changed implementation.

### Clause: `C-CC-10`

**Claim:** The generator uses path utilities and writes only the generated
event-key file.

**Evidence:** `scripts/generate_cao_event_type_keys.py` uses `pathlib.Path` to
derive `REPO_ROOT`, `SRC_ROOT`, and `OUTPUT_PATH`, and writes only
`web/src/generated/caoEventTypeKeys.ts`.

### Clause: `C-CC-11`

**Claim:** Payload field-name duplication is documented and localized to the
frontend typed view boundary.

**Evidence:** `knownCaoEventViews.tsx` defines payload key constant objects
with an adjacent comment explaining that the names mirror backend dataclass
`event_data` JSON keys at the frontend presentation boundary; view bodies read
those constants instead of scattering raw payload key strings.

## Committed Implementation Decisions

### Decision: `CID-1`

**Claim:** Backend timeline reads remain data-only.

**Evidence:** Timeline API code was not changed to add presentation fields.
Runtime delivery payload expansion adds event facts before persistence; the
frontend still owns presentation.

### Decision: `CID-2`

**Claim:** The registry owner remains `web/src/components/timelineEventViews.tsx`
and rows dispatch through `eventTimelineViewRegistry.viewFor(event_type_key)`.

**Evidence:** `AgentIdentityTimelinePanel.tsx` remains unchanged for dispatch,
and `timelineEventViews.tsx` still exports `eventTimelineViewRegistry`.

## Committed-Decision Promotion Draft

Proposed entries:

- `CID-3`: Generated frontend CAO event type constants live at
  `web/src/generated/caoEventTypeKeys.ts` and are refreshed by
  `scripts/generate_cao_event_type_keys.py`, which discovers backend
  module-owned `*_CAO_EVENTS` tuples and calls
  `cli_agent_orchestrator.events.serialization.event_type_key`.
- `CID-4`: Frontend known event view modules self-register by exporting
  `timelineEventViewRegistrations` from files under
  `web/src/components/timelineEventViews/`; `timelineEventViews.tsx` discovers
  those modules with Vite `import.meta.glob` and registers the declared views.

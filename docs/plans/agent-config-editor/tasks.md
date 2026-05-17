# Agent Config Editor Tasks (Draft v1)

This task list derives from `docs/plans/agent-config-editor/plan.md`.

Policy: any task that changes code requires reviewer gate before it is
considered complete.

Every task includes a criteria-catalog acceptance bullet. Before
completion, the implementer walks the catalog at
`docs/criteria/implementation/` and `docs/criteria/tests/` (browseable
via `uv run python scripts/catalog_criteria.py`), identifies every
entry whose `when` clause applies to the task's changes, and confirms
the landed code satisfies it.

This plan inherits the hard-cutover discipline. Forbidden in any task:
shims, facades, fallback chains, feature flags, deprecation warnings,
function/module aliases preserving old import paths, optional props
preserving old behavior, hardcoded provider lists or
`reasoning_effort` enums in the dashboard, duplicate provider
enumeration in the backend, and runtime translators between old and
new shapes. Legacy call sites are migrated or deleted, not bridged.

## Phase 1 — Backend foundation

### T01 — Provider capability surface

- owner_role: developer
- dispatch_mode: handoff
- depends_on: []
- deliverables:
  - each provider class in `src/cli_agent_orchestrator/providers/`
    declares `supported_reasoning_efforts() -> tuple[str, ...] | None`
    and `suggested_models() -> tuple[str, ...] | None` as
    classmethods (or class attributes)
  - default implementation on the base `Provider` class returns None
    for both — providers that don't override stay non-capable
  - `claude_code` returns `("low", "medium", "high")` for
    `supported_reasoning_efforts` (matches what
    `claude_code.py:355` currently passes via `--effort`)
  - `claude_code` returns a curated list of common Claude models for
    `suggested_models` (start with Opus 4.7, Sonnet 4.6, Haiku 4.5;
    document the list as suggestions, not enforcement)
  - other providers leave both as None (default) unless they have a
    concrete reason to declare otherwise
  - declarations live in each provider's existing file, not in a
    separate capability registry (per
    `system-definitions-are-localized`)
  - unit tests per provider verifying the declared values
- acceptance:
  - `Provider.supported_reasoning_efforts()` and
    `Provider.suggested_models()` exist as part of the provider
    contract
  - `claude_code` declarations match what the launch path currently
    uses (`--effort` value space)
  - tests cover at least three providers (claude_code with values,
    one other with None, and the base default)
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or
    deleted, not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by
    the landed code

### T02 — Restore `GET /providers` endpoint

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - new endpoint `GET /providers` returning a list of
    `ProviderSchemaResponse` objects, one per registered provider
  - each entry includes: `name` (the `ProviderType` value),
    `binary` (binary name), `installed` (bool, via `shutil.which`),
    `supported_reasoning_efforts` (list[str] | null),
    `suggested_models` (list[str] | null)
  - the endpoint enumerates providers from `ProviderType` —
    single source of truth, no parallel list
  - response model defined in
    `src/cli_agent_orchestrator/api/main.py` alongside the existing
    response models
  - integration tests against the endpoint covering: all providers
    present, install status reflects the binary's presence on path,
    capability fields match what providers declared in T01
- acceptance:
  - `GET /providers` returns one entry per `ProviderType` value
  - install status is dynamic (test by mocking `shutil.which`)
  - capability fields are derived from provider classes, not
    re-declared in the endpoint
  - no backwards-compatibility layer introduced — same forbidden
    patterns as above
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by
    the landed code

### T03 — Save-time validation for enumerated fields

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - `PUT /agents/{id}` rejects requests where `cli_provider` is not a
    `ProviderType` value (400 with field-level detail)
  - `PUT /agents/{id}` rejects requests where `reasoning_effort` is
    set but the selected provider's
    `supported_reasoning_efforts()` is None OR does not include the
    submitted value (400 with field-level detail naming both the
    offending value and the provider)
  - validation happens at the service/dataclass layer, not only in
    the HTTP handler — so direct calls to the agent writer can't
    bypass it
  - error responses include enough field-level detail for the
    dashboard to surface inline messages against the offending input
  - unit and integration tests covering: valid save, bad
    `cli_provider`, `reasoning_effort` on a provider that returns
    None, `reasoning_effort` outside the supported set
- acceptance:
  - a `PUT` with `cli_provider = "bogus"` returns 400 with a clear
    error pointing at `cli_provider`
  - a `PUT` setting `reasoning_effort = "ultra"` for `claude_code`
    returns 400 naming both the value and the supported set
  - a `PUT` setting `reasoning_effort = "low"` for `codex` returns
    400 explaining that codex does not support reasoning_effort
  - a valid `PUT` succeeds and the agent file reflects the change
  - validation cannot be bypassed by going through the service or
    dataclass layer directly
  - no backwards-compatibility layer introduced — same forbidden
    patterns as above
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by
    the landed code

## Phase 2 — Frontend schema consumer

### T04 — Provider schema fetcher

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- deliverables:
  - new module/hook under `web/src/` (recommended:
    `web/src/api.ts` for the fetch function +
    `web/src/components/agents-tab/useProviderSchema.ts` or similar
    for a session-cached hook) that calls `GET /providers` once and
    exposes the resulting schema
  - the hook handles loading and error states (the form must render a
    loading state until resolved, not a falsy "no providers known"
    state)
  - shared placement: the hook is callable from multiple components
    (per `properly-designed-shared-code`); even though only the
    Config tab uses it in v1, the create-agent modal in
    `AgentPanel.tsx` will benefit later
  - typed response models in `web/src/api.ts` matching the backend
    `ProviderSchemaResponse` shape exactly (per
    `authoritative-sources-are-referenced-not-copied` — the type
    mirrors the backend, not re-derives it)
  - component tests covering: loading state, success state, error
    state, the cache pattern (a second consumer doesn't trigger a
    second fetch)
- acceptance:
  - mounting a component that uses the hook fires one network call;
    a second consumer in the same session reuses the cached result
  - error state surfaces in the consuming component without crashing
  - typed response matches the backend schema; manual hardcoding of
    provider names in the dashboard is avoided
  - no backwards-compatibility layer introduced — same forbidden
    patterns as above
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by
    the landed code

## Phase 3 — Structured form

### T05 — Five-field structured form section in `AgentConfigTab`

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T03, T04]
- deliverables:
  - new "Structured fields" section inside `AgentConfigTab`
    rendering inputs for:
    - `display_name` (text)
    - `description` (textarea, 3–5 rows)
    - `cli_provider` (dropdown sourced from the schema fetcher;
      installed-status indicator next to each option)
    - `model` (combobox: select-from-suggested or type-your-own;
      suggestions come from the selected provider's
      `suggested_models`)
    - `reasoning_effort` (dropdown sourced from selected provider's
      `supported_reasoning_efforts`; rendered DISABLED with a
      tooltip explaining the selected provider doesn't support it
      when the provider returns null — the field is always visible,
      never hidden, so users learn that the concept exists and which
      providers support it)
  - read-only display of `id`, `session_name`, and `workdir` in the
    panel header area (these are not in the editable form for v1;
    raw-TOML editing remains the escape hatch for `session_name`
    and `workdir`; `id` is also filtered out of raw TOML per T06)
  - read mode shows current structured values as labeled text;
    edit mode flips the section into inputs
  - save flow: form values get serialized back into the agent.toml
    representation by overriding the relevant top-level keys; the
    raw-TOML section's contents (from T06) provide everything else;
    the merged result goes to `PUT /agents/{id}`
  - inline error display: when the backend returns 400 with
    field-level errors, the offending field shows the error message
    in red below the input
  - component tests covering: read mode renders each field, edit
    mode flips to inputs, dropdown options reflect the schema, save
    sends the merged TOML, server-side errors surface inline,
    `reasoning_effort` is disabled (not hidden) when the selected
    provider returns null and shows a tooltip explaining why
- acceptance:
  - selecting an agent and clicking Edit shows the five structured
    fields as inputs/dropdowns with current values pre-filled
  - changing `cli_provider` updates `reasoning_effort`'s
    enabled/disabled state and option set without a save round-trip
  - selecting a provider that returns null for
    `supported_reasoning_efforts` leaves the `reasoning_effort`
    dropdown visibly disabled with an explanatory tooltip
  - typing an invalid `reasoning_effort` (e.g. via combobox) gets
    caught client-side or by the backend with the error surfaced
    inline
  - the form does not re-declare provider names or
    reasoning_effort values — all sourced from the schema fetcher
    per `authoritative-sources-are-referenced-not-copied`
  - no backwards-compatibility layer introduced — same forbidden
    patterns as above
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by
    the landed code

### T06 — Panel layout: structured-on-top, raw-TOML collapsible-below

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T05]
- deliverables:
  - `AgentConfigTab` reorganized so the structured form section
    (T05) sits at the top; the raw TOML view sits below in a
    collapsible disclosure (default collapsed)
  - the raw TOML's textarea content (in edit mode) is filtered to
    exclude the structured-form fields (`display_name`,
    `description`, `cli_provider`, `model`, `reasoning_effort`) so
    users can't double-edit those keys
  - the `id` line is also filtered out of the raw textarea (the id
    is immutable; editing it would corrupt the save)
  - `workdir` and `session_name` REMAIN in the raw textarea as the
    escape hatch for advanced edits (they appear read-only in the
    header but are still editable via raw TOML)
  - existing `prompt.md` view/edit and Linear secrets summary
    preserved unchanged below
  - single Edit / Save / Cancel button row applies to the entire
    panel: clicking Edit flips structured fields, prompt textarea,
    and (if expanded) the raw TOML section into edit mode
    simultaneously; Save submits one merged `PUT /agents/{id}`
  - the raw TOML's collapsed-state and expanded-state both work in
    read mode (formatted display) and edit mode (textarea)
  - component tests covering: collapsed-by-default, expand-collapse
    works, raw textarea in edit mode excludes the structured-form
    fields, save merges structured + raw correctly, no fields are
    dropped or duplicated
- acceptance:
  - by default, a selected agent shows the five structured fields
    visibly and the raw TOML hidden behind a disclosure
  - editing `display_name` via the form and any unstructured field
    via the raw TOML and saving produces an agent.toml with both
    changes
  - the raw TOML never contains a duplicate `display_name`,
    `description`, `cli_provider`, `model`, `reasoning_effort`, or
    `id` key — those are owned by the structured section (or, for
    `id`, the directory name); `workdir` and `session_name` remain
    in the raw TOML as editable escape-hatch fields
  - no backwards-compatibility layer introduced — same forbidden
    patterns as above
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by
    the landed code

## Phase 4 — Cleanup

### T07 — Sweep and finalize tests

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T06]
- deliverables:
  - remove any helpers or fixtures made obsolete by the structured
    form (e.g. the old "raw-only edit" code path inside
    `AgentConfigTab` if it became unreachable)
  - update any tests that previously exercised the raw-only edit
    flow to reflect the new structured-plus-raw layout
  - verify `grep -rn "cli_provider\|reasoning_effort" web/src/`
    returns hits only inside the structured form, the schema
    fetcher, type definitions, or tests — not hardcoded option
    arrays anywhere else
  - full test suite passes (`npm test` / `vitest` for web; pytest
    for backend)
- acceptance:
  - the web and backend test suites both pass on a clean checkout
  - no dead code remains from the pre-structured-form layout
  - no provider names or reasoning_effort values are duplicated in
    the dashboard outside the schema fetcher
  - no backwards-compatibility layer introduced — same forbidden
    patterns as above
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by
    the landed code

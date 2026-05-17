# Agent Config Editor (Draft v1)

Status: draft

This plan adds a structured config editor to the Agents tab — replacing
raw-TOML editing for the most-commonly-edited fields with proper form
controls, while keeping raw TOML available as a collapsible escape hatch
for unstructured fields (MCP servers, hooks, Linear bindings, etc.).
Builds on the unified `AgentConfigTab` introduced by the
`agents-tab-unification` plan.

The editor's value depends entirely on dropdowns being populated from
authoritative sources. `cli_provider` must equal a member of the
`ProviderType` enum. `reasoning_effort` must be a value the selected
provider actually supports. The plan therefore introduces a provider
capability surface plus a restored `/providers` endpoint exposing that
schema to the dashboard.

---

## Locked design

**Tier 1 editable fields (five):**

| Field | UI control | Strictness | Source of truth |
|---|---|---|---|
| `display_name` | text input | free | n/a |
| `description` | textarea | free | n/a |
| `cli_provider` | dropdown | hard enum | `ProviderType` enum + `/providers` install status |
| `model` | combobox | soft suggestions | per-provider `suggested_models()`, free text allowed |
| `reasoning_effort` | dropdown | hard enum, per-provider | per-provider `supported_reasoning_efforts()`; rendered disabled with a tooltip when provider returns None |

**Read-only fields (header):**

- `id` — agent id, immutable. Shown in the panel header next to display
  name. The form does not expose it as editable; the raw TOML editor
  filters it out so users never type a change that would fail save.
- `session_name` — implementation-detail. Shown in the header; not
  editable in v1.
- `workdir` — the agent's starting directory. Shown in the header so
  users can see which project the agent is bound to, but not promoted
  to a structured form field in v1 (changing it has consequences that
  need their own UX design). The raw TOML escape hatch still permits
  edits for advanced users.

**Read-only Linear secrets summary:** preserved as today (mask + reveal
toggle for client_secret/webhook_secret; OAuth tokens labeled "Managed
by OAuth callback").

**Out of scope for v1:** structured editing of `mcp_servers`, `tools`,
`cao_tools`, `skills`, `tags`, `tool_aliases`, `tools_settings`,
`hooks`, `codex_config`, `runtime_capabilities`, `resources`,
`workspace_context`, and the Linear `[linear]` block (beyond the
existing secrets summary). All of these stay in the collapsible raw
TOML section.

### Provider capability surface

Each provider class exposes (as classmethods or class attributes on the
existing `Provider` protocol):

```python
@classmethod
def supported_reasoning_efforts(cls) -> tuple[str, ...] | None:
    """Return the reasoning_effort values this provider accepts, or
    None when reasoning_effort is not a meaningful concept for this
    provider."""
    return None  # default

@classmethod
def suggested_models(cls) -> tuple[str, ...] | None:
    """Return suggested model names for autocomplete. None means no
    suggestions; the field stays free text."""
    return None  # default
```

Today only `claude_code` reads `reasoning_effort` (passes
`--effort <value>` to the Claude CLI). It returns
`("low", "medium", "high")`. Every other provider returns None. The
declarations live with the provider class — one architectural home per
provider, per `system-definitions-are-localized`.

### `GET /providers` endpoint

Restored. Returns the full schema in one fetch:

```json
[
  {
    "name": "claude_code",
    "binary": "claude",
    "installed": true,
    "supported_reasoning_efforts": ["low", "medium", "high"],
    "suggested_models": ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"]
  },
  {
    "name": "codex",
    "binary": "codex",
    "installed": true,
    "supported_reasoning_efforts": null,
    "suggested_models": null
  },
  ...
]
```

The dashboard fetches once on Agents-tab mount (cached for the session).

### Save-time validation

When `PUT /agents/{id}` receives a config update:

- `cli_provider` must be a `ProviderType` member; otherwise 400.
- If `reasoning_effort` is set: the selected provider's
  `supported_reasoning_efforts()` must include the value; otherwise
  400 with a clear message naming the offending field and provider.
- `model` passes through (no enforcement — model namespaces are too
  fluid).
- Other fields validated by the existing Agent dataclass construction.

Errors return as 400 with field-level detail; the dashboard surfaces
them inline against the offending input.

### Panel layout (Config tab)

```
┌─ Status header (from AgentDetailPanel, already exists) ─┐
│ id · display_name · running/stopped · terminal · S/S   │
└─────────────────────────────────────────────────────────┘
┌─ Structured fields ─────────────────────────────────────┐
│ display_name      [_____________________________]      │
│ description       [_______________________________]    │
│                   [_______________________________]    │
│ cli_provider      [claude_code ▾]                      │
│ model             [claude-opus-4-7 ▾]                  │
│ reasoning_effort  [medium ▾]   (disabled with tooltip   │
│                                 when provider doesn't   │
│                                 support it)             │
└─────────────────────────────────────────────────────────┘
┌─ Raw TOML (collapsible, default collapsed) ─────────────┐
│ ▸ Show raw TOML  (everything not in the form above)     │
└─────────────────────────────────────────────────────────┘
┌─ prompt.md (existing) ──────────────────────────────────┐
│ ...                                                     │
└─────────────────────────────────────────────────────────┘
┌─ Linear secrets summary (existing) ─────────────────────┐
│ ...                                                     │
└─────────────────────────────────────────────────────────┘
```

Single Edit / Save / Cancel for the whole panel. When entering edit
mode, the structured fields become editable inputs, the raw TOML
section (if expanded) becomes a textarea filtered to exclude
structured-form fields, and the prompt becomes a textarea. On save the
structured form values are merged into the TOML representation; the
raw textarea's contents provide everything else; the merged result
goes to `PUT /agents/{id}`.

## Forbidden compatibility patterns

Inherits the hard-cutover discipline. Forbidden in any task:

- Hardcoded provider lists in the dashboard (violates
  `authoritative-sources-are-referenced-not-copied`).
- Hardcoded `reasoning_effort` enums in the dashboard (same).
- Duplicate provider enumeration in the backend (the
  `ProviderType` enum is the single source).
- Optional props on the structured form that fall back to "show all
  fields" or "show no fields" depending on whether the schema is
  loaded — instead, render a loading state until the schema resolves.
- Feature flags toggling between raw-only and structured-and-raw
  layouts. Old raw-only behavior is replaced atomically.

## Criteria catalog (likely applicable)

The implementer must run `uv run python scripts/catalog_criteria.py`
and apply every entry whose `when` clause matches the actual diff.
This plan does NOT claim the final applicable set. Criteria identified
as likely to shape this work:

- **`authoritative-sources-are-referenced-not-copied`** — central
  concern. `ProviderType` is the source of provider names. Per-provider
  capability methods are the source for reasoning_effort sets and
  suggested models. The dashboard imports nothing literal; it fetches.
- **`system-definitions-are-localized`** — each provider's capability
  declarations live in its own provider class file, not in a separate
  capability registry.
- **`no-unnecessary-duplication`** — the existing schema-fetching
  pattern (if any), the existing Edit/Save/Cancel handler in
  `AgentConfigTab`, and the existing inline-error UI all get reused.
  The form does not re-implement equivalents.
- **`prefer-public-surfaces`** — the dashboard consumes
  `GET /providers` and `PUT /agents/{id}` as public surfaces. The
  backend consumes each provider class through its declared capability
  methods, not by introspecting internals.
- **`properly-designed-shared-code`** — the schema fetcher (hook or
  module) lives in a shared location callable from multiple components
  if needed, not nested under one consumer.
- **`seams-must-be-tested`** — new seams: dashboard ↔ `/providers`,
  dashboard ↔ `PUT /agents/{id}` (with new validation paths),
  provider class ↔ capability declarations, save handler ↔ Agent
  dataclass write path. Each needs a test exercising the boundary.
- **`test-through-owner-surfaces`** — tests for the form use the same
  response shapes the real `/providers` endpoint produces. Provider
  capability tests go through the provider class's declared interface,
  not internals.
- **`no-test-only-production-seams`** — the provider capability
  classmethods are production-meaningful (the launch path can use
  `reasoning_effort` validation too), not just test scaffolding.

## Criteria acceptance

After implementation, evaluate the pending changes against the criteria
catalog. No criteria applicable to the completed diff may be violated.
Enforced per-task by the criteria-catalog acceptance bullet in
`docs/plans/agent-config-editor/tasks.md`.

## Goals

- Five Tier-1 fields editable through proper form controls.
- Provider-aware dropdowns backed by authoritative backend sources.
- Save-time validation rejects bad `cli_provider` / `reasoning_effort`
  values with field-level errors surfaced inline.
- Raw TOML remains accessible (collapsible) for fields not yet in the
  structured form, including `workdir` and `session_name` for users
  who need to edit them.
- The `id` field is never editable through the dashboard.

## Non-goals

- Structured editing for any Tier 2/3 fields (lists, MCP servers,
  Linear block, hooks, etc.). All stay in raw TOML.
- A model registry or per-provider model validation. `model` stays
  free-text with soft suggestions.
- Rename support for `id` (still out of scope; see
  `agents-tab-unification` discussion).
- Reorganizing the agent dataclass or changing the on-disk file shape.

## Phasing

Four phases. Phase 1 lands backend foundations in parallel. Phase 2
adds the dashboard schema consumer. Phase 3 builds the structured form
and panel layout. Phase 4 cleans up.

### Phase 1 — Backend foundation

T01 adds the provider capability surface (classmethods on each provider
class). T02 restores `GET /providers` exposing the schema. T03 adds
save-time validation in `PUT /agents/{id}` for the enumerated fields.

### Phase 2 — Frontend schema consumer

T04 adds a schema fetcher (hook or module) that calls `/providers`
once and caches the result for the session. Used by any form needing
provider-aware dropdowns.

### Phase 3 — Structured form

T05 builds the five-field form section inside `AgentConfigTab`,
consuming the schema fetcher and surfacing validation errors. T06
reorganizes the panel layout: structured form on top, raw TOML
collapsible below filtered to exclude structured-form fields, with the
existing prompt and Linear secrets summary preserved.

### Phase 4 — Cleanup

T07 sweeps for stragglers and finalizes tests. Removes any obsolete
helpers, dead imports, or stale test fixtures.

The full task breakdown lives in
`docs/plans/agent-config-editor/tasks.md`.

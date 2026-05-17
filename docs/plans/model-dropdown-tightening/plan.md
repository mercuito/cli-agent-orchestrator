# Model Dropdown Tightening (Draft v1)

Status: draft

This plan tightens the `model` field from a soft-suggested combobox to a
strict dropdown, mirroring how `cli_provider` and `reasoning_effort`
already work. The user's review pushed for this: dropdowns are the
discipline — typing free text into a combobox doesn't catch typos and
doesn't let the dashboard help.

The agent-config-editor plan originally treated `model` as soft because
"model namespaces are too fluid to enumerate authoritatively." That was
the wrong call. Each provider's CLI does have an enumeration its
validator enforces (the provider-capability-audit plan demonstrated this
by empirically extracting codex's reasoning_effort enum from the CLI's
own rejection message). The same approach applies to models.

---

## Locked design

- The dashboard's `model` field becomes a **strict dropdown**, not a
  combobox. No free-text entry.
- Each provider declares its supported model namespace via
  `supported_models() -> tuple[str, ...]`. The return is a non-empty
  tuple — every provider has a meaningful enumeration; none "accepts
  arbitrary strings." The existing `suggested_models()` method is
  renamed (hard cutover; no alias).
- The base provider's `supported_models()` is **abstract / raises**.
  Concrete providers must implement it; there is no defaulting to
  None or empty. This guarantees the dashboard always has a
  non-empty dropdown for every provider.
- `GET /providers` returns `supported_models` (renamed from
  `suggested_models`) in the response schema, always non-null.
- Save-time validation in the agent dataclass rejects a `model` value
  that the selected provider's `supported_models()` doesn't contain
  (with field-level detail in the 400 response).

### Provider-by-provider expected outcome

Every provider declares a real, non-empty list. Where the CLI's own
validator exposes an enum, extract it empirically (the same way
codex's reasoning_effort enum was extracted in
`provider-capability-audit` T01-T02). Where the CLI is more
permissive, declare a curated list of supported/recommended models for
that provider — this is the authoritative list from the dashboard's
perspective, even if the underlying CLI/API would accept more.

| Provider | Approach |
|---|---|
| `claude_code` | curated list of common Claude models (the existing `suggested_models` set is a reasonable starting point — promote to authoritative) |
| `codex` | extracted from codex CLI's model validator if it has an enum; otherwise curated list of common GPT-5-family models |
| `gemini_cli` | curated list of Google's documented Gemini models |
| `q_cli`, `kiro_cli`, `kimi_cli`, `copilot_cli` | audit each; declare a curated list of common/recommended models per provider. Empty / None is not a permitted outcome — if the audit can't surface anything, escalate. |

The principle: from the dashboard's perspective, every provider has a
finite, declared model namespace. The dashboard never has to fall back
to free text. Users who need a model outside the curated list edit the
raw TOML escape hatch.

## Goals

- `model` is a strict dropdown in the dashboard structured form.
- Each provider's declared `supported_models` reflects an honest set,
  derived empirically when possible.
- Save-time validation enforces membership at the agent dataclass /
  service layer, not only at the HTTP boundary.
- The `model` dropdown is always populated and enabled — every
  provider declares a real non-empty list. Unlike `reasoning_effort`,
  there is no disabled-when-null path for `model`.

## Non-goals

- No new capability fields beyond renaming `suggested_models` →
  `supported_models`.
- No model registry, dynamic model discovery via the providers' APIs at
  runtime, or caching layer. Declarations are static per provider class.
- No free-text escape valve in the dashboard. If a user needs a model
  outside the declared set, they edit raw TOML (the existing escape
  hatch).
- No changes to the `cli_provider` or `reasoning_effort` handling.

## Forbidden compatibility patterns

Inherits the hard-cutover discipline. Forbidden in any task:

- Keeping a `suggested_models()` alias on the base provider for
  backward compatibility. The rename is hard cutover.
- Hardcoding model lists in the dashboard. Lists come exclusively
  from the `/providers` response.
- Declaring `None` or an empty tuple from any provider's
  `supported_models()`. Every provider implements the method with
  a non-empty tuple. If a provider's audit can't surface a list,
  escalate.
- Falling back to free-text entry anywhere in the dashboard.
- Adding the validation only at the HTTP boundary while leaving the
  dataclass / writer paths permissive.

## Criteria catalog (likely applicable)

The implementer must run `uv run python scripts/catalog_criteria.py`
and apply every entry whose `when` clause matches the actual diff.
Criteria likely to shape this work:

- **`authoritative-sources-are-referenced-not-copied`** — model lists
  come from provider declarations only; the dashboard imports
  nothing literal.
- **`migration-discipline`** — `suggested_models()` →
  `supported_models()` is a rename across the codebase. Every call
  site migrates; no alias preserved. Same shape as the
  `agent-config-editor` plan's renames.
- **`system-definitions-are-localized`** — each provider's model
  declaration lives with its provider class file.
- **`no-unnecessary-duplication`** — the validation pattern from
  `agent-config-editor` T03 (the per-provider check that landed for
  `reasoning_effort`) is reused for `model`. Don't reinvent it.
- **`prefer-public-surfaces`** — dashboard consumes the schema via
  `GET /providers`; backend consumes provider classes through their
  classmethods.
- **`seams-must-be-tested`** — the validation seam (model declared,
  agent saves with invalid model, save rejected) is exercised by at
  least one test per declaring provider.
- **`do-not-assume-backwards-compatibility`** — Always. Anyone with
  an agent currently carrying a `model` outside its provider's new
  authoritative list has to update; no compat fallback (current
  check: no live agents have `model` set, so migration is a no-op).

## Criteria acceptance

After implementation, evaluate the pending changes against the criteria
catalog. No criteria applicable to the completed diff may be violated.

## Tasks

### T01 — Rename `suggested_models()` → `supported_models()` and tighten semantics

- owner_role: developer
- dispatch_mode: handoff
- depends_on: []
- deliverables:
  - rename the classmethod on `BaseProvider` from `suggested_models`
    to `supported_models` (drop "suggested" language; the new
    semantics are authoritative)
  - make `BaseProvider.supported_models()` abstract (raises
    `NotImplementedError`) so concrete providers MUST implement it;
    no None / empty defaults — every provider declares a non-empty
    tuple
  - update the docstring on `BaseProvider.supported_models()` to
    state the new contract: "Return the non-empty tuple of model
    names this provider accepts. Every concrete provider must
    declare a real list — the dashboard never falls back to free
    text. Declared values are validated at agent save time."
  - update `ClaudeCodeProvider.suggested_models` → `supported_models`
    accordingly (the existing list stays as-is; it becomes
    authoritative)
  - update `ProviderManager.list_provider_schemas()` and the
    `ProviderSchema` dataclass field name + every test referencing
    the old name
  - update `GET /providers` response model field name and any tests
    asserting on it
  - update the dashboard's TypeScript types in `web/src/api.ts` to
    use `supported_models` (regenerated or hand-edited consistently)
  - update the schema fetcher hook + the structured form's
    consumption of the field name
  - `grep -rn "suggested_models" .` returns no hits after the
    rename (in source, tests, or docs)
- acceptance:
  - the rename is consistent across backend, API response, frontend
    types, and tests
  - claude_code's declared list is unchanged (still
    `("claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5")`
    or whatever it currently has)
  - the full test suite passes (backend + web)
  - no backwards-compatibility layer introduced (no alias, no
    deprecation shim)
  - criteria catalog applied

### T02 — Audit and declare per-provider supported models

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - audit each provider's CLI for its actual model namespace, using
    the same empirical approach as `provider-capability-audit` T01-T02
    (run the CLI with an invalid model, capture the rejection's enum
    if any)
  - for `codex`: extract its model enum if the validator has one;
    otherwise declare a curated set of common GPT-5-family models
    based on codex 0.130.0's documented support
  - for `gemini_cli`: declare a curated list of Google's documented
    Gemini CLI models
  - for `q_cli`, `kiro_cli`, `kimi_cli`, `copilot_cli`: audit each
    CLI's accepted models or backend's documented models. Every
    provider gets a real non-empty list — if extraction fails AND no
    documented set is available, escalate rather than declaring None
    or empty.
  - record the audit findings per provider in the commit message
    (where the value came from, whether it's an authoritative
    enumeration or a curated recommendation, the provider CLI
    version at audit time)
  - update each provider's unit test to pin its declared values
- acceptance:
  - every provider's `supported_models()` returns a non-empty tuple
    (no None, no `()`)
  - the audit covers all seven providers (`q_cli`, `kiro_cli`,
    `claude_code`, `codex`, `kimi_cli`, `gemini_cli`, `copilot_cli`)
  - each declared value is exercised through a test that confirms
    the launch path (or its closest seam) doesn't reject it
  - a unit test on the base `Provider` interface confirms calling
    `supported_models()` on the abstract base raises (so any future
    provider that forgets to implement it fails loudly at class
    instantiation, not silently at dashboard render time)
  - no backwards-compatibility layer introduced
  - criteria catalog applied

### T03 — Save-time validation for `model`

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- deliverables:
  - `PUT /agents/{id}` rejects requests where `model` is set and the
    selected provider's `supported_models()` doesn't include the
    submitted value (400 with field-level detail naming the
    offending value and the provider)
  - `PUT /agents/{id}` accepts a `model` value that is in the
    selected provider's `supported_models()` tuple
  - `PUT /agents/{id}` with `model` unset succeeds regardless of
    provider (the field stays optional in the dataclass; the
    dashboard always picks a value, but raw TOML edits or migration
    artifacts may legitimately leave it unset)
  - validation happens at the agent dataclass / service layer, not
    only in the HTTP handler — direct calls to the agent writer can't
    bypass it
  - unit and integration tests covering: valid model for each
    provider, invalid model for each provider, model unset entirely
- acceptance:
  - a `PUT` setting `model = "bogus-model"` on a claude_code agent
    returns 400 naming both the value and the supported set
  - a `PUT` with model unset succeeds regardless of provider
  - validation cannot be bypassed by going through the service or
    dataclass layer directly
  - no backwards-compatibility layer introduced
  - criteria catalog applied

### T04 — Dashboard: strict dropdown for `model`

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- deliverables:
  - the structured form's `model` field renders as a strict
    `<select>` dropdown populated from the selected provider's
    `supported_models` tuple (always non-empty, always enabled)
  - free-text typing is no longer possible in the dropdown (the
    combobox affordance and the text-input fallback that's currently
    in place are both removed)
  - changing `cli_provider` updates the `model` dropdown's options
    without a save round-trip; if the previously-selected model
    isn't in the new provider's list, the field falls back to the
    new list's first entry (or is cleared, depending on what the
    raw-TOML merge expects)
  - inline error display surfaces backend validation errors against
    the offending field
  - component tests covering: dropdown populates from schema,
    selecting an option triggers state update, save sends the value,
    options update when provider changes, the dashboard never
    presents an empty dropdown for any provider
- acceptance:
  - selecting a claude_code agent shows a dropdown with claude_code's
    supported models; selecting a codex agent shows codex's; every
    provider's dropdown is populated and enabled
  - the dashboard does not allow saving a model outside the dropdown's
    options (no free-text path)
  - `grep -rn "claude-opus\|claude-sonnet\|gpt-5\|gemini-" web/src/components/agents-tab/` returns no hits inside option arrays — all model values come from the schema
  - no backwards-compatibility layer introduced
  - criteria catalog applied

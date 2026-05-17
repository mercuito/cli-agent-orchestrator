# Provider Capability Audit (Draft v1)

Status: draft

This plan fixes a flawed premise that landed with `agent-config-editor`.
The original plan claimed "only `claude_code` reads `reasoning_effort`"
and instructed every other provider to declare `supported_reasoning_efforts`
as None. Reality, surfaced when the implementing subagent encountered it:
`codex` was also reading `agent.reasoning_effort` (via the `codex_home`
launch path's fallback to `codex_config.model_reasoning_effort`).

The subagent resolved the contradiction by deleting the fallback path,
which is internally consistent with the plan as written but defeats the
plan's actual design intent: **providers advertise the valid values they
support, the dashboard populates dropdowns from those declarations, and
the launch path consumes whatever the agent declares**.

This follow-up restores that design intent for every provider.

---

## Locked design

Every provider's launch path is audited to determine what
`reasoning_effort` values it actually accepts (if any) and what
`model` values are sensible suggestions. Each provider class then
declares its honest support:

- `supported_reasoning_efforts()` returns a tuple of the values its
  launch path accepts, or None when reasoning effort is genuinely not a
  meaningful concept for that provider.
- `suggested_models()` returns a tuple of common/recommended models, or
  None when the provider has no curated list to suggest.

The dashboard's structured form (from `agent-config-editor` plan)
already consumes these declarations — no frontend changes are needed
beyond what's required by the new declarations being honest.

Where a provider's launch path was reading `agent.reasoning_effort`
silently (the codex case), the launch path is restored and the
provider's `supported_reasoning_efforts` is updated to declare its
actual supported values.

### Provider-by-provider expected outcome

| Provider | `supported_reasoning_efforts` | Launch path |
|---|---|---|
| `claude_code` | `("low", "medium", "high")` (already declared) | reads `agent.reasoning_effort`, passes as `--effort <value>` |
| `codex` | the actual codex effort enum (likely `("minimal", "low", "medium", "high")` — verify against codex CLI) | restored: `agent.reasoning_effort` flows into `codex_config.model_reasoning_effort` when the latter is unset |
| Others (`q_cli`, `kiro_cli`, `gemini_cli`, `kimi_cli`, `copilot_cli`) | audit; declare honestly. Default None if their launch path genuinely doesn't consume reasoning_effort. | unchanged |

For `suggested_models`, each provider is audited for sensible defaults:

- `claude_code` already has a list (Opus 4.7, Sonnet 4.6, Haiku 4.5).
- Other providers: audit and declare a short list of common/recommended
  models per provider, or leave None if there's no good curated list.

## Goals

- Every provider's capability declarations match what its launch path
  actually consumes.
- The `codex_home` fallback that flows `agent.reasoning_effort` into
  `codex_config.model_reasoning_effort` is restored.
- Tests deleted during the previous resolution are restored or replaced
  with tests covering the corrected behavior.
- Dashboard dropdowns for `reasoning_effort` and `model` populate
  correctly for every provider that supports them.

## Non-goals

- Reorganizing the provider capability surface (the classmethod shape
  established in `agent-config-editor` T01 stays as-is).
- Adding new fields to the capability surface beyond
  `supported_reasoning_efforts` and `suggested_models`.
- Changing the dashboard's structured form, schema fetcher, or save
  validation (those are correct as landed; this plan only updates the
  values each provider declares).
- Adding `tools`/`mcp_servers`/other capability declarations. Out of
  scope.

## Forbidden compatibility patterns

Inherits hard-cutover discipline. Forbidden in any task:

- Restoring the `codex_home` fallback behind a feature flag.
- Declaring `supported_reasoning_efforts` based on what "feels right"
  rather than what the provider's launch path actually accepts —
  audit reality first.
- Hardcoding model lists in the dashboard. Suggestions come from
  `suggested_models()` only.

## Criteria catalog (likely applicable)

The implementer must run `uv run python scripts/catalog_criteria.py`
and apply every entry whose `when` clause matches the actual diff.
Criteria identified as likely to shape this work:

- **`authoritative-sources-are-referenced-not-copied`** — central.
  Each provider's launch path is the authoritative source for what
  `reasoning_effort` values are valid; the capability declaration
  references that reality, not a guess.
- **`system-definitions-are-localized`** — each provider's capability
  lives with that provider's class, not in a shared registry.
- **`migration-discipline`** — restoring the deleted `codex_home`
  fallback is a corrective migration; the test that was deleted
  comes back (or is replaced with one covering the corrected
  behavior).
- **`do-not-assume-backwards-compatibility`** — Always. No silent
  fallbacks or compat shims; if a provider's declared support
  changes, agent files using the old shape have to migrate (none
  currently exist per a local audit).
- **`seams-must-be-tested`** — each provider's
  `supported_reasoning_efforts()` is a seam between declaration and
  launch path. Each declared value should be exercised in at least
  one test that confirms the launch path actually accepts it.
- **`no-test-only-production-seams`** — Always.

## Criteria acceptance

After implementation, evaluate the pending changes against the criteria
catalog. No criteria applicable to the completed diff may be violated.

## Tasks

### T01 — Audit each provider's reasoning_effort launch path

- owner_role: developer
- dispatch_mode: handoff
- depends_on: []
- deliverables:
  - read each provider's launch implementation in
    `src/cli_agent_orchestrator/providers/` and any associated
    launch utility (e.g. `utils/codex_home.py`) to determine
    whether and how it consumes `agent.reasoning_effort` or an
    equivalent
  - produce a brief audit note (can live in the PR description, no
    separate doc) summarizing per-provider findings: which providers
    consume reasoning_effort, what values are valid, and where the
    consumption happens
- acceptance:
  - the audit covers all seven providers in `ProviderType`
  - for each provider, the audit names the source-of-truth file/line
    where reasoning_effort is consumed (or confirms it isn't)
  - no backwards-compatibility layer introduced
  - criteria catalog applied

### T02 — Update each provider's capability declarations

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - each provider class in `src/cli_agent_orchestrator/providers/`
    overrides `supported_reasoning_efforts()` to declare the values
    its launch path accepts. Providers that genuinely don't consume
    `reasoning_effort` leave the default `None` from `BaseProvider`.
  - each provider class declares `suggested_models()` with a short
    list of common/recommended models, or leaves the default `None`
    when no curated list is appropriate. `claude_code` keeps its
    existing list.
  - unit tests per provider verifying the declared values
- acceptance:
  - `codex` declares its actual reasoning_effort enum (verify
    against codex CLI; likely `("minimal", "low", "medium", "high")`)
  - the launch path for each declaring provider actually accepts
    every declared value (covered by tests that exercise the
    declared value through the launch path or its closest seam)
  - the `/providers` endpoint reflects the updated declarations
  - no backwards-compatibility layer introduced
  - criteria catalog applied

### T03 — Restore the codex_home fallback path

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- deliverables:
  - `utils/codex_home.py` regains the behavior where
    `agent.reasoning_effort`, when set, flows into
    `codex_config.model_reasoning_effort` if that field is not
    already set in `codex_config`
  - the test deleted during the previous resolution
    (`test_prepare_codex_home_applies_reasoning_effort_when_not_overridden`)
    is restored, or replaced with a test that covers the same
    behavior contract under the new structure
  - the comment block at `codex_home.py:286-289` describing why the
    fallback was removed is updated or removed to match the
    restored behavior
- acceptance:
  - a codex agent with `reasoning_effort = "high"` and no
    `codex_config.model_reasoning_effort` produces a codex config
    with `model_reasoning_effort = "high"` at launch
  - a codex agent with both fields set keeps the
    `codex_config.model_reasoning_effort` value (explicit codex_config
    wins over agent-level reasoning_effort)
  - no backwards-compatibility layer introduced (the restored
    behavior is the new authoritative behavior, not a shim)
  - criteria catalog applied

### T04 — Verify dashboard behavior end-to-end

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02, T03]
- deliverables:
  - manual verification on a built dashboard
    (`cd web && npm run build`, hard-refresh the browser) that:
    - selecting a codex agent shows an enabled `reasoning_effort`
      dropdown with codex's actual supported values
    - selecting a claude_code agent shows an enabled dropdown with
      its values
    - selecting a provider whose `supported_reasoning_efforts` is
      genuinely None (e.g. one of `q_cli`/`kiro_cli`/...) shows the
      field disabled with the explanatory tooltip
  - if the verification reveals a frontend bug not covered by
    existing tests, file a follow-up rather than expanding scope
    here
- acceptance:
  - manual verification done; result recorded in the PR description
    or commit message
  - no backwards-compatibility layer introduced
  - criteria catalog applied

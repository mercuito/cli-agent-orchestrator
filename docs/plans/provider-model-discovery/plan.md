# Provider Model Discovery — Phase 1: Claude Code (Draft v1)

Status: implemented

This plan introduces **runtime model discovery** for CAO providers. Each
provider learns to query its underlying API for the currently-available
models and the per-model reasoning effort levels, instead of CAO carrying
static lists in source. Phase 1 scopes the work to `claude_code` only.
Phase 2 (codex) and Phase 3 (dashboard integration) build on the
contract this plan establishes.

This plan replaces an earlier draft (`model-dropdown-tightening`,
deleted) that proposed static per-provider tuples. That premise was
rejected: model IDs change frequently and CAO should not require a
source change every time Anthropic, OpenAI, etc. ship a new model.
The new shape: providers discover dynamically; the dashboard consumes
a fresh catalog.

---

## Locked design

- **Discovery contract is an opt-in capability, not a base method.**
  Providers that can discover their model catalog expose a
  `ModelDiscoveryCapability` (a `Protocol`) via a
  `model_discovery_capability()` classmethod, matching the existing
  `ProviderRuntimeStateCapability` pattern in the same file. Providers
  whose CLIs don't offer model selection (or have no way to enumerate
  models) simply don't expose the capability, and `ProviderManager`
  reports `None` for them. `BaseProvider` itself carries no
  `discover_catalog` method.
- **Catalog shape.** The capability's `discover_catalog()` returns a
  `ProviderCatalog`. Each `ProviderModel` carries its `id`,
  `display_name`, the `reasoning_efforts` it supports, and basic
  capability metadata. A provider that offers model selection but not
  effort levels returns an empty `reasoning_efforts` tuple per model.
- **Source of truth is the upstream API.** For `claude_code`, that is
  Anthropic's `GET /v1/models`, which exposes per-model
  `capabilities.effort.{low,medium,high,xhigh,max}` directly.
- **Filter is structural, not enumerated.** `claude_code` includes any
  model whose `id` matches `claude-*` and whose `capabilities.thinking`
  is supported. New Claude models roll in automatically; CAO never
  hardcodes a model ID.
- **Auth uses what the CLI uses.** Discovery reads the same credentials
  Claude Code uses (OAuth token from macOS keychain or
  `~/.claude/.credentials.json` on Linux/Windows). When the CLI is not
  logged in, discovery surfaces an explicit error — no static fallback.
- **No caching layer.** Each GET calls the capability fresh. The
  `/v1/models` endpoint is metadata (not billed, ~1-2s typical), and
  the dashboard fetches the catalog on tab mount — not in a poll
  loop — so a cache solves a hypothetical problem and introduces
  staleness. If multi-user usage later reveals real latency or
  rate-limit pressure, add caching then with measurements.
- **Per-model effort levels.** The catalog tracks effort levels at the
  model level. The reasoning-effort dropdown in the dashboard will
  eventually react to model selection. This plan stops before the
  dashboard work; the catalog shape supports it.
- **HTTP surface.** New endpoint `GET /providers/{name}/catalog`. No
  refresh endpoint — every GET is fresh. The existing `/providers`
  response and its `supported_reasoning_efforts` / `suggested_models`
  fields are left untouched in this phase; they stay load-bearing for
  the current dashboard until Phase 3 cuts them over.

## Goals

- `ClaudeCodeProvider.model_discovery_capability()` returns a
  `ClaudeModelDiscoveryCapability` whose `discover_catalog()` populates
  a `ProviderCatalog` from a live `GET /v1/models` call.
- The catalog reports every Claude model the user's account can access,
  with the correct per-model effort levels (closing the bug that the
  current static `("low","medium","high")` tuple under-declares `xhigh`
  and `max`).
- A new `GET /providers/claude_code/catalog` endpoint surfaces the
  catalog to API clients. Each request hits the live API; no cache.
- Failure modes (not logged in, network down, routing not supported) are
  reported with actionable detail and never silently fall back to a
  static list.

## Non-goals

- Codex implementation (deferred to Phase 2).
- Other providers (deferred to subsequent phases).
- Dashboard UX changes — strict dropdown, reactive effort dropdown,
  removal of `suggested_models`/`supported_reasoning_efforts` from the
  schema (deferred to Phase 3).
- Save-time validation against the catalog (deferred to Phase 3, when
  the dashboard uses the catalog end-to-end).
- Bedrock / Vertex / Foundry routing for `claude_code`. If discovery
  detects the user has these enabled (via env vars
  `CLAUDE_CODE_USE_BEDROCK` / `CLAUDE_CODE_USE_VERTEX` /
  `CLAUDE_CODE_USE_FOUNDRY`), discovery raises an explicit
  "routed-auth not supported" error. Adding routed-auth discovery is a
  later plan.
- Any caching of the catalog. Phase 1 calls discovery fresh on every
  request. Revisit only with evidence of real latency or rate-limit
  pressure.
- Other `capabilities.*` fields beyond effort levels and thinking
  support (e.g. `image_input`, `pdf_input`, `structured_outputs`,
  `code_execution`). The catalog dataclass leaves room for them but
  Phase 1 only populates effort + thinking-supported.

## Forbidden compatibility patterns

Inherits CAO's hard-cutover discipline. Forbidden in any task in this
plan:

- Hardcoding any model ID anywhere — in `claude_code.py`, in tests,
  in fixtures, in the dashboard. Tests pin against capability shape
  ("at least one model with `id` matching `claude-*` and effort
  support"), not literal model IDs.
- Static fallback when discovery fails. Errors propagate; CAO does
  not pretend to know the list.
- Mocking the Anthropic API in unit tests. Per
  `target-behavior-must-not-be-mocked`, at least one integration test
  must exercise the real `/v1/models` endpoint. Parsing/filtering
  helpers may be unit-tested against recorded JSON fixtures.
- Shipping `ProviderCatalog` / `ProviderModel` alongside a parallel
  catalog shape elsewhere. One catalog data model, owned by
  `providers/base.py`.

## Criteria catalog (likely applicable)

The implementer must run `uv run python scripts/catalog_criteria.py`
and apply every entry whose `when` clause matches the actual diff.
Criteria likely to shape this work:

- **`authoritative-sources-are-referenced-not-copied`** — the model
  list comes from the upstream API at runtime. Filter rules are
  structural patterns, not copied literals.
- **`prefer-public-surfaces`** — discovery uses Anthropic's documented
  `/v1/models` endpoint and the documented credential file paths /
  keychain entry. Don't reach into internal CLI state.
- **`system-definitions-are-localized`** — Claude-specific credential
  resolution and API call live in or beside `providers/claude_code.py`
  (or `utils/claude_runtime.py` if reuse with existing helpers makes
  sense). The base contract is provider-agnostic.
- **`no-global-state-reads`** — credential reading is an explicit
  step inside `discover_catalog()`, not implicit env-var snooping at
  module import. Routed-auth detection reads env vars at the call
  site, not eagerly.
- **`deep-systems`** — no caching layer. Every GET hits the live
  API. Add caching only with evidence it's needed.
- **`do-not-assume-backwards-compatibility`** — when Phase 3 lands and
  the static `supported_reasoning_efforts` / `suggested_models` are
  removed, no shim is preserved. This plan adds the new surface
  alongside the old without coupling them.
- **`target-behavior-must-not-be-mocked`** — at least one test calls
  the real Anthropic API. Helper-level parsing can use recorded
  fixtures.
- **`seams-must-be-tested`** — the discovery seam (credentials →
  API call → filter → catalog) is exercised end-to-end. Each failure
  mode has its own test (not logged in, routed-auth detected, network
  failure).
- **`test-through-owner-surfaces`** — tests assert against the
  catalog's public shape (its dataclass fields), not against the raw
  Anthropic API response.

## Criteria acceptance

After implementation, evaluate the pending changes against the criteria
catalog. No criteria applicable to the completed diff may be violated.

---

## Tasks

### T01 — Catalog contract: dataclasses, exception, and capability Protocol

- owner_role: developer
- dispatch_mode: handoff
- depends_on: []
- deliverables:
  - new module-level dataclasses in `providers/base.py`:
    - `ProviderModel` — frozen dataclass with fields `id: str`,
      `display_name: str`, `reasoning_efforts: tuple[str, ...]`,
      `thinking_supported: bool`, `max_input_tokens: int | None`,
      `max_output_tokens: int | None`. Fields beyond effort/thinking
      are populated when easily available; `None` when unknown.
    - `ProviderCatalog` — frozen dataclass with fields
      `provider_type: str`, `models: tuple[ProviderModel, ...]`,
      `discovered_at: datetime`, `source: str` (free-form, e.g.
      `"anthropic-api"` for traceability).
  - new exception `CatalogDiscoveryError(Exception)` in
    `providers/base.py`. Plain message-only exception; no error
    code field. Callers raise it with a human-readable string.
  - new `ModelDiscoveryCapability(Protocol)` in `providers/base.py`
    declaring a single `discover_catalog(self) -> ProviderCatalog`
    method. Docstring states the implementation must not cache
    (caching lives at the manager) and may raise
    `CatalogDiscoveryError`.
  - **no method on `BaseProvider`.** Providers opt in by exposing a
    `model_discovery_capability()` classmethod returning a concrete
    implementation of the protocol. Providers without the capability
    simply don't expose that classmethod. This matches the existing
    `runtime_state_capability` pattern.
  - leave `supported_reasoning_efforts()` and `suggested_models()`
    classmethods untouched (Phase 3 removes them as part of the
    dashboard cutover).
  - unit tests:
    - `ProviderCatalog` and `ProviderModel` are frozen and reject
      mutation.
    - `ProviderModel` is hashable.
    - `CatalogDiscoveryError` carries the message.
    - A stub class implementing `discover_catalog()` structurally
      satisfies the protocol (assignment to a
      `ModelDiscoveryCapability`-typed slot succeeds and the
      returned catalog round-trips).
    - `BaseProvider` does NOT have a `discover_catalog` attribute
      (verifies the opt-in shape is preserved against accidental
      re-introduction).
- acceptance:
  - public surface compiles and the new types import cleanly from
    `providers.base`.
  - no existing test breaks.
  - criteria catalog applied.

### T02 — `ClaudeModelDiscoveryCapability` implementation

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- spike findings (already verified in conversation, summarized here so
  the task is self-contained):
  - `security find-generic-password -s "Claude Code-credentials" -a "$USER" -w`
    returns the OAuth credential JSON non-interactively on macOS.
    Shape: `{"claudeAiOauth": {"accessToken", "refreshToken",
    "expiresAt", "subscriptionType", "rateLimitTier"}, ...}`. May
    still require a one-time ACL grant for the cao-server binary
    path; verify when wiring through to a running cao-server.
  - `GET https://api.anthropic.com/v1/models` accepts both
    `Authorization: Bearer <accessToken>` and `X-Api-Key:
    <accessToken>` with HTTP 200. Use the Bearer form to keep the
    semantics honest (this is an OAuth token, not an API key).
  - The current static `("low","medium","high")` tuple under-declares
    `max` for the frontier models (`claude-opus-4-7`,
    `claude-sonnet-4-6`, `claude-opus-4-6`) and over-declares
    effort for models that report empty effort sub-flags (haiku-4-5,
    older 4-5 / 4-1 / 4 dated builds). Per-model effort is correct.
- deliverables:
  - new concrete class `ClaudeModelDiscoveryCapability` in
    `providers/claude_code.py` (alongside `ClaudeRuntimeStateCapability`)
    implementing the `ModelDiscoveryCapability` protocol.
  - new classmethod
    `ClaudeCodeProvider.model_discovery_capability()` returning a
    `ClaudeModelDiscoveryCapability()` instance, mirroring the
    existing `runtime_state_capability()` classmethod.
  - inline keychain read (macOS only) inside `claude_code.py`: read
    `security find-generic-password -s "Claude Code-credentials"
    -a "$USER" -w`, parse JSON, return
    `claudeAiOauth.accessToken`. No separate credential resolver
    module. On non-macOS or any failure, return None and the
    capability raises `CatalogDiscoveryError("...not found...")`.
  - single `GET https://api.anthropic.com/v1/models` request with
    `anthropic-version: 2023-06-01` and `Authorization: Bearer
    <token>`. No pagination loop — the response is a handful of
    models with `has_more=false` in practice. Non-200 or non-JSON
    raises `CatalogDiscoveryError` with the upstream status / error.
    10s timeout.
  - filter / mapping:
    - keep models where `id.startswith("claude-")` AND
      `capabilities.thinking.supported is True`
    - for each kept model, extract `reasoning_efforts` from
      `capabilities.effort.{low,medium,high,xhigh,max}` by walking the
      sub-supported flags
    - map `display_name`, `max_input_tokens`, `max_tokens` →
      `max_output_tokens`
  - return a `ProviderCatalog` with `source="anthropic-api"` and
    `discovered_at=datetime.now(tz=timezone.utc)`
  - tests:
    - **integration**: a real `GET /v1/models` call against the
      developer's logged-in Claude Code credentials, asserting the
      returned catalog is non-empty. Marked `@pytest.mark.integration`
      and gated with `pytest.skip` when the keychain read returns
      None so CI without creds skips automatically.
    - **parsing**: unit tests against a recorded `/v1/models` JSON
      fixture plus a few constructed dicts that confirm the filter
      rule (non-claude prefix dropped; thinking-unsupported dropped;
      thinking-supported but empty effort sub-flags kept with
      `reasoning_efforts=()`).
    - **failure modes**: one test for "no credentials" and one for
      non-200 response. No need to enumerate every HTTP status; the
      single `CatalogDiscoveryError` carries the upstream detail.
- acceptance:
  - on a logged-in Claude Code installation, calling
    `ClaudeCodeProvider.model_discovery_capability().discover_catalog()`
    returns a non-empty catalog within ~2s.
  - no Claude model IDs appear as string literals in source files
    (verify with `grep -rn "claude-opus\|claude-sonnet\|claude-haiku" src/`).
  - the integration test runs locally (it may skip in CI per the
    marker decision).
  - criteria catalog applied.

### T03 — HTTP surface

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- design note: no caching layer, no manager-level wrapper. The HTTP
  handler resolves the capability directly via `getattr` on the
  provider class — the `ModelDiscoveryCapability` protocol IS the
  declaration of support.
- deliverables:
  - new Pydantic response models in `api/main.py`:
    - `ProviderModelResponse` mirroring `ProviderModel`
    - `ProviderCatalogResponse` mirroring `ProviderCatalog`,
      including ISO 8601 `discovered_at`
  - new endpoint
    `GET /providers/{provider_type}/catalog -> ProviderCatalogResponse`:
    - looks up the provider class through whatever public surface
      `ProviderManager` exposes (or a thin new accessor if the
      existing `_provider_class` is private — pick the smaller of:
      promote `_provider_class` to public, or add a one-line
      `provider_class(provider_type)` method)
    - unknown `provider_type` → 404
    - `getattr(provider_cls, "model_discovery_capability", None)`;
      if `None`, return 404 with a body indicating the provider has
      no model-discovery capability
    - call `capability().discover_catalog()` and return the result
    - on `CatalogDiscoveryError`, return HTTP 503 with the error
      message in `detail`
  - tests in `test/api/`:
    - happy-path GET that exercises the capability against the
      recorded `/v1/models` fixture from T02. Patches `requests.get`
      at the `cli_agent_orchestrator.providers.claude_code` seam.
    - 503 when keychain read returns None (no credentials).
    - 404 for unknown `provider_type`.
    - 404 for a provider that doesn't expose the
      `model_discovery_capability` classmethod.
- acceptance:
  - curling `GET /providers/claude_code/catalog` against a running
    cao-server on a logged-in macOS machine returns a populated
    catalog with each model's per-model effort levels.
  - criteria catalog applied.

---

## Open item

**cao-server binary keychain ACL.** The spike confirmed
`security find-generic-password` works non-interactively from a regular
shell. Different binaries can have different keychain ACLs on macOS,
so the first time T02 runs against an actual cao-server process (not a
direct test invocation) we may discover the keychain prompts. If it
does, decide in T02:

- one-time ACL grant for the cao-server binary path (documented in
  [`docs/claude-code.md`](../../claude-code.md)), or
- `ANTHROPIC_API_KEY` env-var fallback for headless / non-interactive
  contexts

This is not a plan-blocker; it's a wiring detail surfaced during T02.

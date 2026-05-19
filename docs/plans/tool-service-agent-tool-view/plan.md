# Tool Service Agent Tool View

Status: draft

## Goal

Move dashboard-facing agent tool metadata and effective-access answers behind
`ToolService`, so API routes ask the service for tool information instead of
rebuilding provider/MCP tool metadata per request.

This plan follows the ownership model already established in
[`effective-tool-access-consolidation`](../effective-tool-access-consolidation/plan.md):
`ToolService` is the owner of tool catalogs, provider-mediated tool policy,
MCP tool surface decisions, and effective access decisions. The immediate
performance problem is `/agents`, but the fix must be an ownership correction,
not a scattered cache.

## Problem

The dashboard calls `/agents` to render agent roster/detail surfaces. Each
agent response currently includes:

- normal durable/runtime agent status;
- `mcp_tool_surface`, the tools visible to that agent;
- `effective_tool_access`, the allowed/blocked tools and source diagnostics for
  that agent.

The slow path appears when those tool fields are built. Provider/MCP metadata,
especially Linear provider tool metadata and runtime freshness material, is
assembled repeatedly while serving one dashboard request. A lower-level source
inspection cache can reduce repeated `inspect.getsource` work, but that is only
a symptom fix. The correct boundary is for `ToolService` to own the assembled
tool view and expose it through a public API.

## Target Ownership

`ToolService` should answer dashboard/API questions about tools. API response
models should adapt service results; they should not reconstruct the tool
catalog, provider policies, MCP surface, or effective access directly.

Target public service shape:

```python
tool_service.agent_tool_view(agent)
```

or equivalent focused methods if the existing service shape makes that cleaner:

```python
tool_service.mcp_tool_surface_for_agent(agent)
tool_service.effective_tool_access_for_agent(agent)
tool_service.runtime_generation_fingerprint_for_agent(agent)
```

The exact method names may change during implementation, but the ownership must
not: consumers ask `ToolService`; they do not independently interpret tool
catalogs, provider grants, team roles, or MCP freshness inputs.

## Scope

In scope:

- backend service/API refactor for the `/agents` tool metadata hot path;
- service-owned in-memory reuse of expensive tool catalog/policy/runtime
  metadata;
- route/model updates needed for `/agents` and `/agents/{agent_id}` to consume
  the service-owned tool view;
- tests proving behavior, staleness, and ownership boundaries;
- profiling and served-dashboard verification after implementation;
- documentation of performance and review evidence.

Out of scope:

- changing the external `/agents` JSON response shape unless explicitly
  justified by the implementation and tests;
- caching agent lists, team membership, role grants, Linear issue/project data,
  or complete API responses;
- changing Linear provider semantics or adding provider-specific dashboard
  fields;
- broad migration of all `ToolService` consumers from the consolidation plan;
- unrelated frontend redesign work.

## Cache And Staleness Model

The service may cache or memoize derived data that is expensive and owned by
the tool subsystem:

- built-in CAO tool descriptors and runtime metadata;
- provider tool definitions and role-access schema;
- normalized provider policies;
- provider-mediated runtime generation material;
- per-agent tool view, only when keyed by all inputs that affect it.

The service must not blindly cache live authority data. These inputs must cause
the affected service result to recompute:

- agent config content relevant to tools, MCP servers, workspace, provider, and
  runtime capabilities;
- team membership and selected role for the agent;
- team role grants, including CAO tools, MCP servers, and provider grants;
- workspace setup/provider configuration;
- enabled/available provider set;
- built-in CAO tool registry changes;
- provider tool registry/source changes;
- runtime generation/source freshness changes.

Prefer a deterministic input fingerprint for the first implementation. It is
easier to test and safer than hidden lifecycle invalidation. Explicit
invalidation hooks may be introduced only if they make the implementation
simpler and are covered by tests for every write path that can change tool
answers.

Lower-level source introspection caches are allowed only as private
implementation details behind `ToolService`-owned public behavior. They must
not become the architectural answer to dashboard performance.

## Implementation Tasks

1. **Map the current `/agents` hot path.** Identify every call made while
   building `AgentStatusResponse.mcp_tool_surface` and
   `AgentStatusResponse.effective_tool_access`, including provider policy,
   Linear tool metadata, MCP surface, and runtime generation calls.

2. **Define the service result shape.** Add or reuse a `ToolService` result
   that contains the data the API needs for `mcp_tool_surface` and
   `effective_tool_access`. Keep route response models as adapters from this
   owner result.

3. **Move construction behind `ToolService`.** Replace API/model-level
   rebuilding with calls into the public `ToolService` surface. Avoid route
   code reaching into provider internals, MCP server internals, or freshness
   internals.

4. **Add service-owned reuse.** Memoize static or input-fingerprinted derived
   data in `ToolService`, not in API routes. The implementation must document
   what is reused and what inputs invalidate it.

5. **Preserve behavior.** `/agents` and `/agents/{agent_id}` must continue to
   return the same tool fields and diagnostics for existing scenarios unless a
   deliberate response-shape change is called out and tested.

6. **Handle staleness.** Add tests that demonstrate recomputation when relevant
   inputs change: at minimum team role grants, agent workspace/team assignment,
   provider availability or provider policy content, and source/runtime
   freshness token changes.

7. **Remove the wrong abstraction if superseded.** If a lower-level
   `mcp_server.freshness` cache was added only as a hot-path bandage, either
   remove it or reduce it to a clearly private helper whose correctness is
   covered by service-level tests.

8. **Profile and verify.** Re-profile the response-build path and time served
   endpoints after restarting the dashboard server. Verify the served
   dashboard, not only unit tests, so the result reflects user-visible load
   behavior.

9. **Document completion evidence.** Create
   `docs/plans/tool-service-agent-tool-view/completion-report.md` with commands,
   tests, profiling before/after, served URL, browser used, staleness checks,
   criteria catalog judgments, and review-loop evidence.

## Test Strategy

Use tests at the owner boundary first:

- `ToolService` tests for same-input reuse of expensive provider/tool metadata.
- `ToolService` tests for recomputation after each relevant input changes.
- API route tests proving `/agents` and `/agents/{agent_id}` still expose the
  expected `mcp_tool_surface` and `effective_tool_access` fields.
- Regression tests for Linear provider-mediated tools because they were the
  observed expensive path.
- A focused performance test or profiling script recorded in the completion
  report. It does not need to be a brittle timing assertion in CI, but the
  evidence must be reproducible.

Tests must use owner surfaces for setup wherever practical. Do not seed private
provider/tool internals unless there is no public owner surface; any exception
must be documented in the test.

## Criteria Catalog

Catalog command used while drafting this plan:

```bash
uv run python scripts/catalog_criteria.py --format json
```

Likely implementation criteria to consult during implementation:

- `migration-discipline`
- `minimal-cohesive-changes`
- `no-test-only-production-seams`
- `no-unnecessary-duplication`
- `parallel-safe-execution`
- `prefer-public-surfaces`
- `properly-designed-shared-code`
- `readable-and-explicit`
- `simple-systems`
- `system-code-locality`
- `system-definitions-are-localized`

Likely test criteria to consult during implementation:

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
- `ui-changes-require-real-browser-verification` if any frontend or served
  static dashboard behavior changes.

After implementation, evaluate the pending changes against the criteria
catalog. No criteria applicable to the completed diff may be violated.

## Definition Of Done

- The plan's ownership model is implemented: `/agents` and
  `/agents/{agent_id}` consume a public `ToolService` tool-view/access surface.
- API routes and response models no longer independently rebuild provider/MCP
  tool metadata when a service-owned answer is available.
- `ToolService` owns any in-memory reuse for tool catalog, provider policy,
  runtime generation, and per-agent tool view data.
- The implementation documents, in code or completion report, exactly what is
  reused and which inputs invalidate it.
- Live authority data is not cached blindly: agent config, team membership,
  role grants, workspace setup/provider state, provider availability, and
  runtime/source freshness changes recompute affected answers.
- Existing `/agents` and `/agents/{agent_id}` response behavior is preserved or
  any deliberate response-shape change is explicitly documented and tested.
- Tests cover same-input reuse and recomputation on changed inputs through
  service-owned/public surfaces.
- Tests cover the API route shape for both list and single-agent routes.
- Any lower-level freshness/source cache left in place is justified as a
  private helper and covered by tests that prove it cannot create stale tool
  authority answers.
- The served dashboard is restarted and verified against the built/current code.
- The completion report records commands, tests, profiling before/after,
  served URL, browser used, staleness checks, and criteria judgments.
- A fresh-context review loop is completed after implementation. Reviewers must
  inspect the implementation, this plan, the completion report, and the agreed
  acceptance criteria.
- If a reviewer reports a valid issue, the issue is verified, fixed,
  documented in the completion report, and the review loop restarts.
- Completion requires two successive fresh-context reviews with zero valid
  findings.


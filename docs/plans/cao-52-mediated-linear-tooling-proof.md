# CAO-52 Mediated Linear Tooling Proof

## Source

Linear issue CAO-52 and its 2026-05-09 implementation-plan refinement comment.
The refinement scopes this slice to an automated vertical proof using the
existing fake tmux runtime provider, real Linear presence/runtime delivery,
real provider-mediated MCP registration/invocation, and fake Linear GraphQL
transport only at the external API boundary.

## Scope

- Extend `test/integration/test_agent_runtime_provider_state.py`.
- Start from a Linear-style `AgentSessionEvent` routed through
  the typed Linear workspace provider event publisher and
  `linear_runtime.notify_agent_for_persisted_event`.
- Use `LinearWorkspaceProvider` config to map the Linear presence to the CAO
  identity and grant that same identity all landed CAO-mediated Linear tools.
- After runtime delivery, register tools for the resulting terminal with
  `register_provider_mediated_mcp_tools` and the real Linear provider access
  policy. This lower-level registration function is the assigned owner surface
  named by CAO-52's latest refinement; production startup loading through
  `register_provider_mediated_mcp_tools_for_terminal` is covered by existing
  provider-mediated registration tests and is not expanded in this slice.
- Through FastMCP, prove the delivered terminal can invoke:
  `cao_linear.get_issue`, `cao_linear.list_comments`,
  `cao_linear.create_comment`, `cao_linear.create_issue`, and
  `cao_linear.update_issue`.
- Prove a raw/unmapped terminal cannot register or invoke those tools.
- Preserve compact-message assertions: exact user prompt body, sender presence,
  useful breadcrumb context, and no `promptContext` dump as message body.

Out of scope:

- Production behavior changes.
- Live Linear mutation or live Linear smoke tests.
- Real Codex/Claude/LLM turns.
- Linear monitor or reconciliation behavior.

## Selected Criteria

Coding code criteria:

- `full-verification-required`: CAO-52 produces code/test changes and requires
  focused plus broader verification.
- `minimal-cohesive-changes`: the change should remain a narrow proof around
  the existing runtime/provider-mediated surfaces.
- `no-unnecessary-duplication`: local fake payloads should model only external
  Linear GraphQL shapes and avoid copying production handler behavior.
- `respect-ownership-boundaries`: runtime delivery, Linear config/policy, MCP
  registration, and invocation should each be exercised through their owning
  surfaces.
- `readable-and-explicit`: the scenario uses authored payload/config/tool
  inputs visible from the test.
- `respect-standing-decisions`: CAO-52 explicitly requires no raw Linear access
  and no real LLM/token-burning turn.
- `prefer-public-surfaces`: the test uses `LinearWorkspaceProvider`,
  Linear typed workspace provider events,
  `linear_runtime.notify_agent_for_persisted_event`, FastMCP, and
  `register_provider_mediated_mcp_tools`.
- `no-test-only-production-seams`: no production seam is added for this test.
- `external-integration-testing`: the fake GraphQL boundary asserts operation
  names, variables, app key, access token, and provider-shaped payloads.

Coding test criteria:

- `test-validity-preserved`: existing runtime, Linear, and provider-mediated
  tests should remain valid.
- `verification-scope-discipline`: focused integration proof plus relevant
  Linear/provider-mediated subsets and full suite.
- `reusable-test-state`: extend the existing tmux runtime provider setup and
  Linear provider installer rather than creating a parallel harness.
- `test-through-owner-surfaces`: exercise real runtime delivery, real provider
  policy registration, and real MCP invocation.
- `real-surface-proof-discipline`: use tmux/database/FastMCP surfaces, faking
  only the external Linear GraphQL transport and no-token model CLI boundary.
- `given-when-then-test-structure`: keep the vertical test auditable despite
  several steps.
- `inspectable-authored-inputs`: keep the Linear payload, TOML grant, and tool
  arguments visible in the leaf test.
- `setup-invariant-ownership`: shared helpers own repeated valid setup; leaf
  assertions prove CAO-52 behavior.
- `test-artifact-containment`: all config, tmux sessions, database rows, and
  working directories remain scoped to test fixtures and cleanup.
- `public-boundary-proof`: the proof invokes the FastMCP tool boundary used by
  terminal clients.
- `external-integration-testing`: CAO-52 reuses the broader CAO-28/50/51
  negative/error matrix and adds the missing vertical proof.

## Behavioral Contract Defence

- Linear ingestion starts from a Linear-style `AgentSessionEvent`, publishes the
  typed Linear workspace provider event, persists the resulting inbox records,
  and calls `linear_runtime.notify_agent_for_persisted_event`.
- The fake tmux provider avoids a real model turn while still proving runtime
  restart/resume and terminal message delivery through tmux output.
- The delivered message body is exactly the authored user prompt. The sender is
  `presence`; terminal output includes actor and issue breadcrumb context; the
  large `promptContext` text is not delivered as the prompt body.
- The resulting refreshed terminal id is used for provider-mediated MCP
  registration. The Linear policy comes from `LinearWorkspaceProvider` and the
  real `LinearToolProvider` access policy.
- FastMCP calls run through `ProviderMediatedMCPTool` and
  `ProviderMediatedToolInvocationService`; the fake GraphQL function is only
  the external Linear API boundary.
- The five landed Linear tools are all registered and invoked from the mapped
  terminal.
- A raw terminal row with no `agent_identity_id` registers no Linear tools and
  FastMCP reports the Linear tool as unavailable.
- No production behavior was changed.

## Test Contract Defence

- Focused proof:
  `test_linear_agent_session_terminal_uses_provider_mediated_linear_mcp_tools`.
- Existing compact-message proof:
  `test_linear_agent_session_prompt_survives_stale_refresh_with_exact_body`
  remains intact and the CAO-52 test repeats the required compact assertions
  for the vertical MCP proof.
- Existing owner-surface coverage reused by this slice:
  `test/integration/test_provider_mediated_contract.py`,
  `test/mcp_server/test_provider_tool_registration.py`,
  `test/workspace_providers/test_provider_tool_invocation.py`, and
  `test/linear/test_provider_tools.py`.
- Existing CAO-28/50/51 tests retain detailed negative/error coverage for
  unauthorized issues, wrong-provider refs, malformed input, credentials, and
  Linear API failures. CAO-52 adds the previously missing end-to-end connection
  between Linear event delivery and CAO-mediated Linear MCP access.

## Reviewer Outcomes

- Correctness reviewer found no behavioral defect, but requested a persisted
  defence. This document records the behavioral defence.
- Implementation-criteria reviewer found `isort` failing. Import ordering was
  corrected with `uv run isort`.
- Test-contract reviewer requested a persisted Test Contract Defence and either
  production-startup registration proof or explicit scoping to the lower-level
  registration owner surface. This document records that CAO-52's refinement
  explicitly names `register_provider_mediated_mcp_tools` for this proof; no
  production-startup expansion is included.

## Verification Results

- `uv run pytest test/integration/test_agent_runtime_provider_state.py -q`
  passed: 3 tests.
- `uv run pytest test/integration/test_provider_mediated_contract.py test/mcp_server/test_provider_tool_registration.py test/workspace_providers/test_provider_tool_invocation.py test/linear/test_provider_tools.py -q`
  passed: 92 tests.
- `uv run pytest test/linear test/runtime/test_agent_runtime.py test/presence/test_provider_manager.py test/services/test_linear_agent_runtime_service.py -q`
  passed: 172 tests.
- `uv run pytest -q` passed: 1969 passed, 16 skipped, 76 deselected,
  3 warnings.

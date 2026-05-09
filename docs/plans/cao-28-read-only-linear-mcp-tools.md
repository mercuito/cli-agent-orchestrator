# CAO-28 Read-Only Linear MCP Tools

## CAO-28 Feature Task Handoff

Source of truth: Linear issue CAO-28.

Scope:

- Add only read-only CAO-mediated Linear MCP tools:
  `cao_linear.get_issue` and `cao_linear.list_comments`.
- Register tools only for identity-managed CAO terminals whose agent identity
  has explicit Linear tool access.
- Reject raw terminals, unmapped identities, identities without tool access,
  profile grants whose matching identities lack Linear presence,
  unavailable/malformed provider config, unauthorized Linear targets, missing
  credentials, expired credentials, inaccessible issues, archived issues, and
  Linear API failures before returning Linear data.
- Keep Linear-specific vocabulary, API queries, and read policy in the Linear
  workspace provider area.
- Preserve existing built-in CAO MCP behavior and provider-mediated framework
  behavior.

Out of scope:

- Linear mutations.
- Raw Linear MCP passthrough.
- Arbitrary user Python hooks.
- CAO-50, CAO-51, CAO-52, and CAO-30.

## Committed Implementation Decisions

- Linear read access is provider-owned configuration in `linear.toml` under
  `[tool_access.<name>]`.
- A tool access entry grants a read tool to exactly one `agent_id` or
  `agent_profile` and a bounded list of authorized Linear issue ids or
  identifiers.
- `issue_ref.provider` must be `linear` when a provider-owned reference is
  used.
- Authorized targets are checked before GraphQL and checked again against the
  returned issue id or identifier.
- Linear OAuth presence and credential checks happen before GraphQL.
- Returned issue/comment payloads are compact, stable, text-oriented, and
  bounded.
- Provider pre-call denials include the provider-specific reason in the MCP
  error text while preserving the existing denial reason field.

## CAO-28 Coding Implementation Plan

1. Read CAO-28, current provider-mediated MCP surfaces, Linear workspace
   provider code, and relevant criteria.
2. Add a Linear provider tool module that exposes normalized CAO tools,
   performs read-policy checks, maps Linear GraphQL responses, and translates
   Linear/OAuth failures into distinct CAO diagnostics.
3. Extend the Linear workspace provider to parse, validate, expose, and
   preserve `tool_access` configuration.
4. Preserve provider-mediated registration behavior by initializing Linear read
   policies only when `tool_access` exists.
5. Add focused owner/public-surface tests for registration, authorization,
   successful reads, denial paths, provider/API failures, payload bounds, and
   config preservation.
6. Run formatting, type checking, focused tests, and the full suite.
7. Dispatch reviewer agents and address grounded findings.

## Selected Criteria

Coding code criteria:

- `full-verification-required`: CAO-28 touches provider-mediated MCP behavior,
  Linear provider config, and error propagation, so focused and broad proof are
  required.
- `minimal-cohesive-changes`: the slice is limited to CAO-28 read-only tools
  and the provider-mediated registration hook needed to preserve existing
  behavior.
- `no-unnecessary-duplication`: shared tool access parsing and payload helpers
  keep policy and shaping logic centralized.
- `respect-ownership-boundaries`: Linear vocabulary, GraphQL queries, OAuth
  credential handling, and target policy live under the Linear provider area.
- `readable-and-explicit`: failure mappings and payload shaping use named
  helpers instead of hidden dynamic behavior.
- `respect-standing-decisions`: implementation uses CAO-27 provider-mediated
  policy surfaces and does not bypass built-in CAO MCP behavior.
- `boundary-and-failure-testing`: denial and provider/API failure branches are
  explicit feature obligations.
- `centralized-vocabulary`: Linear tool names, provider name, policy hook name,
  and issue-reference vocabulary are centralized in the Linear tool module.
- `prefer-public-surfaces`: tests invoke FastMCP or
  `ProviderMediatedToolInvocationService` rather than private helpers.
- `red-green-refactor`: tests were added around missing behavior and extended
  after reviewer findings.
- `semantic-continuity`: existing provider-mediated authorization semantics are
  preserved while adding Linear-specific policy.
- `service-definition-surface`, `service-export-discipline`,
  `well-defined-service`: the Linear workspace provider exposes the provider
  tool access service without making CAO core know Linear API details.
- `external-integration-testing`: Linear GraphQL shape and auth assumptions are
  documented against official Linear GraphQL/API docs.
- `authored-document-edit-preservation`: saving Linear OAuth config preserves
  user-authored `tool_access` entries.

Coding test criteria:

- `test-validity-preserved`: existing Linear and provider-mediated tests still
  pass.
- `verification-scope-discipline`: focused Linear/provider-mediated subsets and
  the full suite were run.
- `reusable-test-state`: shared fixtures create Linear config, terminal
  metadata, provider instances, issue payloads, and MCP services.
- `test-through-owner-surfaces`: tests exercise registration and invocation
  through provider-owned public surfaces.
- `real-surface-proof-discipline`: tests call FastMCP and the invocation
  service rather than testing only pure helper functions.
- `public-boundary-proof`: authorization failures are asserted through MCP
  `ToolError` or public service errors.
- `given-when-then-test-structure`: tests describe setup/action/result at the
  behavioral boundary.
- `setup-invariant-ownership`: fixtures own identity, presence, credential, and
  tool access setup.
- `external-integration-testing`: mocked Linear responses mirror the official
  Linear GraphQL schema/docs surfaces used by production code.

## CAO-28 Coding Completion Report

Implemented files:

- `src/cli_agent_orchestrator/linear/provider_tools.py`
- `src/cli_agent_orchestrator/linear/workspace_provider.py`
- `src/cli_agent_orchestrator/workspace_providers/registry.py`
- `src/cli_agent_orchestrator/workspace_providers/invocation.py`
- `test/linear/test_provider_tools.py`
- `test/linear/test_workspace_provider.py`

Verification commands:

- `uv run isort --check-only src/cli_agent_orchestrator/linear/provider_tools.py src/cli_agent_orchestrator/linear/workspace_provider.py src/cli_agent_orchestrator/workspace_providers/registry.py src/cli_agent_orchestrator/workspace_providers/invocation.py test/linear/test_provider_tools.py test/linear/test_workspace_provider.py`
- `uv run black --check src/cli_agent_orchestrator/linear/provider_tools.py src/cli_agent_orchestrator/linear/workspace_provider.py src/cli_agent_orchestrator/workspace_providers/registry.py src/cli_agent_orchestrator/workspace_providers/invocation.py test/linear/test_provider_tools.py test/linear/test_workspace_provider.py`
- `uv run mypy src/cli_agent_orchestrator/linear/provider_tools.py src/cli_agent_orchestrator/linear/workspace_provider.py src/cli_agent_orchestrator/workspace_providers/registry.py src/cli_agent_orchestrator/workspace_providers/invocation.py`
- `uv run pytest test/linear/test_provider_tools.py test/linear/test_workspace_provider.py test/workspace_providers test/mcp_server/test_provider_tool_registration.py test/integration/test_provider_mediated_contract.py -q`
- `uv run pytest -q`

## CAO-28 Behavioral Contract Defence

- Read-only tools are the only registered Linear MCP tools, and registration is
  identity-managed by provider-mediated CAO policy.
- Raw terminals, discovery terminals, missing terminals, unauthorized issues,
  wrong-provider refs, malformed config, profile grants without matching Linear
  presence, missing credentials, expired credentials, inaccessible issues,
  archived issues, and API failures are rejected through owner/public surfaces.
- Successful issue reads return stable issue identity, status, team, project,
  assignee, description preview, URL, and timestamps.
- Successful comment reads return stable issue identity and ordered, bounded,
  text-oriented comments with author and timestamps.
- Linear-specific API and policy logic stays in the Linear provider area; CAO
  core consumes normalized provider-mediated policies.

## CAO-28 Test Contract Defence

- Registration and authorization proof:
  `test_linear_read_tools_register_and_fetch_authorized_issue_context`,
  `test_linear_read_tools_fail_closed_at_registration_for_unauthorized_terminals`,
  and `test_linear_read_tools_reject_unauthorized_targets_before_graphql`.
- Read success proof:
  issue and comment payload assertions through FastMCP tool calls.
- Denial and provider/API failure proof:
  missing issue, archived issue, expired credentials, inaccessible issue,
  generic API failure, missing credentials before GraphQL, returned issue
  outside policy, profile grants without matching Linear presence, wrong
  provider refs, invalid limits, and malformed config.
- Bounds and ordering proof:
  deliberately unordered comment fixture, limit validation, and truncation
  assertions for long issue descriptions and comment bodies.
- Preservation proof:
  structured Linear OAuth token updates preserve `tool_access` entries.

## Review Readiness Command

```bash
uv run isort --check-only src/cli_agent_orchestrator/linear/provider_tools.py src/cli_agent_orchestrator/linear/workspace_provider.py src/cli_agent_orchestrator/workspace_providers/registry.py src/cli_agent_orchestrator/workspace_providers/invocation.py test/linear/test_provider_tools.py test/linear/test_workspace_provider.py && \
uv run black --check src/cli_agent_orchestrator/linear/provider_tools.py src/cli_agent_orchestrator/linear/workspace_provider.py src/cli_agent_orchestrator/workspace_providers/registry.py src/cli_agent_orchestrator/workspace_providers/invocation.py test/linear/test_provider_tools.py test/linear/test_workspace_provider.py && \
uv run mypy src/cli_agent_orchestrator/linear/provider_tools.py src/cli_agent_orchestrator/linear/workspace_provider.py src/cli_agent_orchestrator/workspace_providers/registry.py src/cli_agent_orchestrator/workspace_providers/invocation.py && \
uv run pytest test/linear/test_provider_tools.py test/linear/test_workspace_provider.py test/workspace_providers test/mcp_server/test_provider_tool_registration.py test/integration/test_provider_mediated_contract.py -q && \
uv run pytest -q
```

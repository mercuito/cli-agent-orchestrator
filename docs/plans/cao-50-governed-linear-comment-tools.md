# CAO-50 Governed Linear Comment Write Tools

## Source

Linear issue CAO-50, with CAO-25 parent context, CAO-27 provider-mediated MCP
contract, and the landed CAO-28 read-only Linear provider tools as binding
context.

## Scope

- Add only the CAO-mediated Linear comment creation tool:
  `cao_linear.create_comment`.
- Use the existing provider-mediated MCP registration and invocation lifecycle.
- Keep Linear write policy, target resolution, credential checks, GraphQL
  mutation, and payload shaping in `cli_agent_orchestrator.linear`.
- Preserve existing read-only Linear tools, quick-reply behavior, and built-in
  CAO MCP behavior.

Out of scope:

- Issue creation or issue update fields.
- Raw Linear MCP passthrough.
- Live Linear smoke tests.
- Broad audit/event systems.

## Comment-Write Policy

- Linear comment access remains provider-owned configuration in
  `linear.toml` under `[tool_access.<name>]`.
- A `tool_access` entry grants `cao_linear.create_comment` to exactly one
  `agent_id` or `agent_profile` and a bounded list of authorized Linear issue
  ids or identifiers through the existing `issues` list.
- The target issue is accepted only when `issue` or a Linear `issue_ref`
  matches that allowlist. Wrong-provider refs are denied before provider API
  calls.
- The comment body must be a non-empty string after trimming. Blank or
  non-string bodies are denied before provider API calls, but valid authored
  comment text is sent to Linear unchanged.
- The provider must find a Linear presence and usable credentials for the CAO
  identity before GraphQL calls. Missing or expired credentials fail clearly.
- The handler resolves the authorized issue through Linear before mutation, so
  archived, inaccessible, missing, or policy-mismatched issues fail before
  comment creation. The mutation uses the resolved Linear issue id.
- The mutation result must indicate success and return a comment id. Provider
  or API failures are reported through the existing mediated handler error
  path and never shaped as success.

## Implementation Plan

1. Extend the Linear provider tool module with centralized comment-write
   vocabulary, input schema, a write policy pre-call hook, mutation helper, and
   compact result shaping.
2. Reuse CAO-28 target authorization, returned-issue validation, presence, and
   credential handling rather than adding a parallel policy path.
3. Extend Linear provider config validation to accept `cao_linear.create_comment`
   in existing `tool_access` entries while preserving existing read-only tools.
4. Add focused tests for registration, allowed creation, denied creation,
   raw/unmapped terminal rejection, blank/invalid body rejection, missing and
   expired credentials, provider/API failure behavior, raw/unmapped terminal
   invocation rejection, and read-only tools remaining unaffected.
5. Run focused Linear/provider-mediated tests, formatting/type checks for the
   touched Python files, and the full suite if feasible.

## Selected Criteria

Coding code criteria:

- `full-verification-required`: CAO-50 changes production behavior and needs
  focused and broad proof.
- `minimal-cohesive-changes`: the slice is limited to governed Linear comment
  creation and the config vocabulary needed to expose it.
- `no-unnecessary-duplication`: comment creation must reuse the CAO-28 Linear
  policy and payload helpers where reasonable.
- `respect-ownership-boundaries`: Linear vocabulary, GraphQL mutation, and
  write policy stay in the Linear provider package; CAO core sees normalized
  provider-mediated tool access.
- `readable-and-explicit`: denial reasons, mutation response checks, and result
  fields are named explicitly.
- `respect-standing-decisions`: CAO-25/27/28 require provider-mediated access,
  no raw Linear MCP passthrough, and provider-owned policy.
- `boundary-and-failure-testing`: the MCP/provider boundary accepts authored
  issue refs and comment bodies and must reject malformed and denied calls.
- `centralized-vocabulary`: the new tool name, hook name, and Linear tool set
  are centralized in the Linear provider tool module.
- `prefer-public-surfaces`: tests should prove registration/invocation through
  FastMCP or `ProviderMediatedToolInvocationService`.
- `red-green-refactor`: tests are added for new observable behavior before or
  alongside the implementation.
- `semantic-continuity`: write access follows the same provider-mediated
  lifecycle and Linear target allowlist as read access.
- `service-definition-surface` and `well-defined-service`: the existing Linear
  provider tool service is extended without moving Linear policy into CAO core.
- `service-export-discipline`: the Linear provider tool module export surface
  changes from read-only to read/write vocabulary.
- `no-assumed-backwards-compatibility`: old read-only provider class aliases
  are not preserved without an explicit contract requirement.
- `authored-document-edit-preservation`: saving structured Linear OAuth config
  must preserve `tool_access` entries that may now include the write tool.
- `external-integration-testing`: the new Linear GraphQL mutation is documented
  against Linear's official GraphQL/API documentation and mocked tests mirror
  the expected provider payload shape.

Coding test criteria:

- `test-validity-preserved`: existing read-only Linear tests must continue to
  prove the same behavior.
- `verification-scope-discipline`: run focused Linear/provider-mediated tests
  and broader verification.
- `reusable-test-state`: shared fixtures should own repeated identity,
  presence, config, provider, MCP, and payload setup.
- `test-through-owner-surfaces`: tests exercise Linear provider config,
  provider-mediated invocation, and MCP registration surfaces.
- `real-surface-proof-discipline`: proof goes through FastMCP/invocation
  surfaces rather than only private helper calls.
- `public-boundary-proof`: the new MCP tool and `linear.toml` config shape are
  public/user boundaries.
- `given-when-then-test-structure`: multi-step authorization/mutation scenarios
  should remain easy to audit.
- `setup-invariant-ownership`: fixtures own valid setup so failures are about
  the behavior under test.
- `test-file-organization`: comment-write tests live beside the existing
  Linear provider tool tests and are grouped by behavior.
- `external-integration-testing`: mocked GraphQL responses include the expected
  `commentCreate { success comment { ... issue { ... } } }` shape and failure
  variants.

## CAO-50 Behavioral Contract Defence

- Only `cao_linear.create_comment` is added as a new Linear write tool. No issue
  creation/update tools, raw Linear passthrough tools, quick-reply replacement,
  or audit/event subsystem are introduced.
- Registration remains governed by the existing CAO provider-mediated MCP
  lifecycle. The tool is visible only when an identity-managed terminal resolves
  to a CAO agent identity with a matching Linear `tool_access` grant.
- Comment-write policy is Linear-provider-owned and uses the existing
  `linear.toml` `[tool_access.<name>]` entry shape: one `agent_id` or
  `agent_profile`, explicit `tools`, and a bounded `issues` allowlist.
- The write pre-call hook rejects unauthorized issues, wrong-provider refs,
  missing issue arguments, and invalid or blank bodies before the Linear API
  can be called. Valid authored comment text is preserved rather than trimmed
  before mutation.
- The handler resolves the authorized Linear issue through the mapped Linear
  app/user credentials, rejects missing/archived/inaccessible/policy-mismatched
  issues, then calls `commentCreate` with the resolved issue id.
- Missing and expired credentials fail before any provider API success is
  shaped. Linear API/OAuth failures and unsuccessful mutation responses surface
  through the existing provider-mediated handler error path.
- Successful writes return a compact result with status, created comment id,
  comment or issue URL, issue id/identifier/url, and created/updated
  timestamps when Linear returns them.
- Existing read-only tools continue to use the read policy hook and are tested
  in a mixed `tool_access` entry with the write tool to prove they remain
  unaffected.

## CAO-50 Test Contract Defence

- Registration and allowed-write proof:
  `test_linear_comment_tool_registers_and_creates_authorized_comment`.
- Denial proof:
  `test_linear_comment_tool_denies_unauthorized_issue_before_graphql`,
  `test_linear_comment_tool_rejects_invalid_body_before_graphql`, and
  `test_linear_comment_tool_fail_closed_for_unmapped_or_unauthorized_terminals`.
- Credential and provider/API failure proof:
  `test_linear_comment_tool_reports_missing_or_expired_credentials_before_graphql`
  and `test_linear_comment_tool_reports_provider_api_failures`.
- Read-only preservation proof:
  `test_linear_comment_tool_leaves_read_only_tools_unaffected` plus the
  existing CAO-28 read-only tests in `test/linear/test_provider_tools.py`.
- Config preservation proof:
  `test_structured_token_update_preserves_linear_tool_access` now includes
  `cao_linear.create_comment` in the preserved tool list.

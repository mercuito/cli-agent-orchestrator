# CAO-51 Governed Linear Issue Mutation Tools

## Source

Linear issue CAO-51, including the 2026-05-09 policy-decision comment, with
CAO-25 parent framing, CAO-27 provider-mediated MCP contract, and landed
CAO-28/CAO-50 Linear provider tool implementations as binding context.

## Scope

- Add only these CAO-mediated Linear issue mutation tools:
  `cao_linear.create_issue` and `cao_linear.update_issue`.
- Use the existing provider-mediated MCP registration, access, hook, and
  invocation lifecycle.
- Keep Linear tool names, GraphQL, mutation policy, validation, reference
  resolution, and result shaping inside `cli_agent_orchestrator.linear`.
- Preserve CAO-28 read-only tools and CAO-50 comment-write behavior.

Out of scope:

- Raw Linear MCP passthrough.
- Delete/archive, bulk mutation, monitor behavior, live smoke tests,
  arbitrary user Python hooks, and broad audit/event storage.

## Issue Mutation Policy

- Linear issue mutation access remains provider-owned configuration in
  `linear.toml` under `[tool_access.<name>]`.
- A `tool_access` entry grants tools to exactly one `agent_id` or
  `agent_profile`.
- `issues` remains the allowlist for issue-targeting tools. It is required when
  `cao_linear.update_issue` or the existing read/comment tools are configured,
  and optional for create-only grants.
- `cao_linear.create_issue` requires `create_team_ids` to be a non-empty list
  of authorized Linear team ids or keys. The agent supplies that authorized id
  or key as `team_id`; the provider resolves it to the Linear team UUID before
  `issueCreate`. It may set `project_id` only when the project is listed in
  `create_project_ids`. It may set `parent_issue` only when the parent is
  listed in `create_parent_issues` and the provider resolves that parent before
  mutation. Top-level creation is allowed only when
  `allow_top_level_create = true`.
- A create grant must permit at least one creation shape: top-level creation or
  one or more configured parent issues.
- `cao_linear.update_issue` requires a non-empty `update_fields` list. V1
  allowed fields are `title`, `description`, `state_id`, `assignee_id`,
  `project_id`, `parent_issue`, `label_ids`, and `priority`. The issue comment
  lists `priority` as accepted input but omits it from one supported-field
  sentence; this plan treats it as governed by `update_fields`, not as a
  passthrough.
- Update target issues are resolved before mutation, must be authorized by
  `issues`, must not be archived, and mutation uses the returned Linear issue
  id.
- `parent_issue` update values must be authorized by `create_parent_issues`,
  resolved before mutation, and sent to Linear as `parentId`.
- Blank create/update titles, non-list or blank `label_ids`, unknown/denied
  fields, invalid priority values, unauthorized team/project/parent/issue
  targets, missing/expired credentials, and provider/API failures fail with
  bounded diagnostics.
- Results return compact stable mutation payloads with `status`, issue id,
  identifier, title, URL, compact team/project/state, and sorted
  `changed_fields`.

## Implementation Plan

1. Extend `LinearToolAccess` and `linear.toml` parsing/preservation for the
   CAO-51 create/update boundary fields, with fail-closed preflight validation.
2. Extend `LinearToolProvider` with centralized tool names, schemas, mutation
   hooks, validation helpers, Linear reference resolution, GraphQL mutations,
   and compact result shaping.
3. Reuse the CAO-28/CAO-50 provider-mediated authorization lifecycle and
   credential/API failure handling rather than adding any CAO-core Linear
   policy.
4. Add focused tests through the Linear provider/MCP/invocation surfaces for
   successful create/update, denied targets before mutation, invalid fields and
   refs, raw/unmapped/no-access terminals, missing/expired credentials,
   provider/API failures, and read/comment preservation.
5. Run focused formatting/type/test proof plus the broader relevant Linear,
   provider-mediated, and full test suite if feasible.
6. Dispatch the required correctness, implementation-criteria, and
   test-contract reviewer agents against CAO-51, this plan, the criteria
   catalog, and the final diff; address grounded findings before reporting.

## Selected Criteria

Coding code criteria:

- `full-verification-required`: CAO-51 changes production behavior and needs
  focused and broad proof.
- `minimal-cohesive-changes`: the slice is limited to governed Linear issue
  creation/update and related config vocabulary.
- `no-unnecessary-duplication`: mutation tools reuse existing Linear policy,
  credential, issue-resolution, and payload helpers where reasonable.
- `respect-ownership-boundaries`: Linear vocabulary, GraphQL, and policy stay
  in the Linear provider package; CAO core consumes normalized provider access.
- `readable-and-explicit`: field allowlists, denials, GraphQL mappings, and
  result shaping are named rather than inferred dynamically.
- `respect-standing-decisions`: CAO-25/27/28/50 and the CAO-51 policy comment
  require provider-mediated access and no raw Linear passthrough.
- `boundary-and-failure-testing`: the MCP/provider boundary accepts authored
  mutation input and must reject malformed, denied, and provider-failed calls.
- `centralized-vocabulary`: new tool names, hook names, fields, and supported
  Linear mutation vocabulary are centralized in the Linear provider tool module.
- `prefer-public-surfaces`: tests prove behavior through FastMCP or
  `ProviderMediatedToolInvocationService`.
- `red-green-refactor`: tests are added for new observable mutation behavior.
- `semantic-continuity`: issue mutation follows the same provider-mediated
  lifecycle as read/comment tools.
- `service-definition-surface` and `well-defined-service`: the existing Linear
  provider tool service is extended without moving provider policy to CAO core.
- `service-export-discipline`: the Linear provider tool module export surface
  expands with issue mutation tool vocabulary.
- `authored-document-edit-preservation`: saving structured Linear OAuth config
  must preserve new tool access fields.
- `external-integration-testing`: mocked GraphQL responses mirror the Linear
  GraphQL mutation shapes used by production code.

Coding test criteria:

- `test-validity-preserved`: existing read-only and comment-write Linear tests
  remain valid.
- `verification-scope-discipline`: run focused Linear/provider-mediated tests
  plus broader verification.
- `reusable-test-state`: shared fixtures own repeated identity, presence,
  config, provider, MCP, and payload setup.
- `test-through-owner-surfaces`: tests exercise provider config,
  provider-mediated invocation, and MCP registration surfaces.
- `real-surface-proof-discipline`: proof goes through FastMCP/invocation
  surfaces rather than only private helper calls.
- `public-boundary-proof`: the new MCP tools and `linear.toml` fields are
  public/user boundaries.
- `given-when-then-test-structure`: multi-step mutation scenarios should remain
  easy to audit.
- `setup-invariant-ownership`: fixtures own valid setup so failures prove the
  behavior under test.
- `test-file-organization`: issue mutation tests live beside existing Linear
  provider tool/config tests and are grouped by behavior.
- `external-integration-testing`: mocked GraphQL responses include expected
  `issueCreate` and `issueUpdate` success/failure variants.

## CAO-51 Behavioral Contract Defence

- Only `cao_linear.create_issue` and `cao_linear.update_issue` were added as
  new Linear tools. No delete/archive, raw Linear passthrough, monitor, live
  smoke, Python hook, or audit/event subsystem was introduced.
- Registration remains governed by the existing provider-mediated MCP
  lifecycle. Tools are visible only to identity-managed terminals whose CAO
  identity has matching Linear `tool_access`.
- Create policy is owned by the Linear provider config: `create_team_ids` is
  required, `create_project_ids` bounds project targets, `create_parent_issues`
  bounds sub-issue parents, and `allow_top_level_create` controls top-level
  creation.
- Update policy is owned by the Linear provider config: target issues must be
  in `issues`, `update_fields` must be non-empty, and only listed fields may
  be mutated. `project_id` updates are also bounded by `create_project_ids`;
  `parent_issue` updates are bounded by `create_parent_issues`.
- Mutation validation rejects blank titles, invalid labels, non-integer or
  out-of-range priorities, unknown fields, unauthorized team/project/parent
  targets, unauthorized issue targets, missing/expired credentials, invalid
  references, and provider/API failures with bounded diagnostics.
- Successful mutation payloads return compact stable issue fields plus sorted
  `changed_fields`.
- Existing CAO-28 read-only tools and CAO-50 comment-write tools remain on
  their prior policy paths and are covered in mixed-tool tests.

## CAO-51 Test Contract Defence

- Successful create/update proof:
  `test_linear_create_issue_tool_registers_and_creates_authorized_subissue`
  and `test_linear_update_issue_tool_registers_and_updates_authorized_fields`.
- Unauthorized target proof:
  `test_linear_issue_mutation_tools_reject_unauthorized_targets_before_graphql`
  covers denied team, project, parent, issue, and update field targets before
  GraphQL mutation.
- Invalid field/reference proof:
  `test_linear_create_issue_tool_rejects_invalid_fields_before_graphql`,
  `test_linear_update_issue_tool_rejects_invalid_fields_before_graphql`, and
  `test_linear_issue_mutation_tools_reject_invalid_references_before_mutation`.
- Raw/unmapped/no-access proof:
  `test_linear_issue_mutation_tools_fail_closed_for_unmapped_or_unauthorized_terminals`.
- Credential and provider/API failure proof:
  `test_linear_issue_mutation_tools_report_missing_or_expired_credentials_before_graphql`
  and `test_linear_issue_mutation_tools_report_provider_api_failures`.
- CAO-28/CAO-50 preservation proof:
  `test_linear_comment_tool_leaves_read_only_tools_unaffected` plus the
  existing read/comment tests in `test/linear/test_provider_tools.py`.
- Authored config preservation proof:
  `test_structured_token_update_preserves_linear_tool_access` proves CAO-51
  fields, comments, and unrelated authored keys survive structured OAuth token
  updates.

## Reviewer Outcomes

- Correctness reviewer requested project-boundary checks for update
  `project_id`, strict integer priority validation, and confirmation that
  authorized team keys work rather than only raw team UUIDs. All three were
  implemented.
- Implementation-criteria reviewer requested centralized config-key vocabulary
  and authored TOML preservation. Config keys are now constants, and structured
  token updates patch only the relevant presence section.
- Test-contract reviewer requested parent-denial coverage, update invalid-input
  coverage, and persisted test/readiness defence. Tests and this defence were
  added.

## Verification Results

- `uv run isort --check-only src/cli_agent_orchestrator/linear/provider_tools.py src/cli_agent_orchestrator/linear/workspace_provider.py test/linear/test_provider_tools.py test/linear/test_workspace_provider.py && uv run black --check src/cli_agent_orchestrator/linear/provider_tools.py src/cli_agent_orchestrator/linear/workspace_provider.py test/linear/test_provider_tools.py test/linear/test_workspace_provider.py`
  passed.
- `uv run mypy src/cli_agent_orchestrator/linear/provider_tools.py src/cli_agent_orchestrator/linear/workspace_provider.py`
  passed.
- `uv run pytest test/linear/test_provider_tools.py test/linear/test_workspace_provider.py -q`
  passed: 85 tests.
- `uv run pytest test/linear/test_provider_tools.py test/linear/test_workspace_provider.py test/workspace_providers test/mcp_server/test_provider_tool_registration.py test/integration/test_provider_mediated_contract.py -q`
  passed: 126 tests.
- `uv run pytest -q` passed: 1968 passed, 16 skipped, 76 deselected, 3 warnings.

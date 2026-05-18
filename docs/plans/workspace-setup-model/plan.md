# Workspace Setup Model

Status: draft

## Problem

Workspace context is currently configured at too low a level for how agents are
supposed to collaborate.

Today an agent can opt into workspace context resolution through its own
`[workspace_context]` block:

```toml
[workspace_context]
enabled = true
resolver_id = "linear_planning"
```

That exposes implementation details directly on each agent. It also makes
collaboration fragile: two agents may both be "workspace aware" while using
different resolver definitions, provider assumptions, or context IDs. When that
happens, a message can look valid while the receiver is not actually in the same
planning/work context.

The desired model is higher level:

- an agent belongs to one named workspace setup,
- a setup defines the workspace providers available to that collaboration
  domain,
- a setup owns exactly one resolver,
- the resolver may consult multiple providers, but it is the only authority for
  deriving workspace context IDs,
- agents in the same setup can naturally collaborate,
- agents outside the same setup receive an explicit rejection instead of
  silently degrading.

## Current Shape

The implementation pieces already exist, but they are not grouped into a single
concept:

- Global provider enablement lives in `workspace-providers.toml`.
- `AgentWorkspaceContextConfig` lives on each agent and stores
  `enabled/resolver_id`.
- `resolve_workspace_context_for_agent(agent, event)` skips resolution when the
  agent-level flag is disabled and otherwise dispatches by resolver id.
- The Linear provider registers `linear_planning` as a resolver.
- `AgentRuntimeHandle` always binds terminals to a concrete workspace context;
  when no context is supplied it uses the default context.
- Agent inbox receiver IDs include the active workspace context id, so runtime
  messaging already has a context dimension.

The missing piece is a manager above providers and resolvers that turns these
parts into an agent membership model.

## Locked Vocabulary

Use **workspace setup** for this concept.

Avoid **workspace scope** in the implementation and UI unless a later plan
defines a different concept. "Scope" is too vague for the product model here.

Treat "membership" carefully. An agent can have an external provider presence,
such as a Linear app user or GitHub identity, without being addressable inside a
CAO workspace setup. In this plan, membership means participation in the
CAO-managed workspace setup, not membership in the provider's own workspace.

## Target Configuration

Each agent references at most one setup:

```toml
[workspace]
setup = "cao_delivery"
```

No setup means the agent has no workspace setup membership. In that state:

- provider event resolution is disabled for that agent,
- collaboration checks treat the agent as outside any setup,
- runtime terminals still get a default workspace context, preserving the
  existing terminal invariant.

Setup definitions are code-owned in v1. That keeps the subsystem localized and
prevents a second broad config format before the model is proven. A later plan
can introduce TOML-defined setup instances if users need to create arbitrary
setups without code changes.

Example v1 setup definition:

```python
WorkspaceSetup(
    id="cao_delivery",
    display_name="CAO Delivery",
    providers=("linear", "github"),
    resolver=LinearPlanningWorkspaceResolver(...),
)
```

The setup has one resolver. That resolver can ask Linear, GitHub, or future
providers for data, but it must return one authoritative
`WorkspaceContextResolution`.

## Provider Addressability

Workspace setup membership should gate provider addressability as early as
possible.

The boundary should be:

- a workspace provider owns provider-native vocabulary, credentials, API calls,
  webhook parsing, tool implementations, and candidate provider-to-agent
  mappings;
- a workspace setup owns which candidate mappings are authorized for this setup;
- provider-native presence does not automatically imply CAO setup membership.

In other words, Linear can remain a provider adapter, but the
`cao_delivery` setup authorizes the Linear address book that CAO uses for
`cao_delivery`.

External providers can still know about a presence that CAO should not use. For
example, a Linear app user may exist for Agent B because OAuth/setup happened at
some point. If Agent A belongs to setup `cao_delivery` and Agent B does not,
then a Linear mention, delegation, teammate lookup, or app-user ping inside
`cao_delivery` must not resolve Agent B as a CAO-managed recipient.

The natural prevention point is provider config materialization:

- Let each provider build candidate mappings using its own domain rules.
- Pass those candidates through workspace setup authorization before they become
  CAO-addressable.
- Include only authorized provider presences and provider tool access for agents
  that belong to that setup.
- Keep provider-native extraction functions available so the setup can ask the
  provider for candidates without duplicating Linear/GitHub parsing details.
- Let external provider identities remain untouched.
- Do not expose a CAO recipient mapping for out-of-setup agents.

For Linear, the provider still creates candidate `LinearPresence` mappings from
agent `[linear]` config. The setup then authorizes only candidates whose agent
belongs to the current setup. The resulting setup-bound `LinearProviderConfig`
for `cao_delivery` includes only authorized presences and tool access. If a
webhook or provider tool tries to resolve an app user that belongs to Agent B
outside the setup, `presence_by_app_user_id` and `resolve_presence` should
behave as "unknown in this setup" rather than returning Agent B and relying on a
later runtime guard.

This gives three layers of protection:

1. Setup authorization prevents provider candidate mappings from becoming
   addressable in the wrong setup.
2. Event resolution rejects unknown/out-of-setup provider identities before a
   runtime handle is created.
3. Collaboration routing still rejects cross-setup messages as a final
   invariant check.

The third layer is still required, but it should not be the first line of
defense.

## Proposed Architecture

Create a localized workspace setup subsystem, likely under:

```text
src/cli_agent_orchestrator/workspace_setups/
```

The subsystem owns these public concepts:

- `WorkspaceSetup`: immutable definition of a named setup.
- `WorkspaceSetupResolver`: protocol for resolving provider/runtime events into
  a `WorkspaceContextResolution`.
- `WorkspaceSetupRegistry`: code-owned registration and lookup of known setup
  definitions.
- `WorkspaceSetupMembership`: the parsed agent membership reference.
- `WorkspaceSetupManager`: the runtime service that validates membership,
  resolves events, and enforces collaboration boundaries.
- `WorkspaceSetupProviderView`: a setup-filtered projection of provider
  presences, provider tool access, and provider-native address mappings.
- `WorkspaceProviderAdapter`: provider-owned code that can build a provider view
  from authorized provider mappings while keeping provider-specific parsing and
  API behavior inside the provider package.
- `WorkspaceProviderCandidateMapping`: provider-owned candidate mapping from a
  provider-native identity or access grant to a CAO agent before setup
  authorization.
- `WorkspaceSetupAuthorizedMapping`: setup-owned decision that a candidate
  mapping is addressable inside one setup.

Consumers should use this package's public API. They should not reach directly
into registry internals or provider-specific resolver modules except from setup
definition code.

## Manager Responsibilities

`WorkspaceSetupManager` should own the behavior that is currently spread across
agent config, provider runtime code, and message routing decisions:

1. Validate an agent's configured setup name when agents are loaded or used.
2. Report unknown setup names as diagnostics instead of silently disabling
   context.
3. Validate that the setup's providers are available when the setup is used.
4. Request candidate provider mappings from provider adapters.
5. Authorize or prune those mappings against setup membership.
6. Build setup-filtered provider views so out-of-setup agents are not
   addressable through provider-native identities.
7. Resolve provider/runtime events by delegating to the setup's single resolver.
8. Return no resolution for agents without a setup.
9. Bind resolved workspace context IDs into `AgentRuntimeHandle` creation.
10. Decide whether two agents can collaborate naturally:
   - same non-empty setup: allowed,
   - different setup: rejected,
   - one or both without setup: rejected for setup-aware collaboration.
11. Produce user-visible rejection messages that name the sender, receiver, and
   setup mismatch.

The manager should not replace the lower-level workspace context store. It sits
above it and chooses which context ID the runtime should use.

The manager should also avoid becoming a provider parser. It should ask each
provider adapter for candidate mappings, authorize or prune those mappings
against setup membership, and pass authorized mappings back to provider adapters
to construct provider views. That keeps Linear-specific fields like
`app_user_id`, `app_key`, OAuth state, and Linear tool-access validation inside
the Linear package, while moving the final addressability decision one level
higher.

## Migration Strategy

This plan intentionally includes a short compatibility period because existing
agents and tests may still contain `[workspace_context]`.

Phase 1 may read both shapes:

- `[workspace] setup = "..."` is the new authoritative shape.
- `[workspace_context]` is treated as legacy input only.
- If both are present, `[workspace] setup` wins and a diagnostic should explain
  that the legacy block is ignored.
- Legacy resolver ids are mapped only through an explicit migration table, not
  through fuzzy matching.

By the end of the implementation series:

- all production call sites use workspace setup APIs,
- repository examples/tests use `[workspace] setup`,
- direct behavioral dependence on `[workspace_context]` is removed,
- legacy resolver-id dispatch paths that let agents bypass setup membership are
  removed,
- no new feature is built on the legacy shape.

The plan does not allow preserving legacy behavior indefinitely. Any retained
legacy parser must be temporary migration support inside this implementation
series and must be removed before the Definition of Done is satisfied unless the
operator explicitly amends this plan.

## Implementation Phases

### Phase 1 - Define the Setup Subsystem

- Add the `workspace_setups` package with public types and manager API.
- Register the first setup that models the current Linear planning behavior.
- Keep runtime behavior unchanged while unit tests prove lookup, validation,
  and one-resolver-per-setup invariants.
- Add diagnostics for unknown setup names and unavailable providers.
- Add the provider candidate mapping and setup authorization contracts, even if
  Linear is the only provider implementation at first.

### Phase 2 - Add Agent Membership Config

- Add `[workspace] setup` parsing/writing to the agent config model.
- Keep legacy `[workspace_context]` parsing as temporary migration support.
- Update config serialization so newly written agent files use `[workspace]`.
- Update API responses and dashboard config views to show the setup name and
  workspace context state clearly.

### Phase 3 - Route Resolution Through the Manager

- Replace direct calls to `resolve_workspace_context_for_agent` in provider
  runtimes with manager calls.
- Move Linear planning resolution behind a workspace setup resolver adapter.
- Build Linear presence resolution from setup-authorized candidate mappings, not
  the global set of agents with Linear config.
- Treat a Linear app user/app key that belongs to an out-of-setup agent as not
  CAO-addressable in the current setup.
- Preserve default runtime context behavior for agents without setup
  membership.
- Add integration coverage that a Linear event resolves through the setup and
  starts or addresses the agent in the resolved context.

### Phase 4 - Enforce Collaboration Boundaries

- Identify agent-to-agent messaging entry points, including MCP/server surfaces.
- Add a setup-aware guard before sending workspace-dependent messages.
- Allow same-setup collaboration.
- Reject cross-setup collaboration with a clear message.
- Reject setup-aware collaboration when either agent has no setup.
- Keep purely terminal-addressed diagnostic operations separate if they are not
  semantically agent collaboration.

### Phase 5 - Diagnostics and UI

- Surface setup validation problems in API responses and the dashboard.
- Show the selected agent's setup alongside workspace context metadata.
- Keep terminals visible only in agent context, but include enough setup/context
  information to explain why collaboration or provider event routing worked.
- If UI changes are made, verify in a real browser against the backend-served
  bundle, including any remote/Tailscale route used during review.

### Phase 6 - Legacy Cleanup

- Remove old `[workspace_context]` behavioral entry points once live configs and
  tests have moved.
- Delete unused resolver-id plumbing that lets agents bypass setup membership.
- Delete old tests, fixtures, examples, and docs that encode the legacy
  `[workspace_context]` model except for explicit historical migration notes.
- Update docs/examples so "workspace setup" is the only documented path.

## Test Plan

Use owner surfaces and real seams wherever practical.

Required coverage:

- Config parse/write:
  - agent with `[workspace] setup` round-trips,
  - agent with no setup remains valid,
  - legacy `[workspace_context]` maps only through the explicit migration table,
  - both shapes present prefers `[workspace]` and emits a diagnostic.
- Setup registry/manager:
  - unknown setup is rejected or surfaced as a diagnostic,
  - unavailable provider is detected,
  - setup definitions cannot have multiple resolvers,
  - agents without setup do not run provider event resolution.
- Provider addressability:
  - Linear creates candidate mappings from agent `[linear]` config,
  - setup authorization prunes candidates whose agents are not in that setup,
  - Linear provider view for a setup includes only authorized candidates,
  - an out-of-setup agent with valid Linear credentials is not returned by
    setup-bound app user/app key lookup,
  - provider tool access for out-of-setup agents is not exposed in that setup,
  - the rejection/error text makes clear that the provider identity is not
    CAO-addressable in the current setup.
- Runtime resolution:
  - Linear event plus setup membership resolves to the expected workspace
    context,
  - Linear event targeting an out-of-setup app user is rejected before an
    `AgentRuntimeHandle` is created,
  - `AgentRuntimeHandle` receives the resolved context ID,
  - no setup still binds to the default context.
- Collaboration:
  - same setup can collaborate,
  - different setup is rejected with a clear message,
  - missing setup is rejected for setup-aware collaboration,
  - direct diagnostic terminal access remains possible only through its existing
    owner surface.
- Dashboard/API, if touched:
  - setup name and active workspace context render for selected agents,
  - diagnostics render without blocking unrelated agent inspection,
  - browser verification exercises the real served app, not only component
    tests.

## Verification Matrix

Implementation is not complete until each acceptance claim has observable
evidence. Do not rely on illustrative providers that do not exist in production
unless the test is explicitly exercising the provider-agnostic setup contract.

| Claim | Required evidence |
| --- | --- |
| Agent config supports one setup | Parse/write tests load real temporary agent directories with `[workspace] setup`, no setup, legacy `[workspace_context]`, and both shapes present. |
| Setup definitions are localized | Code review verifies setup public types, registry, manager, and provider-view contracts live under the setup subsystem; consumers import the public surface. |
| Setup owns final addressability | Manager tests use a real in-process test provider adapter that returns candidate mappings for Agent A and Agent B, then verify only setup-member candidates become authorized. The manager itself must not be mocked. |
| Linear candidate mapping still owns Linear domain details | Linear tests build candidate mappings from real temporary agent configs containing `[linear]` fields and assert `app_key`, `app_user_id`, tool access, and validation behavior come from Linear-owned code. |
| Linear pruning works | With Agent A and Agent B both having valid Linear config but only Agent A in setup `cao_delivery`, setup-bound Linear lookup resolves A and does not resolve B by app key, app user id, or app user name. |
| Provider tool access is pruned | With out-of-setup Linear tool access configured for Agent B, the setup-bound provider tool surface does not expose B's tools in `cao_delivery`. |
| Runtime resolution uses authorized mappings | A Linear issue event for Agent A resolves through the setup manager and creates/uses an `AgentRuntimeHandle` with the resolved workspace context id. |
| Runtime rejection is early | A Linear issue event for Agent B, outside the setup, is rejected before an `AgentRuntimeHandle` is constructed, before a terminal is started, and before an inbox notification is queued. |
| Default runtime context survives | Starting an agent with no setup still creates a terminal in the default workspace context and does not attempt provider-event resolution. |
| Collaboration boundaries hold | Public messaging/handoff surfaces allow same-setup collaboration and reject different-setup or missing-setup collaboration with clear text naming both agents and setup mismatch. |
| Diagnostics are visible | Unknown setup, unavailable provider, legacy config conflict, and pruned provider identity diagnostics are visible through the owning API/service surface. |
| Legacy code paths are removed | Static search and focused tests verify production code no longer uses `[workspace_context]` for behavior, direct resolver-id dispatch is gone from agent-owned routing, and examples/docs no longer present the legacy model as valid configuration. |
| UI behavior works if touched | Component tests cover rendered fields/actions, `npm run build` passes, and a real browser verifies the backend-served dashboard path that changed. |

The provider-agnostic pruning test is required even before a GitHub provider
exists. It should implement the real candidate-mapping adapter protocol in test
code and exercise the setup manager's authorization logic. GitHub-specific
behavior is not required until a GitHub provider exists.

## Required Verification Commands

The final implementation report must list the exact commands run and their
results. At minimum, run the narrow tests added for this plan plus the relevant
existing suites they touch.

Expected verification shape:

- `uv run pytest ...` for agent config, setup manager, Linear provider mapping,
  Linear runtime event handling, and collaboration boundary tests.
- `npm test -- ...` for dashboard component changes, if the web UI is touched.
- `npm run build`, if frontend code or generated API types are touched.
- Real browser verification of the backend-served dashboard, if dashboard UI or
  runtime links/actions are touched.
- `git diff --check`.

If any command cannot be run, the implementation is not complete until the
blocker is documented in the completion report and either resolved or accepted
by the operator.

## Definition of Done

The work is done only when all of the following are true:

- Agents reference workspace setup membership through exactly one new
  authoritative config field, `[workspace] setup`.
- Agent config parse/write behavior is verified through real temporary config
  files, including no-setup and legacy-conflict cases.
- Workspace setup definitions, candidate authorization, provider-view creation,
  diagnostics, and collaboration checks are localized behind one public setup
  subsystem surface.
- Each workspace setup owns exactly one resolver, and tests fail if a setup
  attempts to define more than one.
- Providers create candidate mappings using provider-owned domain logic; setup
  authorization decides which candidates become CAO-addressable.
- Provider-agnostic pruning is verified with a real test adapter implementing
  the public provider adapter contract.
- Linear pruning is verified concretely: an out-of-setup agent with valid
  Linear credentials cannot be resolved by app key, app user id, app user name,
  provider event, or provider tool-access lookup inside another setup.
- Linear provider behavior that should still work is verified through the new
  manager path, including a successful issue event for an in-setup agent.
- Out-of-setup provider events are rejected before terminal creation, runtime
  handle construction, or inbox notification creation.
- Agents without setup membership still start in the default workspace context
  and do not receive provider-event context switching.
- Same-setup collaboration succeeds through the public messaging/handoff owner
  surface; different-setup and missing-setup collaboration fail with clear,
  user-visible rejection text.
- Unknown setup names, unavailable providers, legacy config conflicts, and
  pruned provider identities produce diagnostics visible through the owning
  service/API surface.
- Legacy `[workspace_context]` behavior paths, direct resolver-id dispatch, and
  old examples/docs are removed by the end of the implementation series; any
  temporary migration parser retained during intermediate phases is deleted
  before this DoD is claimed unless this plan is explicitly amended.
- Every changed behavior in the verification matrix has passing automated
  coverage through owner surfaces and relevant seams.
- If dashboard or API-visible UI behavior changes, component tests, production
  build, and real browser verification of the served dashboard all pass.
- A review loop has inspected the completed diff against this plan and the
  criteria catalog.
- After implementation, evaluate the pending changes against the criteria
  catalog. No criteria applicable to the completed diff may be violated.

## Criteria Catalog

The criteria catalog was reviewed with:

```bash
uv run python scripts/catalog_criteria.py --format json
```

Likely implementation criteria for this work:

- `do-not-assume-backwards-compatibility`
- `migration-discipline`
- `minimal-cohesive-changes`
- `prefer-public-surfaces`
- `system-definitions-are-localized`
- `authoritative-sources-are-referenced-not-copied`
- `readable-and-explicit`
- `simple-systems`
- `system-code-locality`

Likely test criteria for this work:

- `all-system-interactions-are-verified-by-tests`
- `seams-must-be-tested`
- `target-behavior-must-not-be-mocked`
- `test-through-owner-surfaces`
- `test-validity-preserved`
- `ui-changes-require-real-browser-verification` if dashboard behavior changes.

Implementation must reload any criteria whose `when` clauses match the actual
diff before final review.

## Open Questions

- Should the first setup id be product-specific, such as `cao_delivery`, or
  behavior-specific, such as `linear_planning`?
- Should setup definitions remain code-owned for v1, or should we add a
  user-authored `workspace-setups.toml` after the first implementation proves
  the shape?
- Which messages are truly workspace-dependent collaboration and which are
  lower-level terminal diagnostics that should remain addressable by terminal
  ID?
- Do we need an explicit future bridge concept for agents that belong to
  different setups but are allowed to communicate through a user-approved
  gateway?

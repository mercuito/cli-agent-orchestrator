# CAO-91 Linear CAO Event Migration

Source of truth: Linear issue CAO-91.

## Scope

- Linear's six existing concrete events now publish through
  `cli_agent_orchestrator.events`.
- Linear event registration uses `published_cao_events()` and
  `default_cao_event_dispatcher()`.
- Webhook, monitor, runtime notification, workspace-context, and mediated
  `create_issue` tool-result paths consume the Linear CAO event types directly.

## Selected Criteria

- `full-verification-required`: this slice changes production code and needs
  focused plus broader proof.
- `minimal-cohesive-changes`: changes stay within Linear event migration,
  workspace context typing, provider registration, and directly proving tests.
- `no-unnecessary-duplication`: the Linear event builders remain the single
  source for event classification, CAO metadata, and participant roles.
- `respect-ownership-boundaries`: Linear-owned event vocabulary and role strings
  stay under `cli_agent_orchestrator.linear`; CAO owns only generic event
  primitives and dispatch.
- `respect-standing-decisions`: CAO-90 established `cli_agent_orchestrator.events`
  as the framework event core and explicitly forbade dual publication.
- `migration-discipline` and `no-assumed-backwards-compatibility`: Linear callers
  moved to the CAO dispatcher without old/new adapters or fallback dispatch.
- `semantic-continuity`: existing Linear classification, persistence,
  idempotency, notification, and workspace-context behavior stays on the same
  Linear parsing/runtime paths.
- `centralized-vocabulary`: Linear event types and participant role strings are
  declared in `linear.workspace_events`.
- `service-export-discipline`: no speculative public compatibility exports were
  added for old Linear event paths.
- `public-boundary-proof`, `test-through-owner-surfaces`,
  `verification-scope-discipline`, and `test-validity-preserved`: tests exercise
  Linear webhook, monitor, provider-tool, resolver, and runtime owner surfaces
  while preserving existing regression coverage.

## Legacy Provider Event Owner

`cli_agent_orchestrator.workspace_providers.events` remains only as the
workspace-provider-owned legacy dispatcher for non-Linear provider cleanup
phases. Linear production code does not import it, does not register through
`default_workspace_provider_event_dispatcher`, and does not publish adapters
back to `WorkspaceProviderEvent`.

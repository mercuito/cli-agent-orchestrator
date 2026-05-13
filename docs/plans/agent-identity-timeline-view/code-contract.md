# Feature-Level Code Contract — Agent Identity Timeline View

## Applicable Feature-Level Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [implementation-clause-verifiability](../../planning/methodology/criteria/feature-code-contract/implementation-clause-verifiability.md) | Each cross-task implementation commitment must name a concrete surface and verifiable compliance condition. |
| [stable-code-clause-ids](../../planning/methodology/criteria/feature-code-contract/stable-code-clause-ids.md) | Tasks and defences need stable `F-CC-<n>` slice identifiers. |

## Architectural Commitments

- `F-CC-1`: Backend dashboard identity reads continue to resolve configured
  agent identities through the manager-owned identity surface used by
  `/agents/identities`; the feature must not introduce a second identity
  discovery path for the dashboard.
- `F-CC-2`: Identity timeline and related-thread reads use the durable CAO
  event log surfaces and their participant, correlation, and causation
  lookups as the source of truth; feature code must not decide timeline
  membership by inspecting typed event bodies.
- `F-CC-3`: Frontend dashboard data access for this feature is added to
  `web/src/api.ts` and consumed through React dashboard code; feature
  components must not introduce ad hoc direct dashboard fetches.
- `F-CC-4`: The agent identity timeline experience extends the existing
  top-level Agents dashboard area rather than creating a second dashboard
  navigation surface for agent identities.
- `F-CC-5`: Dashboard source changes live under `web/src`; generated static
  assets under `src/cli_agent_orchestrator/web_ui` are updated only through
  the established frontend build output.
- `F-CC-6`: Live timeline refresh follows the dashboard's existing
  poll-and-reconcile pattern for changing dashboard state unless an upstream
  feature-level contract is amended to require a different live transport.

## Feature-Specific Code Obligations

No additional feature-specific code obligations are created beyond the
architectural commitments above. Task-level Coding Code Contracts will add
task-local obligations after code research.

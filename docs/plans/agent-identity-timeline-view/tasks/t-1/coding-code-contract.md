# Coding Code Contract — t-1

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| `F-CC-1` | Feature-level Code Contract | The backend identity timeline read surface must resolve configured identities through the same manager-owned identity surface as `/agents/identities`. |
| `F-CC-2` | Feature-level Code Contract | Timeline membership and related-thread membership must come from the durable CAO event log participant, correlation, and causation lookups. |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| [full-verification-required](../../../../planning/methodology/criteria/coding-code-contract/full-verification-required.md) | The task produces backend production code changes and has an exact Verification Command. |
| [red-green-refactor](../../../../planning/methodology/criteria/coding-code-contract/red-green-refactor.md) | The new API read surface is testable through route and event-store tests. |
| [boundary-and-failure-testing](../../../../planning/methodology/criteria/coding-code-contract/boundary-and-failure-testing.md) | The API accepts agent identity IDs and event IDs and must fail clearly for unknown identity/event inputs. |
| [semantic-continuity](../../../../planning/methodology/criteria/coding-code-contract/semantic-continuity.md) | The work extends existing `/agents/identities` dashboard identity routes and CAO event-store read paths. |
| [minimal-cohesive-changes](../../../../planning/methodology/criteria/coding-code-contract/minimal-cohesive-changes.md) | The task owns only the backend/API/event-read surface and must not implement UI or live-refresh work. |
| [no-unnecessary-duplication](../../../../planning/methodology/criteria/coding-code-contract/no-unnecessary-duplication.md) | The implementation will add serialization and service glue while reusing existing identity manager and event-store reads. |
| [respect-ownership-boundaries](../../../../planning/methodology/criteria/coding-code-contract/respect-ownership-boundaries.md) | The route layer, identity manager, event store, and task-specific timeline service are separate ownership surfaces. |
| [prefer-public-surfaces](../../../../planning/methodology/criteria/coding-code-contract/prefer-public-surfaces.md) | The API/service must consume identity and event-log behavior through public manager and event-store entrypoints. |
| [respect-standing-decisions](../../../../planning/methodology/criteria/coding-code-contract/respect-standing-decisions.md) | The feature committed-decision ledger is in force even though it is currently empty. |
| [readable-and-explicit](../../../../planning/methodology/criteria/coding-code-contract/readable-and-explicit.md) | Timeline filtering, role selection, and related-thread choices must be apparent from names and types. |
| [service-definition-surface](../../../../planning/methodology/criteria/coding-code-contract/service-definition-surface.md) | A focused backend read service will be introduced for identity timeline composition. |
| [service-export-discipline](../../../../planning/methodology/criteria/coding-code-contract/service-export-discipline.md) | Any new service exports must be required by the route consumer and not expose internal helpers. |
| [well-defined-service](../../../../planning/methodology/criteria/coding-code-contract/well-defined-service.md) | The task creates a service owner for dashboard identity timeline reads. |
| [no-test-only-production-seams](../../../../planning/methodology/criteria/coding-code-contract/no-test-only-production-seams.md) | New production seams must serve the dashboard read surface, not only the test harness. |

## Task-Specific Code Obligations

- `C-CC-1`: The identity timeline API must resolve the requested identity with `default_agent_identity_manager().status_for_identity(...)` before reading timeline data, returning `404` for manager resolution failures.
- `C-CC-2`: Timeline rows must expose envelope-level facts (`event_id`, `event_name`, `event_type_key`, `source_type`, `source_id`, `occurred_at`, `correlation_id`, `causation_id`) plus the selected identity's participant role from the event-store participant index.
- `C-CC-3`: Related-event reads must resolve the canonical event by ID, then use event-store correlation and causation lookup surfaces rather than inspecting typed event bodies.
- `C-CC-4`: The production service for this task must live in the backend identity/event read ownership area, keep route handlers thin, and expose only the consumer-facing methods used by the API routes.
- `C-CC-5`: The implementation must not change frontend dashboard code, live-refresh polling, generated web assets, or task artifacts for `t-2` or `t-3`.

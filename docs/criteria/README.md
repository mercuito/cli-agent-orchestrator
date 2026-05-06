# CAO Implementation And Test Criteria

This directory contains language-neutral criteria that implementers and
reviewers should apply to CAO code changes. The criteria are adapted for this
Python CAO repository so task handoffs can use stable review language instead
of inventing local standards each time.

## Catalogs

| Catalog | Use For |
| --- | --- |
| [coding-code-contract](coding-code-contract/README.md) | Production-code shape, modularity, ownership, migration discipline, duplication, env/global-state policy, service boundaries, and verification obligations. |
| [coding-test-contract](coding-test-contract/README.md) | Test proof quality, fixture/helper discipline, real-surface proof, public-boundary proof, test validity, and verification scope. |
| [external-integration-testing](external-integration-testing.md) | Extra criteria for external integrations such as Linear, GitHub, Jira, OAuth, webhooks, SDKs, GraphQL, and provider APIs. |

## Default Assignment Criteria

Every implementation handoff should include these criteria unless the work is
documentation-only:

Code criteria:

* `full-verification-required`
* `minimal-cohesive-changes`
* `no-unnecessary-duplication`
* `respect-module-boundaries`
* `readable-and-explicit`
* `respect-standing-decisions`, when a Linear issue or plan records active decisions

Test criteria:

* `test-validity-preserved`
* `verification-scope-discipline`
* `reusable-test-state`, when tests repeat setup state
* `test-through-owner-surfaces`, when tests depend on behavior owned by another subsystem
* `real-surface-proof-discipline`, when confidence depends on filesystem, process, HTTP, provider, parser, persistence, or other integration behavior

Add narrower criteria when the task touches the matching surface. For example:

* Use `environment-variable-policy` when code reads env vars or global runtime state.
* Use `migration-discipline` when code moves to a new service, API, config shape, or architecture.
* Use `no-test-only-production-seams` when tests motivate a new constructor option, hook, or helper.
* Use `public-boundary-proof` when a route, CLI command, MCP tool, API, config file, or exported module changes.
* Use `test-artifact-containment` when tests create files, directories, database rows, terminals, or external artifacts.
* Use `external-integration-testing` when the task touches Linear or another external provider.

## Implementer Prompt Requirement

When dispatching an implementer, point them to the issue or task definition and
to the applicable criteria paths. The prompt should require them to:

1. Select applicable criteria before coding.
2. Keep production behavior behind the owning module or provider boundary.
3. Avoid copying production logic into tests.
4. Use shared test helpers when repeated setup would make tests brittle.
5. Test through the owner surface for the behavior being proved.
6. Preserve existing test validity unless the issue explicitly changes the behavior.
7. Run focused proof and the broader verification command before completion.

## Reviewer Prompt Requirement

When dispatching a reviewer, require them to judge the implementation against:

* the issue/task definition;
* the selected criteria;
* this repository's existing module boundaries and test style.

Reviewers should treat weak tests as correctness risk when tests mock the
surface under test, duplicate authoritative behavior, or freeze local
implementation assumptions that should belong to production code.

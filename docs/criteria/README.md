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

## Selection Index

Use this index before opening every criterion file. Each row mirrors the
criterion `when` trigger so implementers and reviewers can quickly select the
criteria that apply to a task, then open only those specific files.

Code criteria:

| Criterion | Apply When |
| --- | --- |
| [authored-document-edit-preservation](coding-code-contract/authored-document-edit-preservation.md) | Code mutates user-authored persisted documents. |
| [boundary-and-failure-testing](coding-code-contract/boundary-and-failure-testing.md) | A service boundary accepts input or claims composition semantics. |
| [centralized-vocabulary](coding-code-contract/centralized-vocabulary.md) | Code introduces or changes named syntax other code references. |
| [environment-variable-policy](coding-code-contract/environment-variable-policy.md) | Code reads environment variables or global runtime state. |
| [filesystem-boundary-required](coding-code-contract/filesystem-boundary-required.md) | Production code performs filesystem I/O. |
| [full-verification-required](coding-code-contract/full-verification-required.md) | Any implementation task produces code changes. |
| [migration-discipline](coding-code-contract/migration-discipline.md) | Existing code moves to a new service, API, or architecture. |
| [minimal-cohesive-changes](coding-code-contract/minimal-cohesive-changes.md) | A task changes code outside pure refactor work. |
| [no-assumed-backwards-compatibility](coding-code-contract/no-assumed-backwards-compatibility.md) | Old callers or shapes could be preserved without an explicit contract requirement. |
| [no-test-only-production-seams](coding-code-contract/no-test-only-production-seams.md) | Tests motivate new or widened production surfaces. |
| [no-unnecessary-duplication](coding-code-contract/no-unnecessary-duplication.md) | Any implementation task adds code, helpers, fixtures, or abstractions. |
| [path-utils-required](coding-code-contract/path-utils-required.md) | Code constructs, resolves, joins, compares, or normalizes paths. |
| [prefer-public-surfaces](coding-code-contract/prefer-public-surfaces.md) | Code consumes another package, module, subsystem, or boundary-owned surface. |
| [readable-and-explicit](coding-code-contract/readable-and-explicit.md) | Any implementation task. |
| [red-green-refactor](coding-code-contract/red-green-refactor.md) | A task adds or changes testable behavior. |
| [respect-ownership-boundaries](coding-code-contract/respect-ownership-boundaries.md) | Code is added, moved, or restructured across files, packages, services, systems, or other ownership surfaces. |
| [respect-standing-decisions](coding-code-contract/respect-standing-decisions.md) | The feature has committed implementation decisions in force. |
| [semantic-continuity](coding-code-contract/semantic-continuity.md) | Code extends an existing variant, branch, subtype, or execution path. |
| [service-definition-surface](coding-code-contract/service-definition-surface.md) | A public or shared service class/module is created or reshaped. |
| [service-export-discipline](coding-code-contract/service-export-discipline.md) | A service module or package export surface changes. |
| [well-defined-service](coding-code-contract/well-defined-service.md) | The work creates, extracts, promotes, or substantially reshapes a service. |

Test criteria:

| Criterion | Apply When |
| --- | --- |
| [given-when-then-test-structure](coding-test-contract/given-when-then-test-structure.md) | Tests prove multi-step behavior. |
| [inspectable-authored-inputs](coding-test-contract/inspectable-authored-inputs.md) | A test supplies authored content that affects the assertion. |
| [public-boundary-proof](coding-test-contract/public-boundary-proof.md) | A task changes a public command, API, file format, export, or user boundary. |
| [real-surface-proof-discipline](coding-test-contract/real-surface-proof-discipline.md) | Confidence depends on an integration surface. |
| [reusable-test-state](coding-test-contract/reusable-test-state.md) | Tests repeat setup state across scenarios. |
| [setup-invariant-ownership](coding-test-contract/setup-invariant-ownership.md) | Tests require valid setup that is not the behavior under test. |
| [test-artifact-containment](coding-test-contract/test-artifact-containment.md) | Tests create files, directories, repos, persisted instances, or similar artifacts. |
| [test-file-organization](coding-test-contract/test-file-organization.md) | A test file covers multiple behavior families or public surfaces. |
| [test-through-owner-surfaces](coding-test-contract/test-through-owner-surfaces.md) | A test depends on behavior owned by another subsystem. |
| [test-validity-preserved](coding-test-contract/test-validity-preserved.md) | Always. |
| [verification-scope-discipline](coding-test-contract/verification-scope-discipline.md) | A task needs focused proof and a broader verification surface. |

External integration criteria:

| Criterion | Apply When |
| --- | --- |
| [external-integration-testing](external-integration-testing.md) | A change integrates CAO with an external system such as Linear, Jira, Discord, GitHub, OAuth providers, webhooks, SDKs, GraphQL APIs, or custom presence services. |

## Default Assignment Criteria

Every implementation handoff should include these criteria unless the work is
documentation-only:

Code criteria:

* `full-verification-required`
* `minimal-cohesive-changes`
* `no-unnecessary-duplication`
* `respect-ownership-boundaries`
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
2. Keep production behavior behind the owning system, service, provider, or other ownership boundary.
3. Avoid copying production logic into tests.
4. Use shared test helpers when repeated setup would make tests brittle.
5. Test through the owner surface for the behavior being proved.
6. Preserve existing test validity unless the issue explicitly changes the behavior.
7. Run focused proof and the broader verification command before completion.

## Reviewer Prompt Requirement

When dispatching a reviewer, require them to judge the implementation against:

* the issue/task definition;
* the selected criteria;
* this repository's existing ownership boundaries and test style.

Reviewers should treat weak tests as correctness risk when tests mock the
surface under test, duplicate authoritative behavior, or freeze local
implementation assumptions that should belong to production code.

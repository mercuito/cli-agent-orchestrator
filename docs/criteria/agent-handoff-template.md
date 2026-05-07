# Agent Handoff Criteria Template

Use this block when assigning CAO implementation work to an agent. Add or
remove narrow criteria based on the issue, but keep the defaults for any
code-changing task.

## Implementer Criteria Block

Use these criteria as part of the definition of done:

Code criteria:

* `docs/criteria/coding-code-contract/full-verification-required.md`
* `docs/criteria/coding-code-contract/minimal-cohesive-changes.md`
* `docs/criteria/coding-code-contract/no-unnecessary-duplication.md`
* `docs/criteria/coding-code-contract/respect-ownership-boundaries.md`
* `docs/criteria/coding-code-contract/readable-and-explicit.md`

Test criteria:

* `docs/criteria/coding-test-contract/test-validity-preserved.md`
* `docs/criteria/coding-test-contract/verification-scope-discipline.md`
* `docs/criteria/coding-test-contract/reusable-test-state.md`
* `docs/criteria/coding-test-contract/test-through-owner-surfaces.md`
* `docs/criteria/coding-test-contract/real-surface-proof-discipline.md`

Also apply these when relevant:

* `docs/criteria/coding-code-contract/environment-variable-policy.md`
* `docs/criteria/coding-code-contract/migration-discipline.md`
* `docs/criteria/coding-code-contract/no-test-only-production-seams.md`
* `docs/criteria/coding-test-contract/public-boundary-proof.md`
* `docs/criteria/coding-test-contract/test-artifact-containment.md`
* `docs/criteria/external-integration-testing.md`

Before finishing:

1. State which criteria applied and how the implementation satisfies them.
2. Keep repeated test setup behind named helpers or fixtures.
3. Avoid copying production logic into tests.
4. Test behavior through the owning public surface where practical.
5. Do not mock the behavior or integration surface being proven.
6. Preserve existing test validity unless the issue explicitly changes the target behavior.
7. Run focused tests and the broader verification command.

## Reviewer Criteria Block

Review against the issue definition of done and the criteria listed in the
implementer handoff.

Treat these as findings, not optional polish:

* production logic duplicated in tests;
* test fixtures that freeze behavior owned by production code;
* tests that mock the surface they claim to prove;
* repeated setup that should be a helper or fixture;
* provider or subsystem logic leaking outside its owner;
* legacy compatibility logic leaking beyond its named compatibility edge;
* missing focused proof or missing broader verification.

Findings must cite concrete files and line numbers.

---
name: claim-evidence-verifiability
when: Always.
---

# Claims Are Verifiable Against Their Evidence

Each defence entry's claim must be checkable against the named evidence —
test files, harness locations, fixture definitions, or test runs — without
inventing unstated criteria. If the link from claim to evidence requires
a leap, the evidence isn't concrete enough or the claim isn't actually
supported.

## Illustrations

**Bad — vague evidence pointer.** Claim: "Filesystem boundary is exercised
by real I/O." Evidence: "we have integration tests."
**Good:** Evidence: "`tests/integration/fs.test.ts:12` writes and reads a
real contained file via `tmp/test-<n>/`; mocks are not used."

**Bad — claim wider than evidence.** Claim: "All authored fixtures stay
inspectable." Evidence: "the new fixture is."
**Good:** Evidence enumerates the touched fixtures and shows each meets
`inspectable-authored-inputs`, or scopes the claim to those fixtures.

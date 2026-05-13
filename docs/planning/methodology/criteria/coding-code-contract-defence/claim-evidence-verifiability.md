---
name: claim-evidence-verifiability
when: Always.
---

# Claims Are Verifiable Against Their Evidence

Each defence entry's claim must be checkable against the named evidence —
code paths, file diffs, build/lint output, or other observable artifacts —
without inventing unstated criteria. If the link from claim to evidence
requires a leap, the evidence isn't concrete enough or the claim isn't
actually supported.

## Illustrations

**Bad — vague evidence pointer.** Claim: "Auth module owns the public
session API." Evidence: "see the auth package."
**Good:** Evidence: "`packages/auth/src/index.ts` exports
`createSession`, `validateSession`, `terminateSession`; no other package
exports session functions (verified by `rg 'export.*[Ss]ession'
packages/`)."

**Bad — claim wider than evidence.** Claim: "All path manipulation uses
the path utility." Evidence: "the new file uses it."
**Good:** Evidence enumerates the touched call sites and shows each uses
the utility, or scopes the claim to those call sites.

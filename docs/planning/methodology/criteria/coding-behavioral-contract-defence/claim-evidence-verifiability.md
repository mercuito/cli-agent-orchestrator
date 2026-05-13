---
name: claim-evidence-verifiability
when: Always.
---

# Claims Are Verifiable Against Their Evidence

Each defence entry's claim must be checkable against the named evidence —
tests, commands, or observable artifacts — without inventing unstated
criteria. If the link from claim to evidence requires a leap, the
evidence isn't concrete enough or the claim isn't actually supported.

## Illustrations

**Bad — vague evidence pointer.** Claim: "Login rejects invalid
credentials." Evidence: "auth tests cover this."
**Good:** Evidence: "`tests/auth/login.test.ts:42` — `rejects unknown
username with invalid-credentials outcome`."

**Bad — claim wider than evidence.** Claim: "Sessions expire correctly."
Evidence: "one passing test for the 30-minute case."
**Good:** Claim names the cases the evidence covers; broader behavior is
defended with additional evidence or split into narrower claims.

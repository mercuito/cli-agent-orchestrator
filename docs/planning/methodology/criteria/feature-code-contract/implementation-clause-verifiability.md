---
name: implementation-clause-verifiability
when: Always.
---

# Feature-Level Code Contract Clauses Are Verifiable

Every entry in the feature-level Code Contract — selected criteria,
feature-specific obligations, architectural targets, and any preamble
content — must state a verifiable, unambiguous obligation. Compliance must
be determinable from the entry alone, without inferring author intent.

Each entry names the surface, constraint, or obligation it governs and what
counts as compliance.

Vague directives that depend on unstated context are not contract material.

## Illustrations

**Bad - vague directive.** "The auth module is restructured for
maintainability."
**Good:** "The auth module's session lifecycle moves from
`packages/legacy-auth/src/handlers/` into a new `packages/auth/services/`
service-shaped boundary; existing callers migrate to the new public API."

**Bad - outcome without surface.** "Improve test coverage of the parser."
**Good:** "Tests for `parseRequest` cover every input shape listed in the
test contract; currently uncovered shapes are characterized before
refactoring."


---
name: caller-migration-policy
when: When the contract reshapes a surface that has existing callers in production code, tests, scripts, or external consumers.
---

# Caller Migration Policy Is Stated

For each reshaped surface with existing callers, the contract names
which callers migrate to the new shape within this feature and which
remain on the old shape. "All callers" is a valid policy when paired
with the discovery method the implementer uses to enumerate them (grep
pattern, type-checker error sweep, AST scan, etc.). The policy is
stated as a clause carrying an `F-CC-<n>` ID. The contract does not
omit the policy when the reshaped surface has callers.

## Illustrations

**Bad — caller scope implied.** The contract reshapes a public function
signature but says nothing about its existing call sites. An implementer
migrates the three callers most adjacent to their work and leaves four
others on a compatibility shim.
**Good:** A clause states "every caller of `parseRequest` in `src/` and
`test/` is migrated to the new signature; discovery is by `rg
'parseRequest\('` over those trees."

**Bad — "all callers" without discovery method.** "All callers are
migrated." An implementer interprets "all" as "all I noticed" and
misses two call sites that use the function indirectly through a
re-export.
**Good:** "All callers — enumerated by the type-checker error sweep
after the signature change lands — are migrated in this feature."

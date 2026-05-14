---
name: backward-compatibility-policy
when: When the contract reshapes the public surface, storage layout, or wire format of any existing code, whether as pure refactor or as part of behavior-changing work that includes a reshape.
---

# Backward-Compatibility Policy Is Stated

For each reshaped surface, the contract states whether backward
compatibility is permitted and in what form: translation shim, adapter
object, façade class, compatibility re-export, dual-shape storage,
parallel optional-additive field that preserves the old shape, or any
other mechanism that keeps the old shape reachable after the new one
lands. The policy is stated as a clause carrying an `F-CC-<n>` ID. The
contract does not omit the policy on a reshaped surface.

## Illustrations

**Bad — silent on a wire field.** The contract introduces a new `kind`
discriminator but says nothing about whether the response model retains
the old `event_type_key` field. An implementer keeps both, citing
minimal blast radius.
**Good:** A clause states "`event_type_key` is removed from every event
response model; no parallel field is added."

**Bad — adapter authorized by omission.** The contract migrates a class
hierarchy to Pydantic but does not address whether an adapter can
present the old shape to existing callers. An implementer adds
`LegacyEventAdapter` "to limit caller churn."
**Good:** A clause states "no adapter presents the old class shape;
callers are migrated within this feature."

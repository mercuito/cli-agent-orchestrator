---
name: replaced-surface-lifecycle-policy
when: When the contract replaces an existing code, storage, or wire-format surface with a new shape.
---

# Replaced-Surface Lifecycle Policy Is Stated

For each surface the contract replaces, the contract states the
surface's lifecycle outcome at feature end: removed entirely, retained
as a deprecated-but-kept symbol, retained as production code alongside
the replacement, or retained for a named number of follow-up features
before removal. The policy is stated as a clause carrying an `F-CC-<n>`
ID. The contract does not omit the policy on a replaced surface.

## Illustrations

**Bad — lifecycle implied but not stated.** The contract introduces a
new serializer and describes its shape but says nothing about the old
serializer's fate. An implementer leaves the old one in place with a
`# TODO: remove` comment.
**Good:** A clause states "the old serializer module is deleted in this
feature; a `# deprecated` annotation is not used as a substitute for
deletion."

**Bad — vague lifecycle.** "The old API will be phased out over time."
The implementer interprets "over time" as "not now" and ships parallel
implementations.
**Good:** "The old API endpoint is removed at the close of this feature;
no follow-up feature inherits the removal."

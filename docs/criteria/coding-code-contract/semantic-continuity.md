---
name: semantic-continuity
when: Code extends an existing variant, branch, subtype, or execution path.
---

# New Paths Preserve Existing Semantics

An added path must go through the same validation, normalization, lifecycle,
state, and reporting logic as comparable existing paths unless the in-force
contract justifies divergence.

The path being extended must be understood before any parallel
implementation is added.

## Illustrations

**Bad - parser-only extension.** A parser accepts a new config field, but the
runtime still reads the old field.
**Good:** The new field flows through the same runtime path as existing
configuration.

**Bad - duplicate pipeline.** A new variant bypasses existing validation.
**Good:** The variant enters the shared validation pipeline or documents a
contracted divergence.


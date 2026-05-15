---
name: test-through-owner-surfaces
when: A test depends on behavior owned by another subsystem.
---

# Tests Use Owner Surfaces For Owned Behavior

When setup, behavior, state, parsing, persistence, discovery, or side effects
belong to another subsystem, tests must use that subsystem's public owner
surface instead of duplicating its internals.

If the owner surface is unavailable or out of scope, the test contract must
name the substitute and the risk.

## Illustrations

**Bad - duplicated parser.** A test builds parsed schema objects by hand while
depending on schema parser behavior.
**Good:** The test uses the schema parser or catalog owner surface.

**Bad - fake discovery.** A workspace-provider discovery test manually creates
accepted provider records that belong to the provider registry.
**Good:** The test goes through the provider registry or documented owner
surface.

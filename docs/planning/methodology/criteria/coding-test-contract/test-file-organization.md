---
name: test-file-organization
when: A test file covers multiple behavior families or public surfaces.
---

# Test Files Are Organized By Behavior

Test files must remain navigable. When a file covers multiple behavior
families, public surfaces, or scenario groups, it must group or split tests by
behavior so any reader can find coverage without scanning unrelated cases.

Large files may remain together only when the organization makes the shared
context clearer than a split.

## Illustrations

**Bad - mixed scenario bucket.** One file interleaves parsing, persistence,
CLI, and error-reporting tests.
**Good:** Tests are grouped or split by behavior family or public surface.

**Bad - size justified by convenience.** A file stays large because adding a
new file is slower.
**Good:** The file either splits or explains the cohesive shared context.


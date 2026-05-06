---
name: service-definition-surface
when: A public or shared service class/module is created or reshaped.
---

# Service Definition Is Easy To Scan

A public or shared service must have an obvious definition surface where a
reader can find the service API, public method signatures, input/config types,
and service-owned tokens or config keys.

Internal machinery must not bury the public service surface. Large or
independent internals must be extracted or grouped by concern.

## Illustrations

**Bad - API buried.** A service file starts with rollback helpers and parsers;
the exported class appears hundreds of lines later.
**Good:** The service definition is grouped near the top or placed in a clear
definition file, with internals in focused modules.

**Bad - bucket file.** Loading, parsing, mutation, reporting, and rollback all
grow in one service file.
**Good:** Internals are split or grouped by concern while the public surface
stays obvious.


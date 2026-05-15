---
name: filesystem-boundary-required
when: Production code performs filesystem I/O.
---

# Filesystem I/O Uses The Owning Boundary

Production code outside the filesystem owner must not use raw host filesystem
APIs directly. Runtime-managed code must obtain filesystem behavior at the host
edge and pass the filesystem boundary inward.

If the shared filesystem contract lacks a needed operation, extend the owning
boundary instead of adding a raw-I/O escape hatch.

## Illustrations

**Bad - raw command I/O.** A CLI command calls `Path.read_text()` directly to
read a config file owned by a config-loading boundary.
**Good:** The command receives or resolves the designated filesystem boundary
and uses that surface.

**Bad - helper becomes host owner.** A reusable helper imports `Path` and
opens user files directly.
**Good:** The helper accepts filesystem behavior or already-loaded content
from its caller.

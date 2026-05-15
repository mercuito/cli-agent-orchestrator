---
name: public-boundary-proof
when: A task changes a public command, API, file format, export, or user boundary.
---

# Public Boundaries Are Proven Directly

Tests must exercise the same public boundary a real user or downstream
consumer uses. Lower-level helper tests are not enough when the task changes
exports, commands, adapters, file formats, or routing surfaces.

Detailed behavior matrices may stay near implementation internals; public
boundary proof only needs enough behavior to fail if the front door is broken.

## Illustrations

**Bad - internal import.** A public API changes, but tests import an internal
helper module directly.
**Good:** A smoke test uses the public module, CLI command, HTTP route, MCP
tool, or config entrypoint and proves it delegates to the implementation.

**Bad - metadata-only proof.** A test inspects route registration or config
metadata but never invokes the public entrypoint.
**Good:** The test imports or invokes the entrypoint users depend on.

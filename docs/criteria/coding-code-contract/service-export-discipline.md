---
name: service-export-discipline
when: A service module or package export surface changes.
---

# Service Exports Are Consumer-Facing

Every public module export, package export, and documented import path must be
required by an existing consumer or by the in-force Code Contract. Service
exports must expose only service-shaped API: service entrypoints, tokens,
modules, owned config keys, and consumer-facing types.

Internal helpers, migration scaffolding, test-only types, and convenience
exports must not be public.

## Illustrations

**Bad - helper export.** A parsing helper is exported from a service root so a
migration task can reuse it.
**Good:** The helper stays internal, or a consumer-facing service method is
designed and justified.

**Bad - speculative import path.** A public import path is added because future
tasks might need it.
**Good:** Public import paths are added only when a current consumer or
contract requires them.

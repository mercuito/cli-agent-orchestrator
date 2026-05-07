---
name: respect-ownership-boundaries
when: Code is added, moved, or restructured across files, packages, services, systems, or other ownership surfaces.
---

# Ownership Boundaries Stay Coherent

Changed code must preserve or improve coherent ownership boundaries. An
ownership boundary is the smallest code owner a reader has to understand: a
package, file, class, function group, service, provider, domain system, or other
local code surface.

When one system consumes another system, consumer-specific code belongs with the
consuming system, not with the dependency it consumes.

Use this test:

1. Would this code still exist if the consuming system did not exist?
2. If no, place it under the consuming system's owner surface.
3. If yes, it may belong with the dependency or shared infrastructure owner.

The dependency owns the generic capability it provides to all consumers:
primitives, registries, base classes, execution hooks, generic utilities, and
cross-consumer invariants. It must not absorb consumer workflows merely because
those workflows call into it.

A file must not become a bucket of unrelated domain concerns merely because the
concerns share a technical substrate. "All of this talks to the database",
"all of this is HTTP", or "all of this is CLI code" is not enough cohesion when
the file contains separate domain workflows, invariants, and change reasons.

When separable concerns begin to grow, extract a coherent owner surface instead
of adding more unrelated logic. Co-location is acceptable only when the code has
a single owner or when keeping it together makes a cross-consumer invariant more
obvious than a split would.

## Illustrations

**Bad - responsibility bucket.** A command file grows parsing, validation,
filesystem mutation, and reporting logic.
**Good:** The command delegates to focused owner surfaces.

**Bad - shared substrate bucket.** A database file owns terminal metadata,
inbox delivery semantics, monitoring sessions, baton persistence, flow
schedules, provider presence rows, and migration decisions because they all use
SQLAlchemy.
**Good:** Shared database setup stays central, while domain persistence surfaces
move behind focused owners such as terminal, inbox, baton, flow, or presence
repositories.

**Bad - infrastructure ownership overrules domain ownership.** A messaging
system adds its persistence functions to the generic database file because the
functions use database sessions.
**Good:** The database layer owns sessions and transaction helpers; the
messaging system owns its message tables, repositories, invariants, and
messaging-specific migration declarations.

**Bad - unexplained co-location.** Two unrelated helpers are added to an
existing file because it was nearby.
**Good:** Each helper goes to its owner, or co-location is justified.

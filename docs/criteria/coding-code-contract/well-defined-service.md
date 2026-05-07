---
name: well-defined-service
when: The work creates, extracts, promotes, or substantially reshapes a service.
---

# Service Ownership And Boundary Are Explicit

The Code Contract clause must state whether the work creates a well-defined
service or an intentionally internal service seam. A well-defined service must
have an explicit owner, architectural home, boundary, and public surface
appropriate to repository service conventions.

Internal service seams must be named as internal and defended as such.

## Illustrations

**Bad - ambiguous helper service.** A reusable service remains inside an
unrelated command module with no owner.
**Good:** The service moves to its owning surface/package or the contract states
it is an internal seam.

**Bad - service by name only.** A class named `ThingService` has no defended
boundary or consumer contract.
**Good:** The clause names its owner, consumers, and boundary.

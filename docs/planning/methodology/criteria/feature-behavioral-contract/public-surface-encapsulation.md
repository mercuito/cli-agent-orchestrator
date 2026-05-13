---
name: public-surface-encapsulation
when: A service wraps a third-party runtime, library, or platform.
---

# Encapsulation Is Proven At The Wrapper Surface

The behavioral contract must express encapsulation as a property of the
wrapping service's public surface. Consumers using that surface must not need
third-party runtime types, objects, functions, or imports.

The contract must not rely on a rule about what other services may import as
the only proof of encapsulation.

## Illustrations

**Bad - lint-only boundary.** The contract says no other service may import the
host API.
**Good:** The wrapper's exported types, parameters, and return values expose
only service-owned abstractions.

**Bad - wrapped object leak.** A method returns a proxy that still exposes the
wrapped runtime object.
**Good:** Returned values are plain data or service-owned wrappers with no
runtime-object access.


---
name: no-test-only-production-seams
when: Tests motivate new or widened production surfaces.
---

# Production Seams Serve Production Needs

Production constructors, options, hooks, adapters, exports, and helpers may be
added or widened only for a production behavior or contracted architecture.
They must not exist solely to make tests easier.

Test-only flexibility belongs in test harnesses, fixtures, or internal test
helpers unless the in-force contracts require a production extension point.

## Illustrations

**Bad - test hook exported.** A service exports `createUnsafeForTest()` so
tests can bypass initialization.
**Good:** Tests use a test-owned harness, or the contract names a real
production initialization option.

**Bad - production option for fixture speed.** A constructor option disables
validation only for tests.
**Good:** Tests build valid fixtures or use a test-only helper outside the
production surface.


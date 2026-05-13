---
name: environment-variable-policy
when: Code reads environment variables or global runtime state.
---

# Environment Reads Stay At The Boundary

Environment variables and mutable global runtime state must be read at an
application or test boundary, captured into an explicit context/config object,
and passed inward. Leaf services, utilities, helpers, and module initializers
must not read `os.environ` or equivalent globals directly.

Tests must provide context/config values instead of mutating global state for
leaf code.

## Illustrations

**Bad - leaf read.** A parser helper reads `os.environ["CAO_MODE"]` during
normal operation.
**Good:** The CLI reads the environment once and passes `mode` through config.

**Bad - global test setup.** A test mutates `os.environ` to affect a service.
**Good:** The test constructs the service with an explicit context value.

---
name: real-surface-proof-discipline
when: Confidence depends on an integration surface.
---

# Integration Risk Uses Real Surface Proof

When risk lives at a filesystem, process, HTTP route, MCP tool, database,
runtime, parser, provider API, or other integration boundary, tests must
exercise that real surface enough to prove the contract. Mocks may isolate
collaborators, but they must not replace the surface whose behavior is under
test.

If the real surface cannot run in the test environment, the test contract must
name the closest feasible check and the remaining risk.

## Illustrations

**Bad - mocked filesystem only.** A task changes persisted file behavior but
tests only mock read/write calls.
**Good:** A focused test writes and reads real contained files.

**Bad - fake route boundary.** A route change is tested only by calling the
internal handler helper directly.
**Good:** The test invokes the public route through the API test client.

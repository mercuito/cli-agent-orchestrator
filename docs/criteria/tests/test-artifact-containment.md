---
name: test-artifact-containment
when: Tests create files, directories, repos, persisted instances, or similar artifacts.
---

# Test Artifacts Stay Contained

Tests that create real artifacts must keep them inside an owned, isolated
location and clean them up through the test harness or scoped lifecycle. Tests
must not write into shared repo paths, user paths, or process-global locations
unless that path is the behavior under test and is isolated.

Artifact paths passed between phases must be explicit.

## Illustrations

**Bad - shared output.** A test writes generated files into the repository's
real docs directory.
**Good:** The test writes under a scoped temp root owned by the test.

**Bad - hidden path.** Assertions read from a path implied by global state.
**Good:** Setup returns the artifact path and Then reads that path.


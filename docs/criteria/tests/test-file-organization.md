---
name: test-file-organization
when: Always.
---

# Test Files Mirror Their Target's Organization
Test files are organized in a directory structure that mirrors the organization of the production code they test. This means that tests for a specific module, component, or feature are located in a corresponding directory within the test suite. This organization promotes discoverability and maintainability by making it easy to locate tests related to specific parts of the codebase.


## Illustrations

### Mirroring The Source Tree

```markdown
plan.md
# Add tests for the new `cao.flow.scheduler` module
- [ ] Place tests under the matching directory in `tests/`
...
```

**Bad - flat or unrelated layout.** Tests for many modules pile into a
single directory or live under a layout that does not mirror the source
tree, so finding the test for a given module requires searching.

```
cao/
  flow/
    scheduler.py
    storage.py
  supervisor/
    runtime.py

tests/
  test_everything.py           # Bad: many unrelated targets in one file
  test_misc.py                 # Bad: catch-all
  scheduler_tests.py           # Bad: no parallel to cao/flow/
```

**Good:** The test layout mirrors the source layout, so the test file for
a module sits in the predictable place.

```
cao/
  flow/
    scheduler.py
    storage.py
  supervisor/
    runtime.py

tests/
  flow/
    test_scheduler.py
    test_storage.py
  supervisor/
    test_runtime.py
```

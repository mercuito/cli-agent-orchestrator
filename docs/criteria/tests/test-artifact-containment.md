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

### Writing Inside The Test's Temp Directory

```markdown
plan.md
# Verify the session log is written to disk and can be read back
- [ ] Test that `write_log` appends to the configured log path
...
```

**Bad - hardcoded shared path.** The test writes to a `/tmp` or repo-
relative path. Parallel runs collide, and the file leaks between tests.

```python
def test_write_log_appends_line():
    write_log("/tmp/cao-log", "hello")  # Bad: shared path

    assert Path("/tmp/cao-log").read_text().endswith("hello\n")
```

**Good:** The test path comes from the harness; cleanup is automatic.

```python
def test_write_log_appends_line(tmp_path):
    log_path = tmp_path / "session.log"

    write_log(log_path, "hello")

    assert log_path.read_text().endswith("hello\n")
```

### Passing Artifact Paths Explicitly Between Phases

**Bad - implicit path.** A helper sets up a repo at a well-known location
and later phases retrieve it from there by convention.

```python
def setup_repo():
    repo = Path.home() / ".cao-test-repo"  # Bad: implicit, shared
    repo.mkdir(exist_ok=True)
    # caller is expected to "know" where the repo is

def test_review_runs_against_repo():
    setup_repo()
    result = review()
    assert result.ok
```

**Good:** The path is returned and threaded through.

```python
def setup_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    return repo

def test_review_runs_against_repo(tmp_path):
    repo = setup_repo(tmp_path)

    result = review(repo=repo)

    assert result.ok
```


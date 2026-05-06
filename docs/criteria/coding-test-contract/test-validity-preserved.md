---
name: test-validity-preserved
when: Always.
---

# Tests Continue To Validate Their Target Behavior

After any code change, every existing test must still pass and must still
correctly validate the same target behavior it validated before.

A test's implementation may be refactored — extracting helpers, restructuring
setup, renaming locals — as long as the test's target behavior and the
integrity of its proof are preserved.

A test's assertions, target surface, or proof scope may change only when a
behavioral contract change names the new target. Without that contract change,
existing tests are the authoritative spec; their assertions are not open
to modification.

## Illustrations

**Bad - real surface mocked away.** A test of a filesystem operation is
"refactored" to mock the filesystem layer. The test now passes by exercising
the mock, not the real behavior under test.
**Good:** Setup is extracted into a helper; the test still exercises the
real filesystem.

**Bad - unsupported assertion change.** Implementation changes how an error
is wrapped; the test is updated to assert the new wrapper without a
behavioral contract change naming it.
**Good:** The error wrapping is recognized as user-visible; a behavioral
contract amendment names the new assertion before the test changes.

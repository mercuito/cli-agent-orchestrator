---
name: boundary-and-failure-testing
when: A service boundary accepts input or claims composition semantics.
---

# Boundary And Failure Cases Are Tested

The implementation must test realistic invalid, empty, conflicting, boundary,
or composition cases for every affected boundary that accepts authored or
runtime input.

A happy-path test is insufficient when the task claims behavior such as merge,
ordering, selection, parsing, validation, or failure signaling.

## Illustrations

**Bad - merge happy path.** A merge function is tested with one source only.
**Good:** A test uses two sources with overlapping keys and proves the selected
precedence rule.

**Bad - error mode untested.** The implementation defines invalid-input
failure but no test triggers invalid input.
**Good:** A focused test exercises the invalid input and asserts the specified
failure outcome.


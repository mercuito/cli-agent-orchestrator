---
name: operation-outcome-signaling
when: A public operation reports structured outcomes.
---

# Public Outcome Signals Are Explicit

The behavioral contract must define every structured outcome a public
operation can return or emit: success, failure, diagnostics, partial success,
per-item results, and retry or continuation signals.

Outcome fields must have domain meaning. The contract must distinguish
operation-level failure from per-item failure when both can occur.

## Illustrations

**Bad - unexplained flag.** The contract says `ok` is false but not what
failure means or what remains applied.
**Good:** The contract defines operation failure, no mutation, and a diagnostic
that names the rejected input.

**Bad - flattened partial failure.** A batch operation returns failure when
one item fails, with no per-item outcome.
**Good:** The contract defines which items succeeded, which failed, and the
overall operation status.


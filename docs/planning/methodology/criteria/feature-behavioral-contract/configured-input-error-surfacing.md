---
name: configured-input-error-surfacing
when: Users provide inputs the system loads, resolves, validates, or executes.
---

# Invalid Configured Inputs Surface Clearly

The behavioral contract must specify how invalid user-provided inputs are
reported. It must identify the rejected input, the failure outcome, and whether
any partial mutation or partial admission is allowed.

Configured inputs include manifests, config entries, file paths, directories,
named registrations, and user-chosen references.

## Illustrations

**Bad - generic failure.** Given an invalid manifest, then loading fails.
**Good:** Given a manifest with an unknown handler reference, then admission
rejects that manifest, reports the unknown reference, and admits no surfaces
from it.

**Bad - hidden partial success.** Invalid entries are skipped without a defined
diagnostic.
**Good:** The contract defines whether invalid entries reject the whole input
or produce per-item diagnostics.


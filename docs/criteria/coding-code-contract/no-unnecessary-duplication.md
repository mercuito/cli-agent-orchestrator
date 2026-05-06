---
name: no-unnecessary-duplication
when: Any implementation task adds code, helpers, fixtures, or abstractions.
---

# Existing Suitable Code Is Reused

Before adding new code, search for existing functions, constants, helpers,
fixtures, and abstractions that satisfy or nearly satisfy the need. Reuse
or extend suitable existing code instead of duplicating logic.

Small idioms may remain inline when extraction would obscure intent. Repeated
logic, vocabulary, and multi-step behavior must not be copied.

## Illustrations

**Bad - duplicated constant.** A test defines `DEFAULT_TIMEOUT = 5000` instead
of importing the existing constant.
**Good:** The test imports the shared timeout source.

**Bad - copied validation.** Two services implement the same field validation
with separate branches.
**Good:** Shared validation is reused or extracted.


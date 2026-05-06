---
name: authored-document-edit-preservation
when: Code mutates user-authored persisted documents.
---

# Authored Document Edits Preserve Unrelated Content

Document mutations must change only the authored content required by the task.
Unrelated fields, comments, ordering, formatting, and valid empty containers
must survive unless the behavioral contract explicitly requires cleanup.

When narrow preservation is impractical, the Code Contract must name the
allowed rewrite scope before coding.

## Illustrations

**Bad - broad rewrite.** A config migration rewrites the whole YAML file and
drops unrelated keys.
**Good:** The migration edits only the renamed key and preserves unrelated
authored content.

**Bad - implicit cleanup.** Empty sections are deleted because they look
unused.
**Good:** Empty sections are preserved unless the contract requires removal.


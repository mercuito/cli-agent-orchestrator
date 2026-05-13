---
name: path-utils-required
when: Code constructs, resolves, joins, compares, or normalizes paths.
---

# Path Operations Use Path Utilities

Path manipulation must use the repository's designated path utilities rather
than raw host path APIs in consumer code. This includes joins, resolution,
normalization, relative paths, dirname/basename logic, and path comparison.

Exceptions belong only in the path utility owner or in designated host-boundary
code.

## Illustrations

**Bad - mixed path APIs.** One module builds a path with string concatenation
while another uses the project utility, producing different normalization.
**Good:** Both modules use the same designated path utility.

**Bad - string path building.** Code creates paths with template strings and
manual separators.
**Good:** Code uses the path utility for construction and comparison.

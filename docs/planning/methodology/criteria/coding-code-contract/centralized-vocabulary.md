---
name: centralized-vocabulary
when: Code introduces or changes named syntax other code references.
---

# Named Syntax Has One Source

Named syntax such as CLI flags, config keys, mode values, persisted field
names, command names, and public string identifiers must have one authoritative
source in code. Other code must import or derive from that source rather than
hard-coding disconnected literals.

Any intentional duplicate ownership must be documented at the divergence point.

## Illustrations

**Bad - scattered literals.** `"remote"` appears in parser, tests, and docs as
separate string literals.
**Good:** Parser, tests, and docs derive the value from one exported constant
or enum.

**Bad - grep migration.** A rename requires changing unrelated files by text
search.
**Good:** The rename changes the authoritative source and consumers update
through imports or generated surfaces.


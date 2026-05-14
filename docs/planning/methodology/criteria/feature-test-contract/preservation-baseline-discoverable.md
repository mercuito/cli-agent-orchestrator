---
name: preservation-baseline-discoverable
when: When the feature-level Test Contract names a preservation baseline of existing tests that must continue to validate their original target behavior.
---

# Preservation Baseline Is Discoverable

When the contract names a preservation baseline, it either enumerates
the baseline tests by file path or names a discovery method (an `rg`
pattern, a marker decorator, a directory scan) the implementing task
runs to produce the enumeration. The baseline is verifiable: a reviewer
determines which tests must remain green at every task boundary
without inferring author intent.

When a baseline test file is reshaped, removed, or split during the
feature, the contract is amended; the baseline is not extended or
shrunk silently by a task.

## Illustrations

**Bad — baseline named by adjective.** "The existing event-persistence
and timeline tests form the preservation baseline." An implementer
keeps the tests they noticed green and is surprised when CI flags a
third file they did not consider part of the baseline.
**Good:** "Preservation baseline is the union of
`test/events/test_cao_event_persistence.py`,
`test/api/test_agent_identity_routes.py`,
`test/runtime/test_agent_runtime.py`, and
`web/src/test/agent-identity-timeline-panel.test.tsx`. Additions to
this list during the feature amend the contract."

**Bad — discovery method without anchor.** "All event-driven tests."
The implementer interprets "event-driven" by feel and gets a different
list than the planner intended.
**Good:** "Preservation baseline is every test file under
`test/events/` plus every test file matching
`rg -l 'CaoEvent|event_type_key' test/`; the discovery command is run
at task start and its output is recorded in the Coding Test Contract."

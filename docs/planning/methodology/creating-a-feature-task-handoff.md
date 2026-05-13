# Creating a Feature Task Handoff

## Purpose

The Feature Task Handoff is the per-task assignment packet. It points at
the task's slice entry in the
[Feature Tasks](./creating-a-feature-tasks.md) artifact (which owns the
slice IDs), references the committed-implementation-decisions artifact,
and provides the Verification Command and coding-level artifact paths —
everything needed to start research and drafting the Coding Implementation
Plan.

A Feature Task Handoff exists per task. The Feature Tasks artifact owns
the slice assignments across the whole feature; the per-task handoff is
the operational packet that turns one slice entry into a startable task.

## What it contains

A handoff has the following sections.

### Task brief

A concise statement of the task's intent in domain terms — what the task
exists to accomplish and what done looks like at a high level. This is not
a redraft of the behavioral or code contract; it is the orientation read
first.

### Slice reference

A pointer to the task's entry in the Feature Tasks artifact, which owns
the assigned Behavioral / Code / Test slice IDs. The handoff does not
restate the slice IDs — the Feature Tasks entry is the single source of
truth for what this task is responsible for satisfying.

The slices are resolved by reading the referenced entry. The universal
`test-validity-preserved` criterion applies regardless of whether a
feature-level Test Contract slice is assigned.

### Committed implementation decisions

A reference to the feature's committed-implementation-decisions artifact.
All entries in that artifact are in force for every task; the handoff
does not curate a subset and does not restate IDs. The master document is
read directly and the task remains compatible with every entry.

### Verification Command

The exact command (or command sequence) that must run successfully before
authoring the Coding Completion Report. The handoff names the command
verbatim. If the command is unclear or unavailable, the task is reported
as `blocked` rather than substituted with a different command.

### Coding-level contract pointers

The handoff names where the Coding Code Contract and Coding Test Contract
will be created — the deterministic task-level paths under
`docs/plans/<feature>/tasks/t-<n>/`. The handoff does not contain those
contracts; it points at where they will live and signals that drafting
them is part of the task.

### Supporting references

When the task entry says supporting references are required, the handoff
provides the concrete references the implementer must inspect during
research before drafting the Coding Implementation Plan. References may
include UI designs, screenshots, Figma frames, Storybook stories, routes,
component files, product notes, domain examples, existing implementation
patterns, or other inspectable material.

Each reference must name what it is and how it applies. Do not use vague
entries such as "follow the design" or "match existing UI." If a required
reference is unavailable, the handoff explains the gap directly so the
task can be blocked, revised, or clarified before implementation begins.

## What it does not contain

- The slice IDs themselves (those live in `tasks.md`; the handoff
  references them).
- The full text of feature-level contracts (reference clauses by ID).
- Plan, code, tests, or evidence — those are produced later in the coding
  phase.
- Coding-level criteria selections — those live in the Coding Code
  Contract and Coding Test Contract.
- New design decisions. Supporting references orient research; they do
  not replace the Feature Narrative, contracts, or task slices.

## Document organization

```markdown
# Feature Task Handoff: t-<n> — <short title>

## Task Brief

(One paragraph in domain terms.)

## Slice Reference

See `../tasks.md#t-<n>` for assigned Behavioral, Code, and Test slices.
The universal `test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/<feature>/committed-implementation-decisions.md`. All
entries are in force.

## Supporting References

Use these references during task research and implementation planning.

### UI / Design References

- `<path or URL>`: <what it shows and how it applies>

### Product / Domain References

- `<path or URL>`: <why it matters>

### Existing Code References

- `<path/component/module>`: <relevant existing pattern>

## Verification Command

```
<exact command or command sequence>
```

## Coding-Level Contract Locations

- Coding Code Contract: `docs/plans/<feature>/tasks/t-<n>/coding-code-contract.md`
- Coding Test Contract: `docs/plans/<feature>/tasks/t-<n>/coding-test-contract.md`
```

## Applicable criteria

Browse the [feature task handoff criteria catalog](./criteria/feature-task-handoff/README.md)
and select the criteria that apply. Add an `Applicable Criteria` table near
the top of the handoff with one-line rationale per selection.

## Artifact path

`docs/plans/<feature>/tasks/t-<n>/feature-task-handoff.md`

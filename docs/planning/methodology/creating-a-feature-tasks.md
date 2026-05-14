# Creating a Feature Tasks Artifact

## Purpose

The Feature Tasks artifact (`feature-tasks.md`) enumerates the tasks the feature
will be implemented through. It carries each task's stable ID, brief
scope, and the slice IDs the task owns from the feature-level contracts.

It is **the authoritative source for slice ownership** across the
feature: which task owns which behavior, which Code Contract clause,
which Test Contract clause. The
[Feature Task Handoff](./creating-a-feature-task-handoff.md) is the
operational packet that turns one task entry into a startable assignment;
it references this artifact rather than restating the slices.

## When authored

After the feature-level contracts are stable enough to slice into tasks.
Updated only when the task list itself changes (tasks added, removed,
renumbered, or merged) or when slices are reissued.

## What it contains

For each task:

- a stable ID of the form `t-<n>`
- a short title in domain terms
- a one or two sentence scope summary — what the task delivers, not how
- the task's **slices from the feature-level contracts**, by ID:
  - Behavioral Contract slice — the behavior and constraint IDs the task
    owns, or an explicit "no Behavioral Contract slice: <reason>"
  - Code Contract slice — the feature-level Code Contract clause IDs the
    task owns, or an explicit "no Code Contract slice: <reason>"
  - Test Contract slice — the feature-level Test Contract clause IDs the
    task owns, or an explicit "no Test Contract slice: <reason>" (or a
    note that no feature-level Test Contract exists)
- supporting-reference acknowledgment — whether the task requires UI,
  design, product, domain, or existing-code references in its handoff, or
  an explicit "no supporting references required: <reason>"
- explicit dependency notes when one task must land before another

For the artifact as a whole:

- a brief intro pointing at the feature's contract artifacts so a reader
  can resolve any referenced slice ID
- nothing else — the task list is an index, not a planning document

The slices are referenced by ID only; clause text is never restated. A
reader resolves an ID by opening the named contract artifact.

## What it does not contain

- the full handoff for any task (that is the Feature Task Handoff)
- restatement of behavior, constraint, or contract clause text
- coding-side details (research findings, plan, code obligations)
- the per-task Verification Command and coding artifact paths (those live
  in the Feature Task Handoff)
- concrete UI designs, screenshots, product docs, or code references
  (the task entry only acknowledges whether the handoff must provide them)

## Document organization

```markdown
# Feature Tasks — <feature>

Feature Tasks for the <feature> feature. See `feature-behavioral-contract.md`,
`feature-code-contract.md`, and `feature-test-contract.md` for the slice IDs referenced
below.

## t-1 — <short title>

<One or two sentences of scope.>

- Behavioral slice: `B-1`, `B-3`, `C-2`
- Code slice: `F-CC-1`, `F-CC-4`
- Test slice: `F-TC-1`
- Supporting references: required for UI layout and interaction details

(Optional: depends on `t-<n>`.)

## t-2 — <short title>

<One or two sentences of scope.>

- Behavioral slice: no Behavioral Contract slice for this task: pure
  refactor work.
- Code slice: `F-CC-2`, `F-CC-3`
- Test slice: no feature-level Test Contract exists; universal
  `test-validity-preserved` applies.
- Supporting references: no supporting references required: pure
  backend refactor with no UI, product, domain, or prior-pattern reference
  dependency.

...
```

## Applicable criteria

Browse the [feature tasks criteria catalog](./criteria/feature-tasks/README.md)
and select the criteria that apply. Add an `Applicable Criteria` table near
the top of the artifact with one-line rationale per selection.

## Artifact path

`docs/plans/<feature>/tasks/feature-tasks.md`

The artifact is the Feature Tasks index; the filename keeps the `feature-`
prefix to mark it as a feature-level planning artifact.

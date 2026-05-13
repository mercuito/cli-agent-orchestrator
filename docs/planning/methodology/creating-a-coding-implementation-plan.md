# Creating a Coding Implementation Plan

## Purpose

The Coding Implementation Plan is the task-level approach for one
assigned task. It explains how the task will satisfy its assigned slices
of the feature-level Behavioral Contract (when one exists), Code Contract,
and Test Contract (when one exists), together with the task-level Coding
Code Contract and Coding Test Contract authored during planning.

The plan is provisional during the task. It may be revised through the
revision log when implementation findings demand it.

---

## Inputs

The plan is drafted from:

- the Feature Task Handoff (slice reference into `tasks.md`, Verification
  Command, committed-implementation-decisions artifact reference,
  coding-level contract paths)
- the task's slice entry in `tasks.md`, which lists the assigned IDs from
  the feature-level Behavioral, Code, and Test contracts
- the assigned slice of the feature-level Behavioral Contract, when the
  slice entry names one
- the assigned slice of the feature-level Code Contract
- the assigned slice of the feature-level Test Contract, when one exists
- the task-level Coding Code Contract drafted after research
- the task-level Coding Test Contract drafted after research, when one
  applies
- the committed-implementation-decisions artifact
- research findings

Feature-level contracts are not redrafted at task altitude. If a feature
clause appears wrong or incomplete, the finding escalates upstream
rather than being amended locally. Coding-level contracts are the
task-level authoring authority.

---

## Sections

A plan has three required sections, plus a revision log appended during
implementation when needed.

### 1. Research findings

A brief summary of what preliminary research surfaced:

- what was investigated — which areas of the codebase, which existing
  services, which conventions
- what was learned — key constraints, conventions, patterns to follow
- risks and unknowns — places where research could not fully resolve a
  question, where the plan might be wrong, where mid-implementation
  revision is likely

This section grounds the architecture and sub-task choices that follow.

### 2. High-level architecture

The shape of what will be built:

- **Surface shape.** Modules introduced or extended, exports, key types
  and signatures. Names and shapes, not full implementations.
- **Data flow.** How data moves through the new code. What enters, what
  transforms, what exits.
- **Reuse points.** Existing utilities, services, types, or patterns the
  task will leverage. Explicit declaration so a reader can verify the
  task isn't reinventing things that already exist.

A reader should be able to evaluate whether the architecture coheres
and satisfies the assigned slices and the coding-level contracts without
reading any code.

### 3. Sub-task list

How the work will be chunked. Each sub-task should be small enough for one
TDD cycle (red-green-refactor). If a plan has more than 5 to 10 sub-tasks,
the originating task is probably too big and should have been split during
task definition.

Each sub-task should include:

- **Clauses satisfied** — which behavior IDs, feature-level Code Contract
  clause IDs, feature-level Test Contract clause IDs (when applicable),
  Coding Code Contract clause IDs, and Coding Test Contract clause IDs
  this sub-task delivers.
- **Done condition** — what must be true for the sub-task to be
  considered complete (the test passes, the integration check succeeds,
  the type signature compiles).
- **Dependency order** — which sub-tasks must land first, if any.

The full sub-task list should cover every assigned slice item and every
coding-level contract clause. A clause with no sub-task is missing
coverage; a sub-task with no clause is suspicious.

### Revision log

Plans are provisional. When implementation reveals that a decision in the
plan is wrong, the plan is revised rather than silently worked around.

Each revision-log entry includes:

- what changed
- why — the implementation finding that triggered the revision

If a revision reveals that an upstream feature-level artifact (Behavioral
Contract, Code Contract, Test Contract) is wrong, the issue escalates
upstream. Implementation pauses, the upstream artifact is amended, and
the task resumes once the slice is re-issued. If a revision exposes a
gap in a coding-level contract, that contract is amended directly and
the change is noted in the revision log.

---

## Artifact path

`docs/plans/<feature>/tasks/t-<n>/coding-implementation-plan.md`

Use a deterministic, task-specific path. Do not use generic names like
`plan.md` that require surrounding context to identify the task.

---

## What does not belong in the plan

- implementation code
- verbatim restatement of the Behavioral Contract, Code Contract, Test
  Contract, Coding Code Contract, or Coding Test Contract clauses
  (reference them by ID)
- durable project history from prior tasks (reference committed
  implementation decisions instead)
- the Verification Command (which lives in the Feature Task Handoff;
  the plan may reference it for convenience but doesn't own it)
- a separate "out of scope" section — scope is defined by the assigned
  slices and the coding-level contracts; anything outside them is out of
  scope by construction

---

## Quality check

Can a reader evaluate whether this task's approach is coherent, respects
the assigned slices and coding-level contracts, fits the committed
implementation direction, and gives enough shape to begin TDD — without
the plan having effectively written the implementation in prose? If yes,
the plan is doing its job.

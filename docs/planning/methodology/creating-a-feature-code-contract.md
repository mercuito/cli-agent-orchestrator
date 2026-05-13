# Creating a Feature-Level Code Contract

## Purpose

The feature-level Code Contract defines cross-task obligations on
production code shape for a feature. It is a single feature-level artifact,
drafted alongside the feature-level Behavioral Contract, and it carries
clauses scoped to the whole feature: dependency rules, refactor direction,
public surface commitments, architectural boundaries, and clauses
evaluable from the feature shape alone.

The feature-level contract is not redrafted at task altitude. Each task's
slice of clause IDs is recorded in the Feature Tasks artifact (`tasks.md`);
the Feature Task Handoff references that entry. A separate task-level
Coding Code Contract (see
[creating-a-coding-code-contract](./creating-a-coding-code-contract.md))
names task-specific code-shape obligations after research, drawing from
the coding-level criteria catalog.

If research reveals a feature-level clause is missing or wrong, the
finding escalates upstream for amendment rather than being absorbed
locally.

## What it answers

What cross-task code obligations must the feature satisfy once all of its
tasks are complete?

## What it can contain

- standing architectural boundaries (module ownership, layering,
  ownership of the public surface)
- required reuse points or migration direction
- required public surface rules and dependency commitments
- feature-level code criteria selected from the
  [feature-level Code Contract criteria catalog](./criteria/feature-code-contract/README.md)
- feature-specific code obligations that don't belong in behavioral
  correctness and don't require codebase research to evaluate

The feature-level Code Contract may include obligations that no single
task can satisfy alone. That is expected. Each task's entry in `tasks.md`
names the slice that task is responsible for; task-scoped code-shape
clauses live in the task's Coding Code Contract.

## What does not belong here

- Lower-level code-shape obligations whose `when:` conditions require
  research to evaluate (helper conventions, file-level discipline,
  service-export rules, path-handling, environment-variable use). Those
  are coding-level concerns and live in the task-level Coding Code
  Contract, drawn from the
  [coding-level Code Contract criteria catalog](./criteria/coding-code-contract/README.md).
- Task-by-task implementation guidance. Tasks slice this contract; they
  are not authored from it.

## Slicing

Each task's entry in the Feature Tasks artifact (`tasks.md`) explicitly
enumerates which feature-level Code Contract clauses that task carries
(or states "no slice for this contract" with a one-line reason). Tasks
reference clauses by ID; they do not redraft them. The Feature Task
Handoff references the task's `tasks.md` entry.

If implementation surfaces an obligation the feature-level Code Contract
should carry, the finding escalates upstream — implementation pauses, the
contract is amended, and the task's slice in `tasks.md` is re-issued.
Task-local obligations belong in the Coding Code Contract instead.

## Pure refactor entry

For pure refactor work — work with zero intended externally observable
behavior change — the feature-level Code Contract is the entry artifact.
There is no narrative, capability contract, or behavioral contract.

A pure-refactor feature-level Code Contract must include a scope preamble
naming:

- what structure is being changed
- which code surfaces are affected
- which code surfaces are outside the refactor scope
- which feature-wide obligations must not be violated

Without this preamble, downstream tasks cannot confirm the work is in fact
a pure refactor and cannot slice the restructuring work cleanly. The
preamble's clauses are governed by `implementation-clause-verifiability` —
each entry must be verifiable and unambiguous.

If the planned work changes any externally observable surface, it is not
pure refactor work. It needs a behavioral contract for the changed
behavior, and the narrative path applies.

## Document organization

```markdown
# Feature-Level Code Contract

## Applicable Feature-Level Criteria

| Criterion | Why it applies |
|-----------|----------------|
| ...       | ...            |

## Architectural Commitments

(Module ownership, public surface rules, reuse direction, etc. Each clause
gets a stable ID so the Feature Task Handoff and the Coding Code Contract
can reference it.)

## Feature-Specific Code Obligations

(Anything unique to this feature that doesn't fit a reusable criterion.
Each clause gets a stable ID.)
```

## Artifact path

`docs/plans/<feature>/code-contract.md`

## Relationship to other artifacts

- The **feature-level Behavioral Contract** defines what the system must
  do. The feature-level Code Contract defines cross-task code obligations.
- The **Feature Tasks artifact** (`tasks.md`) enumerates which feature-level
  Code Contract clauses each task carries by ID. The **Feature Task Handoff**
  references that entry and adds the per-task Verification Command and
  coding-level paths.
- The **Coding Code Contract** is the task-level contract. It draws from
  the coding-level criteria catalog and adds task-specific obligations
  after research. It does not duplicate the feature-level contract.
- The **Coding Implementation Plan** explains how the task satisfies its
  assigned feature-level slice along with the Coding Code Contract.
- The **Code Contract Defence** at task altitude defends both the assigned
  feature-level slice and the Coding Code Contract clauses.
- **Committed implementation decisions** are settled facts from landed
  work, not prospective contract obligations. The feature-level Code
  Contract must remain compatible with them.

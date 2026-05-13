# Creating a Feature-Level Code Contract

## Purpose

The feature-level Code Contract defines cross-task implementation-steering
obligations for a feature. The narrative, capability contract, and
behavioral contract describe domain functionality; they intentionally do not
choose database tables, service boundaries, class names, module ownership,
design patterns, migration direction, or other implementation shape. The
feature-level Code Contract is where those feature-wide implementation
decisions live when they are needed.

It is a single feature-level artifact. It carries clauses scoped to the
whole feature: dependency rules, refactor direction, public surface
commitments, architectural boundaries, mandated reuse points, or other
implementation decisions that later tasks must respect.

The feature-level contract is not redrafted at task altitude. Each task's
slice of clause IDs is recorded in the Feature Tasks artifact (`tasks.md`);
the Feature Task Handoff references that entry. A separate task-level
Coding Code Contract (see
[creating-a-coding-code-contract](./creating-a-coding-code-contract.md))
names task-specific code-shape obligations after research, drawing from
the coding-level criteria catalog.

Feature-level Code Contract clauses are optional to create, but binding
once approved and assigned to a task slice. An assigned clause is an
unconditional acceptance requirement for that task, even when the
Behavioral Contract is otherwise satisfied.

If research reveals a feature-level clause is missing or wrong, the
finding escalates upstream for amendment rather than being absorbed
locally.

## What it answers

What implementation decisions, constraints, and code-shape obligations must
the feature satisfy once all of its tasks are complete?

## Inputs

The feature-level Code Contract is not derived from the narrative,
capability contract, or behavioral contract. Those artifacts can reveal
where implementation steering may be useful, but they do not authorize
implementation choices by themselves.

Observable system outcomes belong in the Behavioral Contract. The
feature-level Code Contract may only steer the implementation of those
behaviors by naming ownership boundaries, storage shape, dependency
direction, module placement, API ownership, migration discipline, or other
code architecture decisions.

Author feature-level Code Contract clauses only from:

- explicit user or product direction about implementation shape;
- established repository architecture, ownership boundaries, public
  surfaces, migration patterns, or coding standards;
- existing codebase patterns that the feature must preserve or extend;
- external project documents that impose implementation constraints;
- pure-refactor scope, where this contract is the entry artifact.

If none of those sources create feature-wide implementation obligations,
the contract may explicitly state that there are no feature-level Code
Contract clauses beyond selected criteria, rather than inventing clauses.

## What it can contain

- standing architectural boundaries (module ownership, layering,
  ownership of the public surface)
- required reuse points or migration direction
- required public surface rules and dependency commitments
- feature-level code criteria selected from the
  [feature-level Code Contract criteria catalog](./criteria/feature-code-contract/README.md)
- feature-specific code obligations that don't belong in behavioral
  correctness and are grounded in the inputs above

The feature-level Code Contract may include obligations that no single
task can satisfy alone. That is expected. Each task's entry in `tasks.md`
names the slice that task is responsible for; task-scoped code-shape
clauses live in the task's Coding Code Contract.

Every feature-level Code Contract clause has a stable ID of the form
`F-CC-<n>`. These IDs are the slice surface for `tasks.md`, handoffs,
implementation plans, and defences. Clause titles may change for clarity;
IDs remain stable unless the contract is deliberately reissued.

## What does not belong here

- Implementation choices inferred only from the narrative, capability
  contract, or behavioral contract. Those artifacts describe behavior, not
  code shape.
- Lower-level code-shape obligations whose `when:` conditions require
  research to evaluate (helper conventions, file-level discipline,
  service-export rules, path-handling, environment-variable use). Those
  are coding-level concerns and live in the task-level Coding Code
  Contract, drawn from the
  [coding-level Code Contract criteria catalog](./criteria/coding-code-contract/README.md).
- Task-by-task implementation guidance. Tasks slice this contract; they
  are not authored from it.
- Speculation. If the repo does not already establish a pattern and the
  user has not asked for an implementation direction, do not create one
  just to fill the contract.

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

- `F-CC-1`: <module ownership, public surface rule, reuse direction, or
  other cross-task architectural commitment>
- `F-CC-2`: ...

## Feature-Specific Code Obligations

- `F-CC-3`: <feature-specific obligation that does not fit a reusable criterion>
- `F-CC-4`: ...
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

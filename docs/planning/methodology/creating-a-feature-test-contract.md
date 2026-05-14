# Creating a Feature Test Contract

## Purpose

The feature-level Test Contract defines cross-task proof and test-shape
obligations for a feature. The narrative, capability contract, and
behavioral contract describe what the system must do; they intentionally do
not choose shared harnesses, preservation baselines, fixture patterns, proof
shapes, or verification strategy. The feature-level Test Contract is where
those feature-wide proof decisions live when they are needed.

It is a single feature-level artifact and is optional — used when the
feature has standing proof obligations that need to be sliced across tasks
(shared harnesses, preservation baselines, fixture patterns, or proof shapes
that only a coordinated set of tasks can satisfy).

The feature-level contract is not redrafted at task altitude. Each task's
slice of clause IDs is recorded in the Feature Tasks artifact (`feature-tasks.md`);
the Feature Task Handoff references that entry. A separate task-level
Coding Test Contract (see
[creating-a-coding-test-contract](./creating-a-coding-test-contract.md))
names task-specific proof-shape obligations after research, drawing from
the coding-level test criteria catalog. The universal
`test-validity-preserved` criterion always governs proof integrity at the
coding altitude regardless of whether a feature-level Test Contract
exists.

If a feature has no cross-task proof obligations, no feature-level Test
Contract is needed. The Coding Test Contract for each task and the
universal criterion together carry proof expectations.

Feature-level Test Contract clauses are optional to create, but binding
once approved and assigned to a task slice. An assigned clause is an
unconditional acceptance requirement for that task, even when the
Behavioral Contract is otherwise satisfied.

If research reveals a feature-level clause is missing or wrong, the
finding escalates upstream for amendment rather than being absorbed
locally.

Every feature-level Test Contract clause has a stable ID of the form
`F-TC-<n>`. These IDs are the slice surface for `feature-tasks.md`, handoffs,
implementation plans, and defences. Clause titles may change for clarity;
IDs remain stable unless the contract is deliberately reissued.

## When to use one

Use a feature-level Test Contract when there are proof shapes that must be
consistent across tasks — for example, a required harness, a shared
fixture pattern, or proof obligations that only a coordinated set of tasks
can satisfy.

Author feature-level Test Contract clauses only from:

- explicit user or product direction about proof shape or verification;
- established repository test architecture, fixture conventions, harnesses,
  preservation baselines, or testing standards;
- existing test patterns that the feature must preserve or extend;
- external project documents that impose proof or verification constraints;
- pure-refactor scope, where preservation proof often needs shared
  baselines and characterization decisions.

If proof obligations are local to each task, the task-level Coding Test
Contract and the universal `test-validity-preserved` criterion are
sufficient. No feature-level Test Contract is needed.

## What it can contain

- standing proof shapes that span tasks (harnesses, fixture patterns,
  shared scenarios)
- feature-level test criteria selected from the
  [feature-level Test Contract criteria catalog](./criteria/feature-test-contract/README.md)
- feature-specific proof obligations that don't belong in the behavioral
  contract and are grounded in the inputs above
- proof-integrity scope for refactor work — which existing tests serve as
  the preservation baseline, and where characterization tests are needed
  for preexisting-but-uncovered behavior

## What does not belong here

- Proof choices inferred only from the narrative, capability contract, or
  behavioral contract. Those artifacts describe behavior, not proof shape.
- Lower-level proof-quality obligations whose `when:` conditions require
  research to evaluate (test file organization, fixture choice, harness
  design for one task's affected surfaces). Those are coding-level
  concerns and live in the task-level Coding Test Contract, drawn from the
  [coding-level Test Contract criteria catalog](./criteria/coding-test-contract/README.md).
- Task-by-task proof guidance. Tasks slice this contract; they are not
  authored from it.
- Speculation. If the repo does not already establish a proof pattern and
  the user has not asked for one, do not create one just to fill the
  contract.

## Slicing

Each task's entry in the Feature Tasks artifact (`feature-tasks.md`) explicitly
enumerates which feature-level Test Contract clauses that task carries
(or states "no slice for this contract" with a one-line reason; or notes
that no feature-level Test Contract exists for this feature). Tasks
reference clauses by ID; they do not redraft them. The Feature Task
Handoff references the task's `feature-tasks.md` entry.

If implementation surfaces a proof obligation the feature-level Test
Contract should carry, the finding escalates upstream — implementation
pauses, the contract is amended, and the task's slice in `feature-tasks.md` is
re-issued. Task-local obligations belong in the Coding Test Contract
instead.

## Applicable criteria

Before drafting, read the
[feature-level Test Contract criteria catalog](./criteria/feature-test-contract/README.md)
and select the criteria that apply. Add an `Applicable Feature-Level Test
Criteria` table near the top of the contract with one-line rationale per
selection.

## Refactor work

For pure refactor features, a feature-level Test Contract is typical
because preservation proof usually involves shared baselines and
characterization needs. The universal `test-validity-preserved` criterion
governs: existing tests must continue to validate their original target
behavior; assertions may not change without behavioral contract authority,
and refactors have no behavioral contract.

If existing tests don't cover behavior the refactor needs to preserve,
the feature-level Test Contract names the gaps and requires
characterization tests that describe preexisting behavior — not new
behavior. New assertions that lock in behavior the system did not
previously exhibit are out of scope for a refactor; that work belongs on
the behavior-changing path.

## Document organization

```markdown
# Feature Test Contract

## Applicable Feature-Level Test Criteria

| Criterion | Why it applies |
|-----------|----------------|
| ...       | ...            |

## Standing Proof Shapes

- `F-TC-1`: <shared harness, fixture pattern, preservation baseline, or
  proof obligation that spans tasks>
- `F-TC-2`: ...

## Feature-Specific Proof Obligations

- `F-TC-3`: <feature-specific proof obligation that does not fit a reusable criterion>
- `F-TC-4`: ...
```

## Artifact path

`docs/plans/<feature>/feature-test-contract.md`

The artifact is the Feature Test Contract; the filename keeps the
`feature-` prefix to mark it as a feature-level planning artifact.

## Relationship to other artifacts

- The **feature-level Behavioral Contract** (when present) defines what
  the system must do. The feature-level Test Contract specifies how
  cross-task proof of those behaviors is shaped.
- The **feature-level Code Contract** defines production-code obligations.
  The feature-level Test Contract does not duplicate code obligations.
- The **Feature Tasks artifact** (`feature-tasks.md`) enumerates which feature-level
  Test Contract clauses each task carries by ID. The **Feature Task Handoff**
  references that entry and adds the per-task Verification Command and
  coding-level paths.
- The **Coding Test Contract** is the task-level contract. It draws from
  the coding-level test criteria catalog and adds task-specific proof
  obligations after research. It does not duplicate the feature-level
  contract.
- The **Coding Implementation Plan** explains how the task satisfies its
  assigned feature-level slice along with the Coding Test Contract.
- The **Test Contract Defence** at task altitude defends both the
  assigned feature-level slice and the Coding Test Contract clauses, plus
  the universal `test-validity-preserved` criterion when no feature-level
  Test Contract exists.

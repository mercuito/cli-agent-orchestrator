# Creating a Coding Code Contract

## Purpose

The Coding Code Contract is the task-level production-code contract. It
captures the code-shape obligations for one specific task after the
affected code surfaces have been researched.

Every task produces one. Pure refactor tasks use it to name task-scoped
structural obligations. Behavior-changing tasks use it to name the
task-scoped code obligations discovered by research. If a task truly has no
production-code obligations, the contract states that explicitly with the
reason rather than being omitted.

The Coding Code Contract is *not* a redraft of the feature-level Code
Contract. The feature contract carries cross-task obligations evaluable
from the feature shape alone; the Coding Code Contract carries
task-scoped obligations evaluable *only because* the affected code has
been inspected. The two coexist. The task's Code Contract Defence at the
end of coding defends both.

## When authored

After research, before drafting the Coding Implementation Plan. Both must
land before coding begins.

If research surfaces an obligation that should be cross-task (i.e.,
belongs in the feature-level Code Contract), the finding escalates
upstream rather than being absorbed into the Coding Code Contract.

## Inputs

The Coding Code Contract is drafted from:

- the Feature Task Handoff and the task's slice entry in `feature-tasks.md`
  (the entry lists the assigned feature-level Code Contract clause IDs;
  the handoff carries the Verification Command and the
  committed-implementation-decisions artifact reference)
- research findings — what code is affected, what conventions apply, what
  reuse points exist, what risks are concrete
- the
  [coding-level Code Contract criteria catalog](./criteria/coding-code-contract/README.md)

## What it contains

- coding-level criteria selected from the catalog, with a one-line
  rationale per selection
- task-specific code-shape obligations that don't fit a reusable
  criterion (for example, a particular module boundary the task must
  respect, a specific helper to reuse, a particular file layout for
  added code)
- task-scoped structural intent for refactor work (which exact
  surfaces move where, which call sites the task touches, what the new
  shape looks like)

Each clause gets a stable ID so the Coding Implementation Plan and the
Code Contract Defence can reference it.

## What does not belong here

- Feature-level cross-task obligations. Reference the feature-level Code
  Contract slice by ID instead — those clauses live in the feature
  contract, and the task's `feature-tasks.md` entry names which apply to this task.
- Behavioral correctness. That belongs in the feature-level Behavioral
  Contract; tests prove behaviors at the coding altitude.
- Proof-quality and test-shape obligations. Those belong in the Coding
  Test Contract.
- Implementation code. The contract names obligations; it does not
  contain code.

## Document organization

```markdown
# Coding Code Contract — t-<n>

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| F-CC-1    | feature-level Code Contract | ... |

## Applicable Coding-Level Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| ...       | ...                         |

## Task-Specific Code Obligations

- `C-CC-1`: <obligation>
- `C-CC-2`: <obligation>

(Or: "No task-specific code obligations beyond the inherited feature-level
slice and selected criteria: <reason>.")
```

## Authoring order

1. **Read the Feature Task Handoff and the task's `feature-tasks.md` entry** — the
   entry names the assigned feature-level Code Contract slice; the handoff
   carries the Verification Command and committed-implementation-decisions
   reference.
2. **Research the affected code surfaces.** Inspect existing modules,
   conventions, reuse points, and risks. Concrete codebase findings
   inform which coding-level criteria apply.
3. **Browse the coding-level catalog** and select criteria whose `when:`
   conditions hold given the research findings. Each selection carries a
   one-line rationale.
4. **Add task-specific obligations** that don't fit a reusable criterion.
   Each gets a stable ID and is verifiable on its own — see
   [implementation-clause-verifiability](./criteria/feature-code-contract/implementation-clause-verifiability.md)
   for the standard.
5. **Persist** the Coding Code Contract to its task-level path alongside
   the Coding Implementation Plan.

If research reveals the feature-level slice is wrong or missing, escalate
upstream before drafting the Coding Code Contract — implementation pauses
until the feature contract is amended and the slice in `feature-tasks.md` is
re-issued.

## Artifact path

`docs/plans/<feature>/tasks/t-<n>/coding-code-contract.md`

## Relationship to other artifacts

- The **feature-level Code Contract** carries cross-task obligations.
  Clauses are referenced by ID; not redrafted here.
- The **Feature Tasks artifact** (`feature-tasks.md`) names the assigned feature-level
  slice for this task. The **Feature Task Handoff**
  references that entry and supplies the Verification Command and the
  committed-implementation-decisions reference.
- The **Coding Implementation Plan** explains how the task will satisfy
  this contract's clauses, the inherited feature slice, and any
  behavioral and test slices.
- The **Code Contract Defence** at task altitude defends both the
  inherited feature-level slice and the Coding Code Contract clauses,
  with concrete evidence per clause.
- The **committed implementation decisions** artifact records settled
  facts the Coding Code Contract must remain compatible with.

## Quality check

For each clause: can compliance be verified from the clause text alone,
against the finished implementation, without inferring intent? If not, the
clause is underspecified.

For the contract as a whole: does it name code-shape obligations
defensible *because* of the research, rather than guesses or copy-paste
from the feature contract? If clauses could have been authored at feature
altitude without code research, they probably belong in the feature-level
Code Contract instead.

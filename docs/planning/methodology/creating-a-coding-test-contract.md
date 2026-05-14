# Creating a Coding Test Contract

## Purpose

The Coding Test Contract is the task-level proof and test-shape contract.
It captures the proof obligations for one specific task after the affected
code and test surfaces have been researched.

It exists per task. Every code-touching task has one — at minimum to
record the universal `test-validity-preserved` selection, which always
applies and which the Test Contract Defence covers. Tasks that touch
public boundaries, fixtures, harnesses, or proof shape select additional
coding-level test criteria.

The Coding Test Contract is *not* a redraft of the feature-level Test
Contract. The feature contract (when present) carries cross-task proof
obligations evaluable from the feature shape alone; the Coding Test
Contract carries task-scoped proof obligations evaluable *only because*
the affected code and tests have been inspected. The two coexist when
both are present. The task's Test Contract Defence at the end of coding
defends both, plus the universal criterion.

When no feature-level Test Contract exists, the Coding Test Contract and
the universal `test-validity-preserved` criterion together carry all
proof expectations for the task.

## When authored

After research, before drafting the Coding Implementation Plan. Both must
land before coding begins.

If research surfaces a proof obligation that should be cross-task (i.e.,
belongs in the feature-level Test Contract), the finding escalates
upstream rather than being absorbed into the Coding Test Contract.

## Inputs

The Coding Test Contract is drafted from:

- the Feature Task Handoff and the task's slice entry in `feature-tasks.md`
  (the entry lists the assigned feature-level Test Contract clause IDs
  when one exists, or explicitly states no slice / no feature-level
  Test Contract; the handoff carries the Verification Command and the
  committed-implementation-decisions reference)
- research findings — what test surfaces are affected, what existing
  tests cover the changed behavior, what fixtures or harnesses apply,
  what preservation needs exist
- the
  [coding-level Test Contract criteria catalog](./criteria/coding-test-contract/README.md)

## What it contains

- the universal `test-validity-preserved` selection — present in every
  Coding Test Contract; the Test Contract Defence always defends it
- additional coding-level criteria selected from the catalog, with a
  one-line rationale per selection
- task-specific proof obligations that don't fit a reusable criterion
  (for example, a particular characterization
  test the task must add before refactoring, a specific assertion shape
  required for the touched surfaces, or a fixture pattern the task
  introduces)

Each clause gets a stable ID so the Coding Implementation Plan and the
Test Contract Defence can reference it.

## What does not belong here

- Feature-level cross-task proof obligations. Reference the feature-level
  Test Contract slice by ID instead — those clauses live in the feature
  contract, and the task's `feature-tasks.md` entry names which apply to this task.
- Behavioral correctness claims. Tests prove behaviors at the coding
  altitude, but *what* the system must do lives in the feature-level
  Behavioral Contract, not here.
- Production code-shape obligations. Those belong in the Coding Code
  Contract.
- Test code itself. The contract names obligations; it does not contain
  tests.

## Document organization

```markdown
# Coding Test Contract — t-<n>

## Inherited Feature-Level Slice

| Clause ID | Source | Why this slice applies |
|-----------|--------|------------------------|
| F-TC-1    | feature-level Test Contract | ... |

(Or: "No feature-level Test Contract exists for this feature; universal
`test-validity-preserved` applies.")

## Applicable Coding-Level Test Criteria

| Criterion | Why it applies to this task |
|-----------|-----------------------------|
| `test-validity-preserved` | Universal — always applies |
| ...       | ...                         |

## Task-Specific Proof Obligations

- `C-TC-1`: <obligation>
- `C-TC-2`: <obligation>
```

## Authoring order

1. **Read the Feature Task Handoff and the task's `feature-tasks.md` entry** — the
   entry names the assigned feature-level Test Contract slice (or absence,
   or no feature-level Test Contract); the handoff carries the Verification
   Command and committed-implementation-decisions reference.
2. **Research the affected test surfaces.** Inspect existing tests,
   fixtures, harnesses, and preservation needs. Note what the changed
   behavior currently has covered and where gaps exist.
3. **Read the coding-level criteria catalog before drafting** and select
   criteria whose `when:` conditions hold given the research findings.
   `test-validity-preserved` is always selected. Each selection carries a
   one-line rationale.
4. **Add task-specific obligations** that don't fit a reusable criterion.
   Each gets a stable ID and is verifiable on its own.
5. **Persist** the Coding Test Contract to its task-level path alongside
   the Coding Implementation Plan.

If research reveals the feature-level slice is wrong or missing, escalate
upstream before drafting the Coding Test Contract — implementation pauses
until the feature contract is amended and the slice in `feature-tasks.md` is
re-issued.

## Artifact path

`docs/plans/<feature>/tasks/t-<n>/coding-test-contract.md`

## Relationship to other artifacts

- The **feature-level Test Contract** (when present) carries cross-task
  proof obligations. Clauses are referenced by ID; not redrafted here.
- The **Feature Tasks artifact** (`feature-tasks.md`) names the assigned feature-level Test
  Contract slice for this task (or the explicit absence of one). The
  **Feature Task Handoff** references that entry
  and supplies the Verification Command and committed-implementation-decisions
  reference.
- The **Coding Implementation Plan** explains how the task will satisfy
  this contract's clauses, the inherited feature slice, and any
  behavioral and code slices.
- The **Test Contract Defence** at task altitude defends the inherited
  feature-level slice (when one exists), the Coding Test Contract
  clauses, and the universal `test-validity-preserved` criterion.
- The **Coding Code Contract** names production-code obligations; the
  Coding Test Contract does not duplicate them.

## Quality check

For each clause: can compliance be verified from the clause text alone,
against the finished tests, without inferring intent? If not, the clause
is underspecified.

For the contract as a whole: does it name proof obligations defensible
*because* of the research, rather than guesses or copy-paste from the
feature contract? If clauses could
have been authored at feature altitude without code research, they
probably belong in the feature-level Test Contract instead.

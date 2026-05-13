# Creating a Test Contract Defence

## Purpose

The Test Contract Defence is the evidence-backed proof that the finished
proof artifacts (tests, fixtures, harnesses) satisfy the assigned slice
of the feature-level Test Contract and the task-level Coding Test
Contract. Producing it forces clause-by-clause demonstration that the
proof obligations are honestly satisfied.

It exists per task. Even tasks without a feature-level Test Contract slice
produce a Test Contract Defence because every task produces a Coding Test
Contract.

## What it contains

A defence matrix covering, by ID:

- every assigned feature-level Test Contract clause when one exists
  (standing proof shapes, shared harnesses, fixture patterns, feature-wide
  proof obligations)
- every clause of the task-level Coding Test Contract (selected
  coding-level test criteria and task-specific proof obligations)

Each entry carries concrete evidence — pointers to test files, harness
locations, fixture definitions, or test runs that demonstrate compliance.

## What it does not contain

- Restatement of clause text — reference clauses by ID.
- Behavioral evidence framed as behavior compliance — that belongs in the
  Behavioral Contract Defence. (The same test may appear as evidence in
  both defences, but for different claims: behavioral compliance vs.
  proof-quality compliance.)
- Production code-shape evidence — that belongs in the Code Contract
  Defence.
- High-level summary, plan divergence, or risks — those belong in the
  Coding Completion Report.

## Document organization

```markdown
# Test Contract Defence

## Feature-Level Test Contract

### Clause: <F-TC-ID>

**Claim:** <what compliance looks like for this clause>
**Evidence:** <pointers to test files, harnesses, fixtures>

## Coding Test Contract

### Clause: <C-TC-ID>

**Claim:** ...
**Evidence:** ...

```

## When authored

After the Verification Command runs successfully and after the
slice-adequacy self-check confirms the assigned slice still fits the
finished implementation. If a clause is wrong or missing, escalate
upstream to the Test Contract owner before authoring the defence.

If writing the defence reveals a claim that cannot be defended honestly,
the fix goes to the tests, the Coding Test Contract, or the upstream
Test Contract before the defence is persisted.

## Applicable criteria

Browse the [test contract defence criteria catalog](./criteria/coding-test-contract-defence/README.md)
and select the criteria that apply. Add an `Applicable Criteria` table near
the top of the defence with one-line rationale per selection.

## Artifact path

`docs/plans/<feature>/tasks/t-<n>/test-contract-defence.md`

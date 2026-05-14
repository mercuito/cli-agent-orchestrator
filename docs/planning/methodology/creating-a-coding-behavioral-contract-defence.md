# Creating a Behavioral Contract Defence

## Purpose

The Behavioral Contract Defence is the evidence-backed proof that the
finished implementation satisfies the assigned slice of the feature-level
Behavioral Contract. Producing it forces clause-by-clause demonstration
that the contract is honestly satisfied.

It exists per task. Pure refactor tasks do not have a Behavioral Contract
Defence — they have no behavioral contract slice.

## What it contains

A defence matrix: every assigned behavior and constraint slice item named by
ID, with concrete evidence demonstrating compliance — pointers to tests,
commands, or observable artifacts.

## What it does not contain

- Restatement of the behavior or constraint text — reference clauses by ID
  from the feature-level Behavioral Contract.
- Code-shape or proof-quality evidence — those belong in the Code Contract
  Defence and Test Contract Defence respectively.
- Plan divergence, spec sync, files changed, risks, opportunities, or the
  committed-decision promotion draft — those belong in the Coding Completion
  Report or the Code Contract Defence.

## Document organization

```markdown
# Behavioral Contract Defence

## Behavior: <ID>

**Claim:** <one-line summary of what compliance looks like>
**Evidence:** <pointers to tests, commands, or observable artifacts>

## Constraint: <ID>

**Claim:** ...
**Evidence:** ...
```

## When authored

After the Verification Command runs successfully and after the
slice-adequacy self-check confirms the assigned slice still fits the
finished implementation. If a slice item is wrong or missing, escalate
upstream to the Behavioral Contract owner before authoring the defence.

If writing the defence reveals a claim that cannot be defended honestly
with concrete evidence, the fix goes to the implementation, tests, or
upstream artifacts before the defence is persisted.

## Applicable criteria

Before drafting, read the
[behavioral contract defence criteria catalog](./criteria/coding-behavioral-contract-defence/README.md)
and select the criteria that apply. Add an `Applicable Criteria` table near
the top of the defence with one-line rationale per selection.

## Artifact path

`docs/plans/<feature>/tasks/t-<n>/behavioral-contract-defence.md`

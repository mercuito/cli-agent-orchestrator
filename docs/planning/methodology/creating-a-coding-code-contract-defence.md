# Creating a Code Contract Defence

## Purpose

The Code Contract Defence is the evidence-backed proof that the finished
implementation satisfies the assigned slice of the feature-level Code
Contract and the task-level Coding Code Contract. Producing it forces
clause-by-clause demonstration that the code-shape obligations are
honestly satisfied.

It exists per task, including pure refactor tasks (where the Code Contract
is the entry artifact and carries the structural intent).

## What it contains

A defence matrix covering, by ID:

- every assigned feature-level Code Contract clause (architectural
  commitments, dependency rules, refactor direction, public-surface rules,
  and any feature-level criteria selections)
- every clause of the task-level Coding Code Contract (selected
  coding-level criteria and task-specific code obligations)
- every committed implementation decision in force that constrains this
  task

Each entry carries concrete evidence — pointers to code paths, file diffs,
build/lint output, or other observable artifacts that demonstrate
compliance.

## Committed-decision promotion draft

When the task settles a durable implementation fact that future tasks must
inherit, the proposed committed-decision entries are drafted in this
defence. Promotion to the committed-decisions artifact happens after the
defence is persisted.

If no promotion is warranted, the defence states so explicitly with a
one-line justification rather than omitting the section.

## What it does not contain

- Restatement of clause text — reference clauses by ID.
- Behavioral evidence (tests as proof of behavior) — that belongs in the
  Behavioral Contract Defence.
- Test-shape or proof-quality evidence — that belongs in the Test Contract
  Defence.
- High-level summary, plan divergence, observations, or hiccups — those
  belong in the Coding Completion Report.

## Document organization

```markdown
# Code Contract Defence

## Feature-Level Code Contract

### Clause: <F-CC-ID>

**Claim:** <what compliance looks like for this clause>
**Evidence:** <pointers to code, diffs, build output>

## Coding Code Contract

### Clause: <C-CC-ID>

**Claim:** ...
**Evidence:** ...

## Committed Implementation Decisions

### Decision: <ID>

**Claim:** <how this task remained compatible>
**Evidence:** <pointers>

## Committed-Decision Promotion Draft

(Proposed entries for promotion, or explicit "no promotion warranted: <why>".)
```

## When authored

After the Verification Command runs successfully and after the
slice-adequacy self-check confirms the assigned slice still fits the
finished implementation. If a clause is wrong or missing, escalate
upstream to the Code Contract owner before authoring the defence.

If writing the defence reveals a claim that cannot be defended honestly,
the fix goes to the implementation, the Coding Code Contract, or the
upstream Code Contract before the defence is persisted.

## Applicable criteria

Browse the [code contract defence criteria catalog](./criteria/coding-code-contract-defence/README.md)
and select the criteria that apply. Add an `Applicable Criteria` table near
the top of the defence with one-line rationale per selection.

## Artifact path

`docs/plans/<feature>/tasks/t-<n>/code-contract-defence.md`

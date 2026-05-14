# Creating a Feature Committed Implementation Decisions Artifact

## Purpose

The Feature Committed Implementation Decisions artifact records settled
implementation facts from landed tasks that future tasks must remain
compatible with. It is the running ledger of cross-task constraints
discovered during implementation — module boundaries chosen, public
shapes locked in, conventions established, prior tradeoffs settled.

Unlike the other feature-level artifacts, it is **not authored once**.
It begins thin (often empty) when a feature starts and grows entry by
entry as tasks promote durable facts from their Code Contract Defences.

## When authored

Seeded when feature-level work begins (often as an empty scaffold).
Extended during the promotion step of the per-task lifecycle by moving
entries from the Code Contract Defence's Committed-Decision Promotion
Draft into this artifact.

Existing entries are amended only when a later task discovers the entry
is wrong; in that case the amendment is itself promoted from a Code
Contract Defence.

## What it contains

For each entry:

- a stable ID of the form `cid-<n>`
- a one-sentence statement of the settled fact
- the source task (e.g. `t-3`) that promoted the entry
- a short rationale explaining why future tasks must remain compatible

For the artifact as a whole:

- entries are append-only by default; amendments cite the original entry
  ID and the task that triggered the amendment
- nothing else — the artifact is a ledger, not a planning document

## What it does not contain

- speculative future commitments (only landed-and-promoted facts)
- restatement of feature-level contract clauses
- implementation code or plan content

## Document organization

```markdown
# Feature Committed Implementation Decisions — <feature>

## cid-1 — <short statement>

**Source:** `t-1`
**Rationale:** <why this fact is binding for future tasks>

## cid-2 — <short statement>

**Source:** `t-2`
**Rationale:** ...

## cid-1.amended — <amended statement>

**Source:** `t-5`
**Original:** `cid-1`
**Rationale:** <why the original was wrong and what changed>
```

## Applicable criteria

Browse the [committed implementation decisions criteria catalog](./criteria/feature-committed-implementation-decisions/README.md)
and select the criteria that apply. Add an `Applicable Criteria` table
near the top of the artifact with one-line rationale per selection.

## Artifact path

`docs/plans/<feature>/feature-committed-implementation-decisions.md`

The artifact is the Feature Committed Implementation Decisions ledger; the
filename keeps the `feature-` prefix to mark it as a feature-level planning
artifact.

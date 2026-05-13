# Planning Workflow

This document shows the flow: which artifacts get produced, in what order,
and where they land. Each artifact has its own `creating-a-*.md` guide
that defines its content, structure, and quality criteria.

The methodology stops at artifact production. Quality assurance practices
like review, pairing, or gating belong to whoever implements the workflow
and are out of scope here.

## Feature-level artifacts

Authored before coding begins, in this order:

1. [Feature Narrative](./creating-a-feature-narrative.md) — behavior-changing
   work only; pure refactors skip.
2. [Feature Capability Contract](./creating-a-feature-capability-contract.md)
   — behavior-changing work only; derives capabilities from the narrative
   and captures cross-cutting invariants and domain graphs.
3. [Feature Behavioral Contract](./creating-a-feature-behavioral-contract.md)
   — behavior-changing work only.
4. [Feature Code Contract](./creating-a-feature-code-contract.md) — entry
   artifact for pure refactors.
5. [Feature Test Contract](./creating-a-feature-test-contract.md) — optional;
   only when proof obligations span tasks.
6. [Committed Implementation Decisions](./creating-a-feature-committed-implementation-decisions.md)
   — running ledger of settled facts from landed tasks; seeded when the
   feature begins, grown entry by entry as tasks promote durable facts.
7. [Feature Tasks](./creating-a-feature-tasks.md) — the feature's task list
   with stable IDs, brief scopes, and assigned contract slice IDs.
8. [Feature Task Handoff](./creating-a-feature-task-handoff.md) — one per
   task; references the task's slice entry in `tasks.md`, the
   committed-decisions artifact, the Verification Command, and coding
   artifact paths. When the task entry requires supporting references, the
   handoff carries the concrete UI, design, product, domain, or existing-code
   references needed for implementation research.

## Per-task lifecycle

For each task:

1. **Read handoff and research.** Read the handoff, the task's entry in
   `tasks.md` (which lists the assigned slices), the named feature-level
   contracts, the committed-decisions artifact, the Verification Command,
   the artifact paths, and any supporting references. Inspect the affected
   code and test surfaces.
2. Draft [Coding Code Contract](./creating-a-coding-code-contract.md).
3. Draft [Coding Test Contract](./creating-a-coding-test-contract.md).
4. Draft [Coding Implementation Plan](./creating-a-coding-implementation-plan.md).
5. **Implement.** Revise the plan or coding contracts via the revision log
   when findings demand. Escalate upstream if a feature-level artifact or
   handoff slice is wrong.
6. **Verify.** Run the Verification Command exactly as assigned. The task
   blocks if the command is unclear, unavailable, or impossible.
7. Write [Coding Completion Report](./creating-a-coding-completion-report.md)
   and applicable Contract Defences:
   [Behavioral](./creating-a-coding-behavioral-contract-defence.md),
   [Code](./creating-a-coding-code-contract-defence.md),
   [Test](./creating-a-coding-test-contract-defence.md).
8. **Promote committed decisions.** Move proposed entries from the Code
   Contract Defence into the committed-decisions artifact.

Pure refactor tasks omit the Behavioral Contract Defence in step 7.

## Directory layout

```text
docs/plans/<feature>/
├── narrative.md                            # behavior-changing only
├── capability-contract.md                  # behavior-changing only
├── behavioral-contract.md                  # behavior-changing only
├── code-contract.md
├── test-contract.md                        # optional
├── committed-implementation-decisions.md
└── tasks/
    ├── tasks.md
    └── t-<n>/
        ├── feature-task-handoff.md
        ├── coding-code-contract.md
        ├── coding-test-contract.md
        ├── coding-implementation-plan.md
        ├── coding-completion-report.md
        ├── behavioral-contract-defence.md  # behavior-changing only
        ├── code-contract-defence.md
        └── test-contract-defence.md
```

## Criteria

Criteria catalogs at [`./criteria/`](./criteria/) are libraries. A criterion
becomes binding only when the appropriate contract selects it. Feature-level
criteria are evaluable from the feature shape alone; coding-level criteria
are evaluable only after researching the affected codebase.

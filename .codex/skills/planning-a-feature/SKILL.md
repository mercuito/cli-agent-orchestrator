---
name: planning-a-feature
description: Use when asked to implement a narrative, turn a narrative into a capability contract, derive behavioral/code/test contracts, create implementation tasks, or orchestrate implementer/reviewer agents through the repo planning methodology.
---

# Planning Contract Workflow

Use this skill when the user asks to take a narrative through the planning and
implementation workflow, especially phrases like "implement this narrative",
"derive capabilities", "derive the behavioral contract", "break this into
tasks", or "dispatch implementers".

## Required Reading

Before deriving artifacts, read the repo-local methodology and criteria. Prefer
paths in the current repo; if missing, ask briefly or locate equivalent docs.

- `docs/planning/methodology/workflow.md`
- `docs/planning/methodology/creating-a-feature-narrative.md`
- `docs/planning/methodology/creating-a-feature-capability-contract.md`
- `docs/planning/methodology/creating-a-feature-behavioral-contract.md`
- `docs/planning/methodology/creating-a-feature-code-contract.md`
- `docs/planning/methodology/creating-a-feature-test-contract.md`
- `docs/planning/methodology/creating-a-feature-committed-implementation-decisions.md`
- `docs/planning/methodology/creating-a-feature-tasks.md`
- `docs/planning/methodology/creating-a-feature-task-handoff.md`
- `docs/planning/methodology/creating-a-coding-code-contract.md`
- `docs/planning/methodology/creating-a-coding-test-contract.md`
- `docs/planning/methodology/creating-a-coding-implementation-plan.md`
- `docs/planning/methodology/creating-a-coding-completion-report.md`
- `docs/planning/methodology/creating-a-coding-behavioral-contract-defence.md`
- `docs/planning/methodology/creating-a-coding-code-contract-defence.md`
- `docs/planning/methodology/creating-a-coding-test-contract-defence.md`
- `docs/planning/methodology/criteria/README.md`
- `docs/planning/methodology/criteria/feature-narrative/README.md`
- `docs/planning/methodology/criteria/feature-capability-contract/README.md`
- `docs/planning/methodology/criteria/feature-behavioral-contract/README.md`
- `docs/planning/methodology/criteria/feature-code-contract/README.md`
- `docs/planning/methodology/criteria/feature-test-contract/README.md`
- `docs/planning/methodology/criteria/feature-committed-implementation-decisions/README.md`
- `docs/planning/methodology/criteria/feature-tasks/README.md`
- `docs/planning/methodology/criteria/feature-task-handoff/README.md`
- `docs/planning/methodology/criteria/coding-code-contract/README.md`
- `docs/planning/methodology/criteria/coding-test-contract/README.md`
- `docs/planning/methodology/criteria/coding-behavioral-contract-defence/README.md`
- `docs/planning/methodology/criteria/coding-code-contract-defence/README.md`
- `docs/planning/methodology/criteria/coding-test-contract-defence/README.md`

## Artifact Authoring Rule

Before drafting or revising any methodology artifact, read that artifact's
`creating-a-*.md` guide and its criteria catalog. Select applicable criteria
before drafting the body, include the artifact's `Applicable Criteria` table
when the methodology calls for one, and treat selected criteria as binding
until revised through the artifact.

Use the methodology's artifact filenames exactly. The word "feature-level"
describes artifact altitude; it is not a filename prefix for top-level plan
artifacts. For example, use `capability-contract.md`, not
`feature-capability-contract.md`.

Before dispatching agents, inspect local role prompts under the current repo's
`.codex/agents/` directory first, then fall back to `~/.codex/agents/` if
needed. In this methodology, the standard profile names are:

- `feature-narrative-reviewer.toml`
- `feature-capability-contract-reviewer.toml`
- `feature-behavioral-contract-reviewer.toml`
- `coding-implementer.toml`
- `coding-implementation-plan-reviewer.toml`
- `coding-behavioral-contract-reviewer.toml`
- `coding-code-contract-reviewer.toml`
- `coding-test-contract-reviewer.toml`

## Workflow

1. **Locate the active narrative or refactor intent**
   - Identify the plan folder and feature intent.
   - For behavior-changing work, strengthen a thin narrative before deriving
     contracts.
   - Refuse to derive a capability contract, behavioral contract, or task list
     for behavior-changing work until a Narrative exists.
   - For pure refactor work, skip narrative, capability contract, and
     behavioral contract; enter at the Code Contract.

2. **Create feature-level artifacts**
   - For behavior-changing work, create or update the Narrative using
     `creating-a-feature-narrative.md` and the feature narrative criteria.
     Structure the narrative as a timeline of short, discrete,
     referenceable events with stable event IDs, not as free-form prose
     paragraphs.
   - Dispatch `feature-narrative-reviewer` to review the Narrative.
     Continue only after explicit approval.
   - Derive the Capability Contract from the approved narrative using
     `creating-a-feature-capability-contract.md` and the feature capability
     contract criteria.
   - Dispatch `feature-capability-contract-reviewer` to review the Capability
     Contract. Continue only after explicit approval.
   - Derive the Behavioral Contract from the approved narrative and approved
     capability contract using
     `creating-a-feature-behavioral-contract.md` and the feature behavioral
     contract criteria.
   - Dispatch `feature-behavioral-contract-reviewer` to review the Behavioral
     Contract. Continue only after explicit approval.
   - Create the Code Contract using
     `creating-a-feature-code-contract.md` and feature-level code criteria
     only when there are feature-wide implementation-steering obligations.
     Do not derive code-shape choices from the narrative, capability
     contract, or behavioral contract. Ground clauses in explicit
     user/product direction, established repository architecture or coding
     standards, existing codebase patterns, external project documents, or
     pure-refactor scope. If no such source creates feature-wide
     implementation obligations, state that explicitly rather than
     inventing clauses. Each feature-level Code Contract clause must have a
     stable `F-CC-<n>` ID so `tasks.md` can assign slices by ID.
   - Create a Test Contract only when proof obligations exist at
     feature altitude and need to be sliced across tasks. Use
     `creating-a-feature-test-contract.md` and feature-level test criteria.
     Do not derive proof-shape choices from the narrative, capability
     contract, or behavioral contract. Ground clauses in explicit
     user/product direction, established repository test architecture,
     fixture conventions, harnesses, preservation baselines, testing
     standards, external project documents, or pure-refactor scope. If proof
     obligations are task-local, do not create a feature-level Test
     Contract. Each feature-level Test Contract clause must have a stable
     `F-TC-<n>` ID so `tasks.md` can assign slices by ID.
   - Feature-level Code/Test Contract clauses are optional to create, but
     binding once approved and assigned to a task slice. Any assigned
     clause is an unconditional acceptance requirement for that task, even
     when the Behavioral Contract is otherwise satisfied.
   - Create or update the committed-implementation-decisions artifact as the
     running ledger of settled implementation facts.

3. **Break work into tasks and handoffs**
   - Do not create `tasks.md` for behavior-changing work until the Narrative,
     Capability Contract, and Behavioral Contract have explicit reviewer
     approval.
   - Maintain `tasks.md` as the feature-level task list. Before drafting or
     revising it, read `creating-a-feature-tasks.md` and the feature tasks
     criteria catalog.
   - Create one `feature-task-handoff.md` per task. Before drafting or
     revising a handoff, read `creating-a-feature-task-handoff.md` and the
     feature task handoff criteria catalog.
   - Each handoff must explicitly name behavioral, Code Contract, and Test
     Contract slices, or explicitly state no slice for that
     contract with a reason.
   - Each handoff must reference the committed-implementation-decisions
     artifact, include the Verification Command, and provide deterministic
     paths for coding contracts, plan, report, and defences.

4. **Commit planning artifacts**
   - Once feature artifacts, task list, and handoffs are approved, commit the
     planning docs before implementation orchestration unless the user
     explicitly says not to.

5. **Orchestrate implementation**
   - Dispatch one implementer agent per task.
   - Pass the Task Handoff, feature-level contracts/slices, committed
     implementation decisions, Verification Command, deterministic coding
     artifact paths, and relevant criteria catalogs.
   - Tell implementers they are not alone in the codebase and must not revert
     unrelated user or agent changes.
   - Wait for the implementer to return completed/blocked with persisted
     Coding Completion Report and defence paths. Do not end while an
     implementation agent is still running unless the user explicitly asks you
     to pause or stop.
   - Continue task by task until all assigned tasks are complete or blocked.

6. **Maintain orchestration state**
   - Maintain an orchestration/progress report in the plan folder when the plan
     spans multiple tasks.
   - Keep the committed-implementation-decisions artifact current and treat all
     entries as in force for every later task.
   - Clean up completed agent threads so implementers can still spawn reviewer
     agents and do not hit thread limits.

7. **Verify done**
   - Run the relevant verify/test commands.
   - For broad system work, prefer an integration or smoke test that proves the
     narrative scenario works, not only isolated unit tests.
   - Report proof, residual risks, and any tests not run.

## Review Prompt Requirements

Every reviewer prompt must include:

- the exact artifact under review;
- the source artifact(s) it should be judged against;
- the relevant criteria documents;
- a requirement that findings be substantiated with concrete references;
- a requirement to avoid speculative or vibe-based critique.

Use the narrow reviewer profile that matches the artifact under review:

- `feature-narrative-reviewer` for `narrative.md`;
- `feature-capability-contract-reviewer` for `capability-contract.md`;
- `feature-behavioral-contract-reviewer` for `behavioral-contract.md`;
- `coding-implementation-plan-reviewer` for `coding-implementation-plan.md`;
- `coding-behavioral-contract-reviewer` for behavioral compliance after
  implementation;
- `coding-code-contract-reviewer` for Coding Code Contract criteria
  applicability and violations;
- `coding-test-contract-reviewer` for Coding Test Contract criteria
  applicability and violations.

## Implementer Prompt Requirements

Every implementer prompt must include:

- task scope and ownership;
- Task Handoff and assigned feature-level slices;
- relevant feature-level and coding-level criteria documents;
- paths for Coding Code Contract, Coding Test Contract, Coding Implementation
  Plan, Coding Completion Report, and applicable defences;
- committed-implementation-decisions artifact and Verification Command;
- expected verification;
- instruction not to revert unrelated user or agent changes;
- instruction to produce separate defences for behavioral, code, and test
  contracts as applicable.

## Scope Discipline

Do not skip review gates because the design seems obvious. Do not dispatch
implementers from unreviewed feature-level artifacts or missing handoffs. Do
not hide domain-specific policy inside lower-level services unless the
Narrative and Behavioral Contract establish that ownership.

# Creating a Coding Completion Report

## Purpose

The Coding Completion Report is the high-level summary of the finished
task: what was implemented, what diverged from the plan, what a reader
needs to know about the result, and where future work or follow-up may
matter.

Contract defences live in their own per-contract documents (the Behavioral
Contract Defence, Code Contract Defence, and Test Contract Defence). The
Coding Completion Report does not duplicate those defences — it sits next
to them, summarizing the implementation in terms a reader who only needs
task context still benefits from.

Every task produces a Coding Completion Report.

## What it contains

A Coding Completion Report has the following sections. Sections that do
not apply to a given task are explicitly marked "not applicable" with a
one-line reason rather than omitted silently.

### Implementation summary

A concrete account of what the task implemented — what surfaces changed,
what behavior changed, what didn't change. Specific enough that a reader
who only opens this report can understand the shape of the finished work.

### Plan divergence

What changed between the Coding Implementation Plan and the finished
implementation, why it changed, and why the finished implementation still
satisfies the assigned slices. If there was no material divergence, state
that explicitly.

### Slice-adequacy self-check

Confirmation that the assigned slices still fit the finished
implementation. If implementation revealed an upstream contract clause was
inadequate or wrong, the escalation result is recorded here: the
amendment and re-issued slice are named.

### Contract boundary and escalation check

A concrete account of whether implementation evidence showed any assigned
feature-level Code or Test clause crossing the task's behavior-preservation
boundary, public-surface boundary, or system boundary.

This section does not create a new compatibility policy. It reconciles the
finished implementation against the policies already in force from the
assigned slices, especially feature-level Code Contract clauses selected
under `backward-compatibility-policy`,
`replaced-surface-lifecycle-policy`, and `caller-migration-policy`.

The report states whether the task:

- stayed within the assigned behavior and preservation boundary;
- changed a public surface, wire/storage shape, developer command, generated
  artifact, or other observer-facing surface;
- added or retained compatibility scaffolding, duplicate old/new paths,
  long-lived shims, adapters, facades, compatibility re-exports, or
  dual-shape storage;
- found that an assigned clause was wrong, over-broad, infeasible, or
  incompatible with the actual system boundary.

If no boundary issue was found, say so with the evidence basis. If a boundary
issue was found, name the upstream escalation, the amended artifact or
re-issued slice, and the final policy the implementation followed.

### Verification result

The exact Verification Command from the task definition was run, and the
result. The defences depend on the command having succeeded.

### Spec sync

If the implementation altered the system's behavior, public surface,
constraints, or domain shape, name which upstream planning artifacts
(narrative, capability contract, behavioral contract, Code Contract,
Test Contract) were updated to match post-implementation reality. If no upstream
artifact needed updating, carry an explicit no-spec-delta justification.

### Files changed

A list of files added, modified, or removed by the implementation. The
list scopes which surfaces a reader needs to look at to understand the
finished work.

### Observations

Notes about the implementation experience that a reader should be able to
see at a glance — places where research uncovered something unexpected,
places where the code was harder than the plan suggested, places where
the existing code held surprises.

### Hiccups

Concrete bumps hit during the work — failed approaches, dead ends, broken
tooling, and how each was resolved. Recorded so future similar tasks can
avoid the same friction.

### Optimization opportunities

Non-binding observations of improvement opportunities noticed during the
task but kept out of scope. Recorded here so the signal isn't lost;
explicitly separate from risks because they are not contract obligations.

### Risks and known issues

Issues known but not resolved within this task — edge cases not yet
covered, latent concerns surfaced during research, known follow-up
needed. Each entry is concrete enough that a reader can evaluate its
severity.

## What it does not contain

- Contract defence matrices (those live in the Behavioral Contract
  Defence, Code Contract Defence, and Test Contract Defence).
- Implementation code (the Files changed list points at code; it does not
  duplicate it).
- Verbatim restatement of the plan or contracts.
- Chat-only summaries or ephemeral context that vanish after the session.

## Authoring order

Authored after implementation is functionally complete and the Verification
Command runs successfully, alongside the per-contract defences.

The Coding Completion Report has no standalone criteria catalog. Before
drafting, read the selected criteria and clauses in the task's Coding Code
Contract, Coding Test Contract, assigned feature-level slices, and the
defence criteria catalogs for the per-contract defences being authored
alongside the report.

1. **Run the Verification Command** named in the task definition. The
   command must succeed before the report can be authored.
2. **Run the slice-adequacy self-check.** Walk the assigned slices of the
   behavioral, Code, and Test contracts; confirm each clause still fits
   the finished implementation. If a clause is wrong, escalate upstream
   and pause until the slice is re-issued.
3. **Run the contract boundary and escalation check.** Reconcile the
   finished implementation against the assigned behavior/preservation
   boundary and the assigned compatibility, replacement-lifecycle, and
   caller-migration policies. If the implementation crossed a boundary,
   added unsupported compatibility scaffolding, or revealed a wrong
   upstream clause, escalate upstream and pause until the slice is
   re-issued.
4. **Draft this report.** Implementation summary, plan divergence,
   slice-adequacy self-check, contract boundary and escalation check,
   verification result, spec sync, files changed, observations, hiccups,
   optimization opportunities, risks.
5. **Draft the per-contract defences** alongside this report — one each
   for behavioral, Code, and Test contracts.
6. **Self-check.** If anything in the summary cannot be defended with
   concrete evidence, fix the implementation, tests, upstream artifacts,
   or report until the claim is honest.
7. **Persist** the Coding Completion Report and the per-contract defences
   to their task-level paths.

If subsequent work materially changes the implementation or the evidence,
update the persisted report and any affected defences accordingly.

## Artifact path

`docs/plans/<feature>/tasks/t-<n>/coding-completion-report.md`

## Quality check

Could a reader open just this report and understand what shipped, what
diverged, and what to look at next? If not, the summary is too thin or
too verbose.

Does writing the report surface anything that hadn't already been
addressed? If yes, the report is doing its job as a forcing function. If
the report is purely clerical, the self-check may have been skipped.

# Review Goal: CAO Agent Model Cleanup

## Goal

Walk every commit landed against the CAO agent model cleanup plan and verify
each task against its plan-specified deliverables, acceptance criteria,
criteria-catalog applicability, and the no-backwards-compatibility
enforcement. Produce a structured findings document recording verdicts and
gaps. Earlier review gates may have happened; tracking was lost. **Assume
nothing was reviewed and re-verify everything.** Pass is conditional on
explicit evidence, not absence of doubt.

This is review work, not implementation. Flag findings; do not fix them.

## Sources of truth

- `docs/plans/agent-model-cleanup/plan.md` — locked design, migration shape,
  forbidden compatibility patterns, phasing.
- `docs/plans/agent-model-cleanup/tasks.md` — task definitions: deliverables
  and acceptance criteria for each T01–T15.
- `docs/plans/agent-model-cleanup/handoff.md` — the goal prompt the
  implementer was given. Especially the "Definition of done" section, which
  contains grep checks and behavior checks the reviewer should re-run.
- `docs/criteria/implementation/` and `docs/criteria/tests/` — criteria
  catalog. Browse via `python scripts/catalog_criteria.py`. The
  `do-not-assume-backwards-compatibility` criterion is unusually
  load-bearing for this cleanup.

## Scope

Every commit on the current branch from the plan's introduction onward:

```
git log 91dec61~1..HEAD --oneline
```

Map each commit to its T-number by reading the subject line. Several
caveats up front:

- **T01–T04 are bundled in a single commit** (`968cc79`). Walk all four
  tasks' criteria against that one diff.
- **T07, T08, T09, T10, T14 each have multiple commits.** Walk all
  commits associated with a task as one unit of review (the later
  commits often address findings from a partial first landing).
- The pre-plan commit `9a7e833 "a"` deleted five unrelated stale plan
  files. Out of scope for this review.
- Three plan-doc commits (`91dec61`, `2a071d0`, `15c0cba`) are plan
  edits, not implementation. Out of scope.

## Per-task review checklist

For each task T01–T15, walk the following gates against the associated
commit(s). Do not pass a task unless every gate is satisfied.

### 1. Deliverables match the plan

Read the diff(s) and check the commit produces every artifact listed in
the task's `deliverables:` block in `docs/plans/agent-model-cleanup/tasks.md`.
Flag missing deliverables, even if the task otherwise looks complete.

### 2. Acceptance criteria are met

Walk every bullet in the task's `acceptance:` list. For each:

- If it is a **grep check** (e.g. `grep -rn ... returns no hits`),
  actually run it on the current tree and record the result.
- If it is a **behavior check**, locate the test that exercises it; verify
  the test exists and passes when run.
- If it is a **manual verification** (e.g. a UI behavior), note it as
  such and check whether the implementer recorded the result somewhere
  (commit message, PR description, follow-up note). Reviewer does not
  need to perform manual UI checks themselves.
- If the criterion involves a renamed symbol, file, or endpoint, grep
  for the OLD name to confirm it is fully gone.

### 3. No backwards-compatibility layer

Specifically inspect the diff for any of the patterns forbidden by the
plan's "Forbidden compatibility patterns" section:

- Shims that detect the old shape and fall back to it
- Facades preserving old types as thin wrappers around new types
- Fallback chains (`try new format; on failure, try old format`)
- Feature flags switching between old and new behavior at runtime
- Deprecation warnings emitted instead of removing the old path
- Function or module aliases preserving old import paths
- Optional fields preserving old defaults where the new model requires
  them
- Runtime translators between old and new shapes

If any are present, the task fails this gate. **Escalate to the
operator immediately** rather than just recording in findings — this is
a load-bearing rule and any violation suggests a systemic gap in the
implementer's pass.

### 4. Criteria catalog applicability

Identify every entry in `docs/criteria/implementation/` and
`docs/criteria/tests/` whose `when` clause matches the task's diff. List
them in the findings entry. For each applicable entry, verify the diff
satisfies it; flag specific violations.

Pay particular attention to:

- `do-not-assume-backwards-compatibility` — applies to every task
- `migration-discipline` — applies to anything touching data shape
- `no-test-only-production-seams` — applies to any change introducing
  test scaffolding
- `system-definitions-are-localized` — applies to the agent dataclass
  design (T01)
- `seams-must-be-tested` — applies to the boundary between agent
  reader/writer/validator (T01–T04) and the consumer code in T05/T06

### 5. Tests adequate

Verify the test file(s) implied by the task's deliverables:

- Exist at the expected path
- Have meaningful assertions, not just smoke tests
- Run and pass when invoked (`pytest <path>` or the project's
  equivalent — confirm with the operator if unclear)
- Cover the failure modes named in the task's acceptance criteria

Test gaps are findings even if everything else passes.

### 6. Integrates cleanly

Verify at the commit (or last commit if a task spans multiple):

- The tree builds without errors
- Imports resolve
- Existing tests still pass (the task did not silently break a neighbor)
- Type checks pass if the project uses them

If a later commit on the same task addresses earlier breakage,
acknowledge in findings and pass on the merged result — but flag the
hygiene issue.

## Recording findings

Write findings to `docs/plans/agent-model-cleanup/review-findings.md`. One
entry per task. Use this format:

```markdown
### T05 — Rename agent manager/registry and swap API readers

- commit(s): f3a6c20
- verdict: pass | partial | fail | followup
- deliverables: <delivered / missing>
- acceptance criteria: <met / gaps>
- no-shim check: <result of grep checks; specific shim if found>
- criteria catalog: <applicable entries; violations if any>
- tests: <verified / gaps>
- notes: <free-form observations, integration concerns, etc.>
```

Verdict definitions:

- **pass** — every gate satisfied, no follow-up needed
- **followup** — every gate satisfied, but minor cleanup items noted for
  later (does not block the plan being considered complete)
- **partial** — at least one gate has gaps that need implementer action
  before the plan can be considered complete
- **fail** — significant violations (especially of the no-shim rule);
  requires rework before merging into the plan's "done" state

End the findings file with a summary block:

```markdown
## Summary

- pass: T0X, T0Y, ...
- followup: T0X (note: ...), ...
- partial: T0X (gaps: ...), ...
- fail: T0X (reason: ...), ...

## Blocking issues

<bulleted list of partial/fail entries that must be addressed>

## Followups

<bulleted list of followup items that can be deferred>
```

## Out of scope

- **Fixing anything.** Flag in findings, escalate if load-bearing. The
  implementer addresses gaps in a separate pass.
- **Re-running ultra-review or other automated review tools.** This is
  a focused gate review against the plan's contract, not a general code
  quality sweep.
- **Style nits** unless they violate a catalog criterion.
- **Scope changes.** If a commit appears to expand the plan's scope
  (a new task not in T01–T15), flag as out-of-scope and escalate.
- **Re-verifying the plan itself.** The plan is the contract; the job
  is to verify implementation against it, not to second-guess the plan.

## Definition of done

This review is complete when **every item below is true**:

- `docs/plans/agent-model-cleanup/review-findings.md` exists.
- Every task T01 through T15 has an entry with a verdict.
- For every grep check in the plan's acceptance criteria and the
  handoff's Definition of done, the result is recorded in the findings
  (pass or specific hits with file:line).
- The summary block at the end lists verdict buckets and identifies
  every blocking issue.
- Any task with verdict `fail` has been escalated to the operator with a
  separate message describing the violation, not just recorded in the
  file.
- Tests have been run against the current HEAD and the overall pass/fail
  status is recorded (use the project's standard pytest invocation; ask
  the operator if unclear).

## Escalate to the operator immediately if

- A commit introduces any forbidden compatibility pattern (shim, facade,
  fallback chain, feature flag, deprecation warning, alias, optional
  field preserving old default, runtime translator). Do not just record
  in findings.
- A commit appears to have landed without an associated plan task or
  expands the plan's scope.
- The plan itself contains an internal contradiction that prevents
  evaluating a task.
- Tests cannot be run because of infrastructure failure.
- A grep check that should return no hits returns hits in production
  code paths.

## Recommended order

1. Run all grep checks from the plan's acceptance + handoff Definition
   of done first; record results. These are fast and may surface
   load-bearing failures early.
2. Walk tasks in T-number order. Earlier tasks set up the model; later
   tasks consume it. Reviewing in order makes integration concerns
   easier to spot.
3. After per-task review, run the full test suite at HEAD. Record
   overall pass/fail.
4. Compose the summary block and escalate any fail-verdict tasks.

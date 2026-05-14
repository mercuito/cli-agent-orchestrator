# Criteria Catalogs

Each subdirectory is a catalog of reusable criteria for one stage of the
methodology. Catalogs are libraries — a criterion has no authority until a
contract or artifact selects it.

| Catalog | Stage governed |
|---|---|
| [feature-narrative](feature-narrative/README.md) | Authoring the narrative |
| [feature-capability-contract](feature-capability-contract/README.md) | Authoring the capability contract (capabilities, invariants, domain graphs) |
| [feature-behavioral-contract](feature-behavioral-contract/README.md) | Authoring the behavioral contract |
| [feature-code-contract](feature-code-contract/README.md) | Authoring the feature-level Code Contract |
| [feature-test-contract](feature-test-contract/README.md) | Authoring the feature-level Test Contract |
| [feature-committed-implementation-decisions](feature-committed-implementation-decisions/README.md) | Authoring entries in the running ledger |
| [feature-tasks](feature-tasks/README.md) | Authoring the Tasks index |
| [feature-task-handoff](feature-task-handoff/README.md) | Authoring a per-task Task Handoff |
| [coding-code-contract](coding-code-contract/README.md) | Authoring a task-level Coding Code Contract |
| [coding-test-contract](coding-test-contract/README.md) | Authoring a task-level Coding Test Contract |
| [coding-behavioral-contract-defence](coding-behavioral-contract-defence/README.md) | Authoring a Behavioral Contract Defence |
| [coding-code-contract-defence](coding-code-contract-defence/README.md) | Authoring a Code Contract Defence |
| [coding-test-contract-defence](coding-test-contract-defence/README.md) | Authoring a Test Contract Defence |

## Altitude split for Code Contract and Test Contract

Code and test obligations split into two altitudes:

- **Feature-level** catalogs hold criteria evaluable from the feature
  shape alone: cross-task structural commitments, dependency rules,
  refactor direction, and public-surface decisions scoped to the whole
  feature.
- **Coding-level** catalogs hold criteria evaluable only after inspecting
  the codebase: code-shape obligations, helper/fixture discipline,
  verification-design rules, and any clause whose `when:` requires
  research to evaluate.

Coding-level criteria are selected after research, when authoring a
task-level Coding Code Contract / Coding Test Contract. Feature-level
contracts and slices flow downward; coding-level contracts are scoped
to one task.

## Authoring standard for criteria entries

Every entry in every catalog must follow these rules. They exist so each entry
carries strong, undiluted signal.

**One concept per entry.** A criterion entry must encode exactly one
distinguishable obligation. Bundling multiple distinct concepts into one
entry weakens each — split them.

**`when:` is short and verifiable.** The frontmatter `when:` field must be
clear, authoritative, and quickly verifiable by any reader. No exposition.
No information dumps. A reader should be able to decide applicability in
one read.

**Body answers *what*, not *why*.** The body states the obligation directly.
Do not explain why it matters in prose — show that through the illustrations
instead.

**Illustrations are minimal and dense.** Use one or two paired good/bad
illustrations to convey *why* the criterion matters. Each illustration should
fit in a few sentences. No extended walkthroughs.

**Maximize information per word.** Entries should be minimal but complete and
unambiguous. If a sentence does not increase the entry's signal, cut it.

### Required structure

```markdown
---
name: <stable-identifier>
when: <one-sentence applicability>
---

# <Title>

<Body — one or two paragraphs of obligation, no rationale. The body is the
single source of compliance language; it must be specific enough that
compliance can be verified directly from the entry without a separate
checklist.>

## Illustrations

**Bad — <one-line label>.** <Concrete bad example, 1–2 sentences.>
**Good:** <Concrete good counterpart, 1–2 sentences.>
```

The illustrations section may be omitted only when the obligation is so
trivially observable that examples would be padding. That is rare; default to
including them.

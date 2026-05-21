# Issues

This is the project's issue tracker. Issues live as markdown files on disk,
versioned with the code.

## Layout

```
docs/issues/
  README.md                 # this file
  NNNN-short-slug.md        # one file per issue
```

- Filenames begin with a zero-padded numeric ID (`0004-…`, `0123-…`). The ID is
  the issue's permanent name; the slug is descriptive and may be edited.
- New issues take the next available ID.
- IDs 0001–0010 mirror the legacy GitHub issue numbers from
  `mercuito/cli-agent-orchestrator` (migrated 2026-05-20). New IDs start at
  0011.
- No subfolders for status (we use frontmatter instead — see below). Subfolders
  are reserved for grouping unrelated issue families if the directory ever gets
  unwieldy.

## Frontmatter schema

Every issue starts with YAML frontmatter:

```yaml
---
id: 0004
status: ready            # pending | ready | in_progress | done | canceled
type: AFK                # AFK | HITL
title: Schema cutover + all current callers migrated in-place
parent: 0003             # optional — umbrella/parent issue ID
blocked_by: []           # list of issue IDs (numbers, not file paths)
labels: [inbox-refactor] # free-form tags for grouping
github_origin: 4         # optional — legacy GH issue this was migrated from
---
```

### Status flow

```
pending  → ready  → in_progress → done
                              ↘ canceled
```

- **pending**: written but not yet ready for work (waiting on info, draft, etc.)
- **ready**: fully specified, blockers resolved, free for an agent or human to pick up
- **in_progress**: someone is actively working on it (claim by setting status; commit before walking away)
- **done**: merged / shipped / completed
- **canceled**: not happening; leave a brief note in the body

A blocked-but-otherwise-ready issue stays `ready` with its `blocked_by` list non-empty. Agents/humans filter by both.

## Body template

```markdown
---
<frontmatter>
---

## Parent

[#NNNN](NNNN-slug.md) — optional cross-link to the umbrella

## What to build

End-to-end behavior, not layer-by-layer. Avoid file paths and code snippets
unless a precise decision (state machine, schema, type shape) is being pinned.

## Acceptance criteria

- [ ] Concrete, verifiable
- [ ] One row per criterion

## Review Gate

After implementing this task, run a review loop. The reviewer compares the landed implementation against each item in Acceptance criteria above plus all applicable entries in the `docs/criteria` catalog (run `uv run python scripts/catalog_criteria.py` and load any criterion whose `when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the review loop restarts with a fresh reviewer. For every review finding that requires an implementation change, the implementer updates [../completion-report.md](../completion-report.md) under this task's heading, recording what the reviewer found, why it was accepted as valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero valid findings for this task, and those two clean review passes are recorded in the completion report.

## Blocked by

- [#NNNN](NNNN-slug.md) — brief description

Or "None — can start immediately" if no blockers.
```

## How to pick the next issue

```bash
# Issues that are ready and have no open blockers:
grep -l "^status: ready" docs/issues/*.md \
  | xargs grep -L "blocked_by: \[[^]]" \
  || echo "Nothing ready"

# Or simpler: open the directory in your editor and scan the frontmatter.
```

An agent picking work should:

1. Read this README.
2. List `docs/issues/*.md`.
3. For each issue with `status: ready`, check that every entry in `blocked_by` resolves to an issue with `status: done`.
4. Pick the lowest ID that satisfies the above (or the one the user asks for).
5. Set `status: in_progress` and commit before starting code work.

## How to close an issue

- Set `status: done` in the frontmatter.
- Commit the status change in the same commit (or final follow-up commit) as the work.
- Don't move the file. Keeping `done` issues in the same directory preserves grep-ability and link stability.

## How to write a new issue

Pick the next free numeric ID, create `NNNN-short-slug.md`, fill in the frontmatter and template. If it's an umbrella, omit `parent` and list child IDs in the body.

## What lived here before

Before 2026-05-20 the project used a brief experiment with Linear (`yards-framework` org, `CAO` team — issue IDs like `CAO-42`) and a brief experiment with GitHub Issues at `mercuito/cli-agent-orchestrator`. Both surfaces still hold historical context worth reading, but new work lands here.

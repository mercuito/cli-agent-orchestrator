# Issue tracker: local markdown

Issues for this repo live as markdown files under `docs/issues/`, versioned with the code.

See `docs/issues/README.md` for the full convention. Quick reference for agents below.

## Conventions

- **Read an issue**: `Read docs/issues/NNNN-slug.md` (use the dedicated `Read` tool).
- **List issues**: directory listing; or `grep -l "^status: ready" docs/issues/*.md`.
- **Find the next ready issue**: scan for `status: ready` with all `blocked_by` entries pointing to `status: done` issues.
- **Claim an issue**: set `status: in_progress` in the frontmatter and commit before starting code work.
- **Close an issue**: set `status: done` in the frontmatter; commit alongside the work (or as a final follow-up commit). Do NOT move the file.
- **Create a new issue**: pick the next free numeric ID, create `NNNN-short-slug.md`, fill in the frontmatter and body template from `docs/issues/README.md`.

## Frontmatter

Every issue starts with YAML frontmatter:

```yaml
---
id: 0011
status: ready            # pending | ready | in_progress | done | canceled
type: AFK                # AFK | HITL
title: Short imperative title
parent: 0003             # optional umbrella/parent issue ID
blocked_by: []           # list of issue IDs
labels: [some-label]     # free-form tags
github_origin: 11        # optional — legacy GH issue this was migrated from
---
```

## When a skill says "publish to the issue tracker"

Create a new file under `docs/issues/`. Do not use `gh` for new issues unless the user explicitly asks for a GitHub issue.

## When a skill says "fetch the relevant ticket"

`Read docs/issues/NNNN-slug.md`. If the user gives only the issue ID, find the matching file by ID prefix.

## Legacy surfaces

Historical context may live in:

- **GitHub Issues** at `mercuito/cli-agent-orchestrator` — closed; all open work was migrated to `docs/issues/` on 2026-05-20.
- **Linear** at `yards-framework / CAO` team (issue IDs like `CAO-42`) — from an earlier experiment. Use the `linear-server` MCP tool to read for context; do not create new work there.

Cross-references in current `docs/issues/` files may point at these surfaces for predecessor decisions.

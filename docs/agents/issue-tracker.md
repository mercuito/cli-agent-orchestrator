# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues on `mercuito/cli-agent-orchestrator` (the `origin` remote). Use the `gh` CLI for all operations. There is also an `upstream` remote pointing at `awslabs/cli-agent-orchestrator` — do NOT target it for issue work unless explicitly asked.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

`gh` resolves the repo from `origin` automatically when run inside the clone — that's the right target.

## When a skill says "publish to the issue tracker"

Create a GitHub issue on `mercuito/cli-agent-orchestrator`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

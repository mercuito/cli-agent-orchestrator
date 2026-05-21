# Task 07 — Supersede ADR-0001 and ADR-0004; Write the New ADR

## Goal

Record the architectural shift in the project's ADR log. The two Linear-era
ADRs (0001 "Inbox: one agnostic concept" and 0004 "Provider-conversation
cache owned by Linear") no longer reflect the system; mark them as
superseded by a new ADR that captures the agent-to-agent-only inbox model.

## Preconditions

- Task 04 complete: the inbox is collapsed. The new ADR describes the
  shape that actually exists.

## Scope

1. **Annotate the superseded ADRs.** Do not delete them — ADRs are
   historical. Add a header to each:

   `docs/adr/0001-inbox-one-agnostic-concept.md` — add at the top, after
   the title:

   ```markdown
   **Status:** Superseded by ADR-0005 (Inbox: agent-to-agent only) on
   <YYYY-MM-DD>.

   This ADR captured the source-agnostic inbox shape that grew up around
   the Linear provider. With Linear removed, the agnostic shape no longer
   has any consumers and the inbox has been collapsed to a pure
   agent-to-agent queue. See ADR-0005 for the current model.
   ```

   `docs/adr/0004-provider-conversation-cache-owned-by-linear.md` — add
   at the top, after the title:

   ```markdown
   **Status:** Superseded by ADR-0005 (Inbox: agent-to-agent only) on
   <YYYY-MM-DD>.

   This ADR established Linear's ownership of the provider-conversation
   cache. Linear has been removed from CAO and the
   `provider_conversation_*` tables have been dropped. See ADR-0005.
   ```

2. **Write the new ADR.** File:
   `docs/adr/0005-inbox-agent-to-agent-only.md`.

   Use the project's ADR template (check existing ADRs for the convention).
   Sections to include:

   - **Title**: "Inbox: agent-to-agent only; provider integrations write
     through `send_message`"
   - **Status**: Accepted, with the date.
   - **Context**: Why the source-agnostic shape existed (Linear's
     provider-conversation bridge), why it was expensive (≈1500 lines
     supporting "make a Linear ping look like a direct message"), and why
     the Linear deletion makes the agnostic shape pure overhead.
   - **Decision**: The inbox stores only agent-to-agent messages. Every
     notification has exactly one `sender_agent_id`, one `receiver_agent_id`,
     and a body. No `source_kind`, no provider routing, no reply registry.
     Provider integrations that observe external events (GitHub webhooks,
     future Linear-style pings) compose a normal message and call
     `send_message` themselves; from the inbox's perspective they are
     indistinguishable from an agent-authored message. Provider-mediated
     replies happen through provider tools (`github.comment_on_pr`,
     future `linear.comment_on_issue`, etc.), not through a generic
     `reply_to_inbox_message` verb.
   - **Consequences**:
     - The inbox API surface collapses to `send` and `read`.
     - `read_inbox_message` returns the body. `reply_to_inbox_message`
       no longer exists.
     - Agents make routing decisions explicitly: reply via `send_message`
       to another agent, or via a provider's own tool to reply on the
       provider's surface. The previous "magic reply" path is gone.
     - The `workspace_tool_providers/` framework remains in place for
       future providers (the next workstream adds a `local` provider) but
       no longer registers any provider by default.
     - Provider-mediated reply convenience that Linear's bridge offered
       is intentionally not replicated. Each new provider that wants to
       deliver pings as inbox messages composes a textual message (e.g.
       "Alice mentioned you on PR #42: 'can you look at this?'") and
       calls `send_message` like any other writer.
   - **Alternatives Considered**:
     - Keep the source-agnostic shape for hypothetical future providers.
       Rejected: speculative generality, and the local provider that is
       actually coming next has no need for it.
     - Fold provider replies into `send_message` via routing parameters.
       Rejected: hidden routing magic harms clarity; explicit per-provider
       reply tools keep the agent's decision visible.
   - **Migration Notes**: see `docs/plans/delete-linear-provider/`. The
     SQLite migration drops `provider_conversation_*` and
     `linear_monitor_watermarks` tables and removes `source_kind`,
     `source_id`, `metadata_json` columns from `inbox_notifications`.

3. Cross-link: update any other docs that reference ADR-0001 or ADR-0004
   to also mention the supersession.

## Out of Scope

- Inbox code changes (Task 04).
- DB migration (Task 05).
- Web UI changes (Task 06).

## Acceptance Criteria

1. `docs/adr/0001-inbox-one-agnostic-concept.md` and
   `docs/adr/0004-provider-conversation-cache-owned-by-linear.md` are
   annotated as superseded with the date and link to ADR-0005.
2. `docs/adr/0005-inbox-agent-to-agent-only.md` exists and follows the
   project's ADR convention.
3. `grep -rn "0001-inbox-one-agnostic\|0004-provider-conversation" docs/`
   does not flag any reference that fails to mention the supersession.
4. ADR-0005 is concise (≤ 2 pages rendered). It describes what is true
   now, not the history of every iteration.

## Criteria to Consult

This task is documentation-only, so the implementation criteria are
mostly not load-bearing, but:

- `readable-and-explicit` — Names match the new model. No leftover
  references to `source_kind` or `provider_conversation` in the new ADR.
- `do-not-assume-backwards-compatibility` — The new ADR does not
  hedge with "in some cases we might keep..." language. It commits.
- `authoritative-sources-are-referenced-not-copied` — When ADR-0005
  needs to point at code, link the file path; do not duplicate code
  blocks that will rot.

## Notes for the Implementing Agent

- Check `docs/adr/` for the existing convention. Some projects number
  ADRs as `NNNN-slug.md`, others as `NNNN-slug/index.md`. Match the
  existing pattern in this repo.
- The supersession header on 0001 and 0004 must not destroy the
  historical narrative inside — those ADRs are the record of why the
  agnostic shape was tried. The header sits at the top and points
  forward; the body stays.
- Today's date in CAO is in the user's MEMORY.md (`Today's date is
  2026-05-20.`). Use the actual completion date when writing the
  supersession line, not 2026-05-20 if the work lands later.

# Task 08 — Final Full-Suite Test Pass and Verification

## Goal

Confirm the branch is shippable. Run every available check, exercise the
inbox flow manually in a real terminal, and write the completion notes.

## Preconditions

- Tasks 01–07 complete.
- Branch `delete-linear-provider` carries the full deletion + collapse.

## Scope

1. **Backend test suite:**

   ```bash
   uv run pytest -q
   ```

   Must exit 0.

2. **Type check** (if the project runs one):

   ```bash
   uv run mypy src/
   ```

   Any errors that surfaced because of the deletions need to be fixed. Do
   not silence with `# type: ignore` — fix the cause.

3. **Web suite:**

   ```bash
   cd web && npm run test:run && npm run build
   ```

   Tests pass; build succeeds; bundle written to
   `src/cli_agent_orchestrator/web_ui/assets/`.

4. **Real-flow manual verification.** Start CAO and confirm the
   end-to-end agent-to-agent flow works:

   ```bash
   uv run cao serve
   ```

   In another terminal or via the dashboard, start two agents (`agent_a`
   and `agent_b`). From `agent_a`, call `send_message(receiver_agent_id="agent_b", body="hello")`.
   Observe:

   - The message appears in `agent_b`'s terminal once it becomes idle.
   - The terminal output ends with `notification_id=<id>`.
   - `agent_b` calls `read_inbox_message(notification_id=<id>)` and gets
     the body back with the sender id as `from`.
   - There is no `reply_to_inbox_message` tool available.

   Document the exact agent IDs used, the messages sent, the notification
   ids observed, and the read responses in the completion notes.

5. **DB schema check.** Inspect the live SQLite file after a fresh boot:

   ```bash
   sqlite3 ~/.cli-agent-orchestrator/cao.db ".schema inbox_notifications"
   sqlite3 ~/.cli-agent-orchestrator/cao.db ".tables"
   ```

   Confirm `inbox_notifications` columns are
   `(id, sender_agent_id, receiver_agent_id, body, status, created_at,
   delivered_at, failed_at, error_detail)` and the
   `provider_conversation_*` / `linear_monitor_*` tables are absent.

6. **Grep guards.** None of these should return matches outside the
   `docs/plans/delete-linear-provider/` directory and the supersession
   notes in superseded ADRs:

   ```bash
   grep -rn "cli_agent_orchestrator.linear" src/ test/
   grep -rn "LinearConfig\|LinearToolAccessConfig" src/ test/
   grep -rn "provider_conversation_decision\|ProviderConversationAccessRequirement" src/
   grep -rn "source_kind\|source_id\|notification_metadata\|register_reply_handler" src/cli_agent_orchestrator/inbox/
   ```

7. **Write `docs/plans/delete-linear-provider/completion-report.md`.**
   Capture, in 1–2 pages:

   - The final shape of the inbox (link to the ADR).
   - What was deleted (rough LoC accounting is enough).
   - The criteria catalog evaluation: which criteria applied to the final
     diff and how each was satisfied.
   - The manual verification log from step 4.
   - Any follow-up tasks that surfaced and were not folded in.

8. **Final commit.** If everything is green, the branch is ready to
   merge to `main`. Do not push or merge without the user's explicit go.

## Acceptance Criteria

1. All six grep guards in step 6 are empty.
2. Backend `pytest` exits 0.
3. Web `npm run test:run` exits 0.
4. `npm run build` exits 0 and the bundle in `web_ui/assets/` is current.
5. Manual flow in step 4 succeeded; log in completion report.
6. `mypy src/` exits 0 (or matches the project's accepted baseline).
7. `completion-report.md` exists at the plan root and includes the
   catalog evaluation section.

## Criteria to Consult

This task is verification, so the criteria are applied as *checks* against
the cumulative diff, not as authors of new code:

- Every "Always." implementation criterion.
- Every "Always." test criterion.
- `ui-changes-require-real-browser-verification` — Task 06 should have
  documented the browser pass; confirm it exists in this task's
  completion-report section.
- `migration-discipline` — Confirm the migration regression test from
  Task 05 covers the pre-collapse → post-collapse DB.

## Notes for the Implementing Agent

- If any grep guard fires, fix the root cause; do not paper over.
- The completion report is the artifact downstream readers will find when
  they ask "what happened to Linear?". Make it self-contained: include
  the why (Linear was over-iterated, the convenience was inverted), the
  what (inbox collapsed to agent-to-agent), and the where (link the ADR
  and the relevant code paths). Skip narrative about the process of
  doing the work; focus on the resulting shape.

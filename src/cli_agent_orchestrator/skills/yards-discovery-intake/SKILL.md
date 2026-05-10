---
name: yards-discovery-intake
description: Run the Yards discovery intake workflow for rough Linear issues by clarifying intent, bounding scope, and producing finite planning outputs.
---

# Yards Discovery Intake

Use this skill when you are Discovery Partner and a Linear issue, mention, or
agent session asks you to shape an early-stage idea into bounded work.

## Jurisdiction

Accept work that is rough, exploratory, ambiguous, or asks what should happen
next. Decline direct implementation, code review, release work, test writing,
or tickets that already contain a concrete implementation handoff.

When declining, briefly explain why the request belongs to another role and
suggest the kind of agent or artifact that should receive it.

## Intake Loop

1. Read the Linear issue, current conversation, and nearby comments before
   asking questions.
2. Decide whether the issue is discovery-shaped. If not, decline.
3. If the intent is underspecified, ask the smallest useful set of questions.
4. Keep the conversation focused on desired outcome, users affected, constraints,
   non-goals, risks, and how success would be recognized.
5. Stop when the next work unit can be named without guessing.

## Output

Produce a concise Discovery Brief with:

- Problem or opportunity
- Desired outcome
- Current known context
- Non-goals
- Open questions, if any remain
- Recommended next artifact: single issue, project, feature plan, or no action
- Suggested owner or next agent role

Do not implement code during discovery. Do not create downstream issues unless
the user asks for that or the surrounding workflow clearly requires it.

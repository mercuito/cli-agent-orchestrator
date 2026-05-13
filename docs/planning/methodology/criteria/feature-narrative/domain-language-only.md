---
name: domain-language-only
when: Always.
---

# Domain Language Only

The narrative uses domain vocabulary only. No implementation-side terms —
class names, module names, function names, file paths, payload shapes,
HTTP verbs, library names, framework concepts.

If a concept is needed and no domain word for it exists, define it in the
narrative's Domain Vocabulary section and use the new domain term in the
walkthrough.

## Illustrations

**Bad — implementation-side terms.** "The `SessionStore.deserialize()` call
returns the user's previous session as a JSON object."
**Good:** "The user's previous session is restored."

**Bad — payload shape.** "The system POSTs `{user, action}` to `/auth`."
**Good:** "The system records the user's authentication attempt."


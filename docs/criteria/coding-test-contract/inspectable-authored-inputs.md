---
name: inspectable-authored-inputs
when: A test supplies authored content that affects the assertion.
---

# Authored Test Inputs Stay Inspectable

Behavior-relevant authored content must be visible from the leaf test, a
narrowly named builder with explicit inputs, or a clearly named fixture path.
Broad setup helpers must not hide the authored example that explains the
assertion.

Authored content includes config, schemas, Markdown/frontmatter, procedure
files, scenario files, patches, request payloads, and malformed examples.

## Illustrations

**Bad - hidden fixture.** A test calls `createPassingScenario()` and asserts a
specific shell output.
**Good:** The shell-output YAML is inline, passed to a named builder, or stored
in a fixture named for that output case.

**Bad - vague config helper.** `setupHappyPathProvider()` creates the config
whose invalid field is under test.
**Good:** `linearConfigWithUnknownAgentReference()` exposes the authored case.

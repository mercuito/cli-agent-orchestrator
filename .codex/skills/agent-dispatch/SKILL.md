---
name: agent-dispatch
description: Dispatch repository agents with explicit context boundaries. Use when spawning, delegating to, or orchestrating subagents, workers, explorers, reviewers, or parallel agents in this repository, especially when deciding whether to fork the current conversation context.
---

# Agent Dispatch

## Overview

Use this skill to keep agent delegation intentional and bounded. The default
dispatch posture is to pass a focused task packet, not the current thread's full
conversation history.

## Core Rules

1. Do not fork the current context unless the user explicitly asks for it.
2. Wait on the agent to complete, do not end your turn until the agent has finished its task and returned its output.

## Dispatch Packet

Give each dispatched agent a self-contained packet with only the context it
needs:

- Grounded acceptance criteria or definition of done relevant to the task;
- owned files, directories, or responsibility area;
- relevant source artifacts, paths, commands, and constraints;
- coordination notes, including that other users or agents may be editing the
  same repository and unrelated changes must not be reverted;
- verification expectations or what evidence to return.

Prefer passing precise files, snippets, paths, or short summaries over inheriting
thread history. If the agent needs information discovered in the current thread,
summarize the needed facts explicitly in the prompt.

## Forking Exception

Fork context only for explicit requests such as:

- "fork this context to an agent";
- "give the agent the full thread";
- "spawn an agent with the same context";
- "have a subagent continue from everything we've discussed."

When using the exception, still keep the delegated task concrete and state why a
full-context fork is being used.

## Examples

Default dispatch:

```json
{
  "agent_type": "explorer",
  "message": "Inspect the provider tests under test/providers and report the status-detection fixtures that would need updates. Do not edit files.",
  "fork_context": false
}
```

Explicit full-context dispatch:

```json
{
  "agent_type": "worker",
  "message": "Continue from the full thread context and implement the task slice we just discussed.",
  "fork_context": true
}
```

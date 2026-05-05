# Linear-backed Yards Workflow — Agent Presence Plan

**Status:** scoping. This document captures the current working model for
using Linear as the visible workflow surface while CAO owns local agent
execution.

## Goal

Let a human start from a normal Linear issue, delegate or mention a
CAO-backed Linear agent, and have CAO keep the matching local agent
operational. The agent's CAO profile/system prompt supplies the workflow
procedure until the Yards framework has local procedure execution.

Linear owns work state. CAO owns runtime presence.

## Core Model

### Linear

- **Workspace:** account boundary where the Linear app user exists.
- **Team:** issue lane and access scope for the app user.
- **Issue:** visible work unit, discussion thread, and completion state.
- **Linear agent / app user:** named presence such as `Discovery Partner`.
- **Agent session:** optional Linear conversation/run surface when the agent or
  human needs Linear-native interaction.

### CAO

- **Team member:** local mapping from a Linear app user to one CAO profile.
- **Agent profile:** narrow role prompt that defines accepted work, refusal
  rules, workflow procedure, communication policy, and completion behavior.
- **Terminal:** live manifestation of one team member. For the first version,
  each team member has at most one active terminal.

## First Agent

Use one Linear app user:

```text
Linear app user: Discovery Partner
CAO team member: cao-discovery-partner
CAO profile: yards-discovery-partner
Workflow: yards/discovery
Max active terminals: 1
```

The Discovery Partner accepts unbounded or early-stage ideas and turns them
into bounded work. It refuses implementation, code review, test/release work,
and already-bounded execution tickets.

## Dispatcher Responsibility

The dispatcher should stay mechanical:

1. Receive a Linear signal such as an agent mention, delegation, or agent
   session event.
2. Identify the Linear app user.
3. Find the mapped CAO team member.
4. Check whether that team member already has an operational terminal.
5. Start or wake the terminal if needed.
6. Deliver the Linear issue/session context to that terminal.

The dispatcher should not decide the full workflow. It should not create a
local assignment record that duplicates Linear state.

## Agent Responsibility

The agent profile owns the procedure:

1. Read the assigned/delegated issue, comments, and linked artifacts.
2. Decide whether the issue is within its jurisdiction.
3. Refuse out-of-scope work by commenting in Linear and leaving the issue open.
4. Choose the communication channel from issue context and user availability:
   Linear agent session, Linear comments, or CAO dashboard terminal.
5. For accepted work, follow the Yards discovery workflow.
6. Produce or update planning artifacts.
7. Create or recommend bounded follow-up Linear issues/projects.
8. Mark the issue complete only after required outputs exist.

## Communication

Opening a Linear agent session is not automatic on assignment. It is one
available communication channel.

The agent should use a Linear agent session when the issue or user context
requests Linear-based conversation, especially when the user is away from the
CAO dashboard. Otherwise the CAO dashboard terminal can be the direct
conversation surface.

## OAuth And Webhooks

The first integration needs:

- a Linear OAuth app named `Discovery Partner`
- `actor=app` installation so Linear creates app-user presence
- app scopes for being assignable/mentionable and for the minimal issue/comment
  operations needed by the workflow
- a public HTTPS CAO callback URL, currently exposed through Tailscale Funnel
- CAO routes:
  - `GET /linear/oauth/callback`
  - `POST /linear/webhooks/agent`

The OAuth callback installs the app and records the Linear app user identity.
The webhook route receives Linear agent/session events and starts or wakes the
mapped CAO team member.

## Implementation Slices

### Slice 1: Local HTTPS Bridge

Expose CAO through Tailscale Funnel and allow the Funnel hostname through
CAO's trusted host middleware.

### Slice 2: Linear OAuth Callback

Implement the OAuth callback, exchange the install code for Linear tokens, and
fetch the installed app user's `viewer { id name }`.

### Slice 3: Agent Webhook Receiver

Implement a minimal Linear webhook endpoint for agent/session events. Verify
signatures before acting on events.

### Slice 4: Team Member Mapping

Add config that maps Linear app user identity to a CAO team member and agent
profile.

### Slice 5: Presence Reconciler

Given a Linear event for `Discovery Partner`, start or reuse exactly one local
terminal for `cao-discovery-partner` and deliver the issue/session context.

### Slice 6: Discovery Partner Profile

Create the `yards-discovery-partner` profile with:

- jurisdiction rules
- refusal behavior
- discovery workflow instructions
- communication-channel policy
- completion rules

### Slice 7: End-to-end Smoke Test

Delegate or mention `Discovery Partner` on a Linear issue in the CAO team and
verify:

- Linear reaches CAO webhook
- CAO maps the Linear agent to `cao-discovery-partner`
- CAO starts or reuses the terminal
- the terminal receives issue context and workflow instructions
- the agent can respond through the chosen channel

## Deferred

- Multi-agent workflow graph
- Review/implementation/test specialist app users
- Strict Yards completion gates
- Linear project/issue graph materialization from Yards artifacts
- Recovery monitor for stale sessions or stopped local terminals

# CAO-79 Provider Event Notification Context Design

## Target Model

Workspace providers publish a typed, declared set of domain events. A provider
event is the traceable unit that moves through CAO when an agent is notified.
When CAO is about to notify an agent, the notification must carry the provider
event that caused it.

Workspace context resolution is agent-identity scoped. CAO asks the workspace
context resolver configured for the target agent identity to resolve the
workspace context for the traced provider event. CAO then activates that
identity-local workspace context before delivering the notification to the
agent runtime.

The resolver operates on provider events, not on untyped notification text, the
current terminal, or whichever event happened most recently.

## Required Flow

1. A workspace provider receives or creates domain activity.
2. The provider publishes a typed event from its declared event set.
3. If the event should notify an agent, the provider asks CAO to deliver a
   notification and passes the same provider event with the notification.
4. CAO looks up the target agent identity.
5. CAO asks that identity's configured workspace context resolver to resolve
   the workspace context for the provider event.
6. CAO activates the resolved identity-local workspace context.
7. CAO delivers the notification to the agent runtime.

## Linear Event Set Direction

Linear must not publish only a broad `agent_session` event and require
subscribers to rediscover the semantic meaning. Linear should publish semantic
events that match the work CAO needs to reason about, including at least:

- `linear.agent_mentioned`
- `linear.issue_delegated_to_agent`
- `linear.agent_session_prompted`
- `linear.agent_session_lifecycle_activity`
- `linear.agent_session_stop_requested`
- `linear.issue_created`

The current `linear.agent_session` event is too broad because it collapses human
mentions, issue delegation, follow-up prompts, stop requests, lifecycle
activity, and app-created session bootstraps into one bucket. That shape is not
the intended final model.

## Resolver Contract

A workspace context resolver is associated with an agent identity. The resolver
receives typed provider events and returns the workspace context that should be
active for that identity when CAO handles the event.

The resolver may use provider-specific event payloads and provider APIs to make
that decision. The resolver should be the place where cross-provider workflow
knowledge lives when a workflow depends on multiple providers.

## Notification Traceability Requirement

Every provider-triggered agent notification must preserve the provider event
that caused it. CAO must not infer notification context from timing, terminal
state, notification text, or the last event seen by a resolver.

If a notification cannot be traced to a provider event, that path is incomplete
for workspace-context switching and should fail implementation review for this
work.

## Original Implementation Gap

The first provider-event implementation added a provider event dispatcher and
Linear event publication, but the Linear event set was too thin. Human mentions
were represented only as classified metadata inside a generic
`linear.agent_session` event. That meant context resolution could work for the
narrow AgentSession path while still being architecturally wrong for the
intended provider-event model.

The implementation must keep Linear publication and notification delivery
centered on semantic Linear provider events, then have workspace context
resolution consume those events through the agent identity's configured
resolver. Reintroducing a broad `linear.agent_session` event as the notification
trace would regress this design.

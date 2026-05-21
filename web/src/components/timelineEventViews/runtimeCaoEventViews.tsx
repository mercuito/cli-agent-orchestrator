import { Bell, GitCompareArrows, Inbox, LifeBuoy, Monitor, Radio, UserCheck } from 'lucide-react'
import {
  AGENT_READY,
  AGENT_RUNTIME_LIFECYCLE_EVENT,
  AGENT_RUNTIME_NOTIFICATION_ACCEPTED_EVENT,
  AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
  AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT,
  RUNTIME_WORKSPACE_EVENT,
} from '../../generated/caoEventPayloadTypes'
import type {
  KnownTimelineEventView,
  KnownTimelineEventViewProps,
  TimelineEventViewRegistration,
} from '../timelineEventViews'
import { timelineEventViewRegistration } from '../timelineEventViews'
import {
  DetailPill,
  EntityReferenceButton,
  Snippet,
  ViewShell,
  booleanFact,
  firstFact,
  labelize,
  primitiveFact,
  stringFact,
} from './shared'

const AgentReadyTimelineEventView: KnownTimelineEventView<typeof AGENT_READY> = ({
  event,
}: KnownTimelineEventViewProps<typeof AGENT_READY>) => {
  const data = event.event_data
  const agentId = stringFact(data.agent_id) ?? 'Unknown agent'

  return (
    <ViewShell
      icon={<UserCheck size={15} />}
      title={`Agent ${agentId} ready`}
    >
      <DetailPill label="Agent" value={agentId} tone="emerald" />
    </ViewShell>
  )
}

const RuntimeAcceptedTimelineEventView: KnownTimelineEventView<
  typeof AGENT_RUNTIME_NOTIFICATION_ACCEPTED_EVENT
> = ({
  event,
}: KnownTimelineEventViewProps<typeof AGENT_RUNTIME_NOTIFICATION_ACCEPTED_EVENT>) => {
  const data = event.event_data
  const notificationId = primitiveFact(data.inbox_notification_id) ?? 'Unknown notification'
  const receiver = firstFact(data.receiver_agent_id, data.agent_id) ?? 'Unknown receiver'
  const sender = firstFact(data.sender_agent_id) ?? 'Unknown sender'
  const workspace = firstFact(data.workspace_context_id) ?? 'Unknown workspace'

  return (
    <ViewShell
      icon={<Inbox size={15} />}
      title={`Notification ${notificationId} accepted`}
    >
      <DetailPill label="Receiver" value={receiver} tone="emerald" />
      <DetailPill label="Sender" value={sender} tone="blue" />
      <DetailPill label="Workspace" value={workspace} tone="purple" />
    </ViewShell>
  )
}

const RuntimeDeliveryTimelineEventView: KnownTimelineEventView<
  typeof AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT
> = ({
  event,
  onFocusTerminal,
}: KnownTimelineEventViewProps<typeof AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT>) => {
  const data = event.event_data
  const message =
    stringFact(data.message_body) ?? 'No message text recorded'
  const terminalTarget = stringFact(data.terminal_id)
  const terminalId = terminalTarget ?? 'No terminal recorded'
  const outcome = stringFact(data.outcome) ?? 'unknown outcome'

  return (
    <ViewShell
      icon={<Bell size={15} />}
      title={`Mention delivered to terminal ${terminalId}`}
    >
      <DetailPill label="Terminal" value={terminalId} tone="emerald" />
      <DetailPill label="Outcome" value={outcome} />
      {terminalTarget && onFocusTerminal && (
        <EntityReferenceButton
          label="Open terminal"
          ariaLabel={`Open terminal ${terminalTarget}`}
          icon={<Monitor size={12} />}
          onClick={() => onFocusTerminal(terminalTarget)}
        />
      )}
      <Snippet text={message} />
    </ViewShell>
  )
}

const WorkspaceContextSwitchTimelineEventView: KnownTimelineEventView<
  typeof AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT
> = ({
  event,
}: KnownTimelineEventViewProps<typeof AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT>) => {
  const data = event.event_data
  const fromContext =
    stringFact(data.from_workspace_context_id) ??
    'Unknown from context'
  const toContext =
    stringFact(data.to_workspace_context_id) ?? 'Unknown to context'
  const outcome = stringFact(data.outcome) ?? 'context changed'

  return (
    <ViewShell
      icon={<GitCompareArrows size={15} />}
      title="Workspace context changed"
    >
      <DetailPill label="From" value={fromContext} tone="purple" />
      <DetailPill label="To" value={toContext} tone="emerald" />
      <DetailPill label="Outcome" value={outcome} />
    </ViewShell>
  )
}

const RuntimeLifecycleTimelineEventView: KnownTimelineEventView<typeof AGENT_RUNTIME_LIFECYCLE_EVENT> = ({
  event,
}: KnownTimelineEventViewProps<typeof AGENT_RUNTIME_LIFECYCLE_EVENT>) => {
  const data = event.event_data
  const action =
    stringFact(data.action) ?? 'unknown lifecycle phase'
  const runtimeStatus =
    stringFact(data.runtime_status) ?? 'unknown status'
  const terminalId =
    stringFact(data.terminal_id) ?? 'No terminal recorded'
  const workspaceContext =
    stringFact(data.workspace_context_id) ??
    'Unknown workspace context'
  const ready = booleanFact(data.ready)
  const health = ready === false ? 'attention needed' : runtimeStatus

  return (
    <ViewShell
      icon={<LifeBuoy size={15} />}
      title={`Runtime ${action}`}
    >
      <DetailPill label="Phase" value={action} tone="amber" />
      <DetailPill label="Status" value={health} />
      <DetailPill label="Terminal" value={terminalId} tone="emerald" />
      <DetailPill label="Workspace" value={workspaceContext} tone="purple" />
    </ViewShell>
  )
}

const RuntimeWorkspaceTimelineEventView: KnownTimelineEventView<typeof RUNTIME_WORKSPACE_EVENT> = ({
  event,
}: KnownTimelineEventViewProps<typeof RUNTIME_WORKSPACE_EVENT>) => {
  const data = event.event_data
  const action = stringFact(data.action) ?? 'workspace activity'
  const workspace = stringFact(data.workspace_context_id) ?? 'Unknown workspace'
  const runtimeStatus = stringFact(data.runtime_status) ?? 'unknown status'
  const error = stringFact(data.error)

  return (
    <ViewShell
      icon={<Radio size={15} />}
      title={`Runtime ${action}`}
    >
      <DetailPill label="Workspace" value={workspace} tone="purple" />
      <DetailPill label="Status" value={runtimeStatus} tone="emerald" />
      {error && <DetailPill label="Error" value={error} tone="amber" />}
    </ViewShell>
  )
}

export const timelineEventViewRegistrations: TimelineEventViewRegistration[] = [
  timelineEventViewRegistration(AGENT_READY, AgentReadyTimelineEventView),
  timelineEventViewRegistration(
    AGENT_RUNTIME_NOTIFICATION_ACCEPTED_EVENT,
    RuntimeAcceptedTimelineEventView,
  ),
  timelineEventViewRegistration(
    AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
    RuntimeDeliveryTimelineEventView,
  ),
  timelineEventViewRegistration(
    AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT,
    WorkspaceContextSwitchTimelineEventView,
  ),
  timelineEventViewRegistration(AGENT_RUNTIME_LIFECYCLE_EVENT, RuntimeLifecycleTimelineEventView),
  timelineEventViewRegistration(RUNTIME_WORKSPACE_EVENT, RuntimeWorkspaceTimelineEventView),
]

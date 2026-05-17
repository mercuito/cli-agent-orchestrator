import {
  ClipboardCheck,
  ExternalLink,
  MessageSquareText,
  PlusCircle,
  RotateCcw,
  SquareStop,
} from 'lucide-react'
import {
  LINEAR_AGENT_MENTIONED_EVENT,
  LINEAR_AGENT_SESSION_LIFECYCLE_ACTIVITY_EVENT,
  LINEAR_AGENT_SESSION_PROMPTED_EVENT,
  LINEAR_AGENT_SESSION_STOP_REQUESTED_EVENT,
  LINEAR_ISSUE_CREATED_EVENT,
  LINEAR_ISSUE_DELEGATED_TO_AGENT_EVENT,
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
  firstFact,
  objectFact,
  objectStringFact,
  stringFact,
} from './shared'

function linearIssueIdentifier(data: Record<string, unknown>): string {
  return firstFact(data.issue_identifier, data.issue_id) ?? 'Unknown issue'
}

function linearIssueTitle(data: Record<string, unknown>): string {
  return firstFact(data.issue_title) ?? 'Untitled Linear issue'
}

function linearActor(data: Record<string, unknown>, fallback = 'Unknown teammate'): string {
  return firstFact(data.app_user_name, data.app_user_id) ?? fallback
}

function linearMessage(data: Record<string, unknown>, fallback: string): string {
  return firstFact(data.message_body, data.prompt_context) ?? fallback
}

function LinearIssueLink({
  issueUrl,
  issueContext,
  onOpenExternalReference,
}: {
  issueUrl: string | null
  issueContext: string
  onOpenExternalReference?: (url: string) => void
}) {
  if (!issueUrl || !onOpenExternalReference) return null
  return (
    <EntityReferenceButton
      label="Open in Linear"
      ariaLabel={`Open Linear issue ${issueContext}`}
      icon={<ExternalLink size={12} />}
      onClick={() => onOpenExternalReference(issueUrl)}
    />
  )
}

const LinearMentionTimelineEventView: KnownTimelineEventView<typeof LINEAR_AGENT_MENTIONED_EVENT> = ({
  event,
  onOpenExternalReference,
}: KnownTimelineEventViewProps<typeof LINEAR_AGENT_MENTIONED_EVENT>) => {
  const data = event.event_data
  const issueIdentifier =
    stringFact(data.issue_identifier) ??
    stringFact(data.issue_id)
  const issueTitle =
    stringFact(data.issue_title) ?? 'Untitled Linear issue'
  const issueUrl = stringFact(data.issue_url)
  const mentioner =
    stringFact(data.app_user_name) ??
    stringFact(data.app_user_id) ??
    'Unknown teammate'
  const message =
    stringFact(data.message_body) ?? 'No mention text recorded'
  const issueContext = issueIdentifier ?? 'Unknown issue'

  return (
    <ViewShell
      icon={<MessageSquareText size={15} />}
      title={`${mentioner} mentioned this agent`}
    >
      <DetailPill label="Linear issue" value={issueContext} tone="blue" />
      <DetailPill label="Title" value={issueTitle} />
      <DetailPill label="Mentioner" value={mentioner} tone="emerald" />
      <LinearIssueLink
        issueUrl={issueUrl}
        issueContext={issueContext}
        onOpenExternalReference={onOpenExternalReference}
      />
      <Snippet text={message} />
    </ViewShell>
  )
}

const LinearIssueDelegatedTimelineEventView: KnownTimelineEventView<
  typeof LINEAR_ISSUE_DELEGATED_TO_AGENT_EVENT
> = ({
  event,
  onOpenExternalReference,
}: KnownTimelineEventViewProps<typeof LINEAR_ISSUE_DELEGATED_TO_AGENT_EVENT>) => {
  const data = event.event_data
  const issueContext = linearIssueIdentifier(data)
  const issueTitle = linearIssueTitle(data)
  const issueState = firstFact(data.issue_state) ?? 'Unknown state'
  const agent = firstFact(data.agent_id) ?? 'Unknown agent'
  const actor = linearActor(data)
  const issueUrl = stringFact(data.issue_url)
  const message = linearMessage(data, 'No delegation message recorded')

  return (
    <ViewShell
      icon={<ClipboardCheck size={15} />}
      title={`${issueContext} delegated to ${agent}`}
    >
      <DetailPill label="Issue" value={issueContext} tone="blue" />
      <DetailPill label="Title" value={issueTitle} />
      <DetailPill label="State" value={issueState} tone="amber" />
      <DetailPill label="Agent" value={agent} tone="emerald" />
      <DetailPill label="Actor" value={actor} />
      <LinearIssueLink
        issueUrl={issueUrl}
        issueContext={issueContext}
        onOpenExternalReference={onOpenExternalReference}
      />
      <Snippet text={message} />
    </ViewShell>
  )
}

const LinearAgentSessionPromptedTimelineEventView: KnownTimelineEventView<
  typeof LINEAR_AGENT_SESSION_PROMPTED_EVENT
> = ({
  event,
  onOpenExternalReference,
}: KnownTimelineEventViewProps<typeof LINEAR_AGENT_SESSION_PROMPTED_EVENT>) => {
  const data = event.event_data
  const issueContext = linearIssueIdentifier(data)
  const issueTitle = linearIssueTitle(data)
  const sessionId = firstFact(data.agent_session_id) ?? 'Unknown session'
  const threadId = firstFact(data.thread_id) ?? 'Unknown thread'
  const actor = linearActor(data)
  const threadUrl = stringFact(data.thread_url)
  const issueUrl = stringFact(data.issue_url)
  const message = linearMessage(data, 'No prompt text recorded')

  return (
    <ViewShell
      icon={<MessageSquareText size={15} />}
      title={`${actor} prompted session ${sessionId}`}
    >
      <DetailPill label="Issue" value={issueContext} tone="blue" />
      <DetailPill label="Title" value={issueTitle} />
      <DetailPill label="Session" value={sessionId} tone="emerald" />
      <DetailPill label="Thread" value={threadId} />
      {threadUrl && onOpenExternalReference && (
        <EntityReferenceButton
          label="Open thread"
          ariaLabel={`Open Linear thread ${threadId}`}
          icon={<ExternalLink size={12} />}
          onClick={() => onOpenExternalReference(threadUrl)}
        />
      )}
      <LinearIssueLink
        issueUrl={issueUrl}
        issueContext={issueContext}
        onOpenExternalReference={onOpenExternalReference}
      />
      <Snippet text={message} />
    </ViewShell>
  )
}

const LinearSessionLifecycleActivityTimelineEventView: KnownTimelineEventView<
  typeof LINEAR_AGENT_SESSION_LIFECYCLE_ACTIVITY_EVENT
> = ({
  event,
}: KnownTimelineEventViewProps<typeof LINEAR_AGENT_SESSION_LIFECYCLE_ACTIVITY_EVENT>) => {
  const data = event.event_data
  const issueContext = linearIssueIdentifier(data)
  const issueTitle = linearIssueTitle(data)
  const sessionId = firstFact(data.agent_session_id) ?? 'Unknown session'
  const action = firstFact(data.action) ?? 'session activity'
  const messageKind = firstFact(data.message_kind) ?? 'Unknown message kind'
  const shouldNotify = typeof data.should_notify_agent === 'boolean' ? data.should_notify_agent : null
  const notifyStatus = shouldNotify === false ? 'suppressed' : 'notify agent'
  const suppressionReason = firstFact(data.suppression_reason)

  return (
    <ViewShell
      icon={<RotateCcw size={15} />}
      title={`Session ${action}`}
    >
      <DetailPill label="Issue" value={issueContext} tone="blue" />
      <DetailPill label="Title" value={issueTitle} />
      <DetailPill label="Session" value={sessionId} tone="emerald" />
      <DetailPill label="Action" value={action} tone="amber" />
      <DetailPill label="Message" value={messageKind} />
      <DetailPill label="Notify" value={notifyStatus} />
      {suppressionReason && <DetailPill label="Suppression" value={suppressionReason} tone="amber" />}
    </ViewShell>
  )
}

const LinearSessionStopRequestedTimelineEventView: KnownTimelineEventView<
  typeof LINEAR_AGENT_SESSION_STOP_REQUESTED_EVENT
> = ({
  event,
}: KnownTimelineEventViewProps<typeof LINEAR_AGENT_SESSION_STOP_REQUESTED_EVENT>) => {
  const data = event.event_data
  const issueContext = linearIssueIdentifier(data)
  const issueTitle = linearIssueTitle(data)
  const sessionId = firstFact(data.agent_session_id) ?? 'Unknown session'
  const requester = linearActor(data, 'Unknown requester')
  const action = firstFact(data.action) ?? 'stop requested'
  const message = linearMessage(data, 'No stop reason recorded')

  return (
    <ViewShell
      icon={<SquareStop size={15} />}
      title={`${requester} requested ${action}`}
    >
      <DetailPill label="Issue" value={issueContext} tone="blue" />
      <DetailPill label="Title" value={issueTitle} />
      <DetailPill label="Session" value={sessionId} tone="emerald" />
      <DetailPill label="Requester" value={requester} />
      <DetailPill label="Action" value={action} tone="amber" />
      <Snippet text={message} />
    </ViewShell>
  )
}

const LinearIssueCreatedTimelineEventView: KnownTimelineEventView<typeof LINEAR_ISSUE_CREATED_EVENT> = ({
  event,
  onOpenExternalReference,
}: KnownTimelineEventViewProps<typeof LINEAR_ISSUE_CREATED_EVENT>) => {
  const data = event.event_data
  const issue = objectFact(data.issue)
  const issueContext = objectStringFact(issue, 'identifier', 'id') ?? 'Unknown issue'
  const issueTitle = objectStringFact(issue, 'title', 'name') ?? 'Untitled Linear issue'
  const issueState = objectStringFact(issue, 'state', 'status') ?? 'Unknown state'
  const issueUrl = objectStringFact(issue, 'url')
  const terminalId = firstFact(data.terminal_id) ?? 'Unknown terminal'
  const agent = firstFact(data.agent_id) ?? 'Unknown agent'
  const toolName = firstFact(data.tool_name) ?? 'Unknown tool'

  return (
    <ViewShell
      icon={<PlusCircle size={15} />}
      title={`Issue ${issueContext} created`}
    >
      <DetailPill label="Issue" value={issueContext} tone="blue" />
      <DetailPill label="Title" value={issueTitle} />
      <DetailPill label="State" value={issueState} tone="amber" />
      <DetailPill label="Terminal" value={terminalId} tone="emerald" />
      <DetailPill label="Agent" value={agent} />
      <DetailPill label="Tool" value={toolName} />
      <LinearIssueLink
        issueUrl={issueUrl}
        issueContext={issueContext}
        onOpenExternalReference={onOpenExternalReference}
      />
    </ViewShell>
  )
}

export const timelineEventViewRegistrations: TimelineEventViewRegistration[] = [
  timelineEventViewRegistration(LINEAR_AGENT_MENTIONED_EVENT, LinearMentionTimelineEventView),
  timelineEventViewRegistration(
    LINEAR_ISSUE_DELEGATED_TO_AGENT_EVENT,
    LinearIssueDelegatedTimelineEventView,
  ),
  timelineEventViewRegistration(
    LINEAR_AGENT_SESSION_PROMPTED_EVENT,
    LinearAgentSessionPromptedTimelineEventView,
  ),
  timelineEventViewRegistration(
    LINEAR_AGENT_SESSION_LIFECYCLE_ACTIVITY_EVENT,
    LinearSessionLifecycleActivityTimelineEventView,
  ),
  timelineEventViewRegistration(
    LINEAR_AGENT_SESSION_STOP_REQUESTED_EVENT,
    LinearSessionStopRequestedTimelineEventView,
  ),
  timelineEventViewRegistration(LINEAR_ISSUE_CREATED_EVENT, LinearIssueCreatedTimelineEventView),
]

import { Bell, ExternalLink, GitCompareArrows, LifeBuoy, MessageSquareText, Monitor } from 'lucide-react'
import type { ReactNode } from 'react'
import {
  AGENT_RUNTIME_LIFECYCLE_EVENT,
  AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
  AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT,
  LINEAR_AGENT_MENTIONED_EVENT,
} from '../../generated/caoEventTypeKeys'
import type {
  TimelineEventView,
  TimelineEventViewProps,
  TimelineEventViewRegistration,
} from '../timelineEventViews'

// Payload field names mirror backend dataclass event_data keys at the frontend
// presentation boundary. Event type identity is generated; payload names remain
// the backend-owned JSON contract this view must intentionally read.
const LinearMentionPayloadKey = {
  issueIdentifier: 'issue_identifier',
  issueId: 'issue_id',
  issueTitle: 'issue_title',
  issueUrl: 'issue_url',
  appUserName: 'app_user_name',
  appUserId: 'app_user_id',
  messageBody: 'message_body',
} as const

const RuntimeDeliveryPayloadKey = {
  sourceKind: 'source_kind',
  messageBody: 'message_body',
  terminalId: 'terminal_id',
  outcome: 'outcome',
} as const

const WorkspaceSwitchPayloadKey = {
  fromWorkspaceContextId: 'from_workspace_context_id',
  toWorkspaceContextId: 'to_workspace_context_id',
  outcome: 'outcome',
} as const

const RuntimeLifecyclePayloadKey = {
  action: 'action',
  runtimeStatus: 'runtime_status',
  terminalId: 'terminal_id',
  workspaceContextId: 'workspace_context_id',
  ready: 'ready',
} as const

function stringFact(data: Record<string, unknown>, key: string): string | null {
  const value = data[key]
  return typeof value === 'string' && value.trim() ? value : null
}

function booleanFact(data: Record<string, unknown>, key: string): boolean | null {
  const value = data[key]
  return typeof value === 'boolean' ? value : null
}

function labelize(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function Snippet({ text }: { text: string }) {
  return (
    <div className="mt-2 max-w-3xl rounded border border-gray-700/50 bg-gray-950/50 px-3 py-1.5 text-xs text-gray-300">
      {text}
    </div>
  )
}

function DetailPill({
  label,
  value,
  tone = 'gray',
}: {
  label: string
  value: string
  tone?: 'gray' | 'blue' | 'emerald' | 'amber' | 'purple'
}) {
  const tones = {
    gray: 'border-gray-700/60 bg-gray-950/50 text-gray-300',
    blue: 'border-blue-800/60 bg-blue-950/40 text-blue-200',
    emerald: 'border-emerald-800/60 bg-emerald-950/40 text-emerald-200',
    amber: 'border-amber-800/60 bg-amber-950/40 text-amber-200',
    purple: 'border-purple-800/60 bg-purple-950/40 text-purple-200',
  }
  return (
    <span className={`inline-flex max-w-full items-center gap-1 rounded border px-2 py-0.5 text-[11px] ${tones[tone]}`}>
      <span className="shrink-0 opacity-70">{label}</span>
      <span className="truncate font-mono">{value}</span>
    </span>
  )
}

function EntityReferenceButton({
  label,
  ariaLabel,
  icon,
  onClick,
}: {
  label: string
  ariaLabel: string
  icon: JSX.Element
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={onClick}
      className="inline-flex max-w-full items-center gap-1.5 rounded border border-emerald-800/60 bg-emerald-950/40 px-2 py-0.5 text-[11px] font-medium text-emerald-200 transition-colors hover:border-emerald-600 hover:bg-emerald-900/60"
    >
      {icon}
      <span className="truncate">{label}</span>
    </button>
  )
}

function ViewShell({
  icon,
  title,
  children,
}: {
  icon: JSX.Element
  title: string
  children: ReactNode
}) {
  return (
    <div className="min-w-0">
      <div className="flex min-w-0 items-center gap-2">
        <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded bg-gray-950/80 text-emerald-300">
          {icon}
        </span>
        <span className="truncate text-sm font-semibold text-gray-100">{title}</span>
      </div>
      <div className="mt-1.5 flex min-w-0 flex-wrap gap-1.5">
        {children}
      </div>
    </div>
  )
}

const LinearMentionTimelineEventView: TimelineEventView = ({
  event,
  onOpenExternalReference,
}: TimelineEventViewProps) => {
  const data = event.event_data
  const issueIdentifier =
    stringFact(data, LinearMentionPayloadKey.issueIdentifier) ??
    stringFact(data, LinearMentionPayloadKey.issueId)
  const issueTitle =
    stringFact(data, LinearMentionPayloadKey.issueTitle) ?? 'Untitled Linear issue'
  const issueUrl = stringFact(data, LinearMentionPayloadKey.issueUrl)
  const mentioner =
    stringFact(data, LinearMentionPayloadKey.appUserName) ??
    stringFact(data, LinearMentionPayloadKey.appUserId) ??
    'Unknown teammate'
  const message =
    stringFact(data, LinearMentionPayloadKey.messageBody) ?? 'No mention text recorded'
  const issueContext = issueIdentifier ?? 'Unknown issue'

  return (
    <ViewShell
      icon={<MessageSquareText size={15} />}
      title={`${mentioner} mentioned this agent`}
    >
      <DetailPill label="Linear issue" value={issueContext} tone="blue" />
      <DetailPill label="Title" value={issueTitle} />
      <DetailPill label="Mentioner" value={mentioner} tone="emerald" />
      {issueUrl && onOpenExternalReference && (
        <EntityReferenceButton
          label="Open in Linear"
          ariaLabel={`Open Linear issue ${issueContext}`}
          icon={<ExternalLink size={12} />}
          onClick={() => onOpenExternalReference(issueUrl)}
        />
      )}
      <Snippet text={message} />
    </ViewShell>
  )
}

const RuntimeDeliveryTimelineEventView: TimelineEventView = ({
  event,
  onFocusTerminal,
}: TimelineEventViewProps) => {
  const data = event.event_data
  const sourceKind = stringFact(data, RuntimeDeliveryPayloadKey.sourceKind)
  const message =
    stringFact(data, RuntimeDeliveryPayloadKey.messageBody) ?? 'No message text recorded'
  const terminalTarget = stringFact(data, RuntimeDeliveryPayloadKey.terminalId)
  const terminalId = terminalTarget ?? 'No terminal recorded'
  const outcome = stringFact(data, RuntimeDeliveryPayloadKey.outcome) ?? 'unknown outcome'

  return (
    <ViewShell
      icon={<Bell size={15} />}
      title={`Mention delivered to terminal ${terminalId}`}
    >
      <DetailPill label="Source" value={labelize(sourceKind, 'Unknown source')} tone="blue" />
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

const WorkspaceContextSwitchTimelineEventView: TimelineEventView = ({
  event,
}: TimelineEventViewProps) => {
  const data = event.event_data
  const fromContext =
    stringFact(data, WorkspaceSwitchPayloadKey.fromWorkspaceContextId) ??
    'Unknown from context'
  const toContext =
    stringFact(data, WorkspaceSwitchPayloadKey.toWorkspaceContextId) ?? 'Unknown to context'
  const outcome = stringFact(data, WorkspaceSwitchPayloadKey.outcome) ?? 'context changed'

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

const RuntimeLifecycleTimelineEventView: TimelineEventView = ({
  event,
}: TimelineEventViewProps) => {
  const data = event.event_data
  const action =
    stringFact(data, RuntimeLifecyclePayloadKey.action) ?? 'unknown lifecycle phase'
  const runtimeStatus =
    stringFact(data, RuntimeLifecyclePayloadKey.runtimeStatus) ?? 'unknown status'
  const terminalId =
    stringFact(data, RuntimeLifecyclePayloadKey.terminalId) ?? 'No terminal recorded'
  const workspaceContext =
    stringFact(data, RuntimeLifecyclePayloadKey.workspaceContextId) ??
    'Unknown workspace context'
  const ready = booleanFact(data, RuntimeLifecyclePayloadKey.ready)
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

export const timelineEventViewRegistrations: TimelineEventViewRegistration[] = [
  {
    eventTypeKey: LINEAR_AGENT_MENTIONED_EVENT,
    view: LinearMentionTimelineEventView,
  },
  {
    eventTypeKey: AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
    view: RuntimeDeliveryTimelineEventView,
  },
  {
    eventTypeKey: AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT,
    view: WorkspaceContextSwitchTimelineEventView,
  },
  {
    eventTypeKey: AGENT_RUNTIME_LIFECYCLE_EVENT,
    view: RuntimeLifecycleTimelineEventView,
  },
]

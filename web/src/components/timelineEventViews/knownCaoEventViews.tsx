import { Bell, ExternalLink, GitCompareArrows, LifeBuoy, MessageSquareText, Monitor } from 'lucide-react'
import type { ReactNode } from 'react'
import {
  AGENT_RUNTIME_LIFECYCLE_EVENT,
  AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
  AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT,
  LINEAR_AGENT_MENTIONED_EVENT,
} from '../../generated/caoEventPayloadTypes'
import type {
  KnownTimelineEventView,
  KnownTimelineEventViewProps,
  TimelineEventViewRegistration,
} from '../timelineEventViews'
import { timelineEventViewRegistration } from '../timelineEventViews'

function stringFact(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function booleanFact(value: unknown): boolean | null {
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

const RuntimeDeliveryTimelineEventView: KnownTimelineEventView<
  typeof AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT
> = ({
  event,
  onFocusTerminal,
}: KnownTimelineEventViewProps<typeof AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT>) => {
  const data = event.event_data
  const sourceKind = stringFact(data.source_kind)
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

export const timelineEventViewRegistrations: TimelineEventViewRegistration[] = [
  timelineEventViewRegistration(LINEAR_AGENT_MENTIONED_EVENT, LinearMentionTimelineEventView),
  timelineEventViewRegistration(
    AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
    RuntimeDeliveryTimelineEventView,
  ),
  timelineEventViewRegistration(
    AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT,
    WorkspaceContextSwitchTimelineEventView,
  ),
  timelineEventViewRegistration(AGENT_RUNTIME_LIFECYCLE_EVENT, RuntimeLifecycleTimelineEventView),
]

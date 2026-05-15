import { Clock3, GitBranch, Link2 } from 'lucide-react'
import { AgentIdentityTimelineEvent } from '../api'
import type { CaoEventPayloadForTypeKey, CaoEventTypeKey } from '../generated/caoEventPayloadTypes'

type TimelineEventViewSurface = 'main' | 'related'

export type OpenExternalReference = (url: string) => void
export type FocusTerminalReference = (terminalId: string) => void | Promise<void>

export interface TimelineEventViewProps {
  event: AgentIdentityTimelineEvent
  surface: TimelineEventViewSurface
  onOpenExternalReference?: OpenExternalReference
  onFocusTerminal?: FocusTerminalReference
}

export type TimelineEventView = (props: TimelineEventViewProps) => JSX.Element

export type KnownTimelineEvent<T extends CaoEventTypeKey> = Omit<
  AgentIdentityTimelineEvent,
  'event_type_key' | 'event_data'
> & {
  event_type_key: T
  event_data: Partial<CaoEventPayloadForTypeKey<T>> & Record<string, unknown>
}

export type KnownTimelineEventViewProps<T extends CaoEventTypeKey> = Omit<
  TimelineEventViewProps,
  'event'
> & {
  event: KnownTimelineEvent<T>
}

export type KnownTimelineEventView<T extends CaoEventTypeKey> = (
  props: KnownTimelineEventViewProps<T>
) => JSX.Element

export interface TimelineEventViewRegistration {
  eventTypeKey: string
  view: TimelineEventView
}

export function timelineEventViewRegistration<T extends CaoEventTypeKey>(
  eventTypeKey: T,
  view: KnownTimelineEventView<T>,
): TimelineEventViewRegistration {
  return {
    eventTypeKey,
    view: view as TimelineEventView,
  }
}

interface TimelineEventViewModule {
  timelineEventViewRegistrations?: TimelineEventViewRegistration[]
}

function formatLabel(value: string | null | undefined): string {
  if (!value) return 'None'
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase())
}

function formatTime(value: string | null | undefined): string {
  if (!value) return 'Unknown time'
  return value.replace('T', ' ').replace(/\.\d+Z?$/, '').replace(/Z$/, '')
}

class EventTimelineViewRegistry {
  private readonly views = new Map<string, TimelineEventView>()

  register(eventTypeKey: string, view: TimelineEventView) {
    this.views.set(eventTypeKey, view)
  }

  viewFor(eventTypeKey: string): TimelineEventView {
    return this.views.get(eventTypeKey) ?? FallbackTimelineEventView
  }
}

export const eventTimelineViewRegistry = new EventTimelineViewRegistry()

const timelineEventViewModules = import.meta.glob<TimelineEventViewModule>(
  './timelineEventViews/*.tsx',
  { eager: true },
)

Object.values(timelineEventViewModules).forEach(module => {
  module.timelineEventViewRegistrations?.forEach(registration => {
    eventTimelineViewRegistry.register(registration.eventTypeKey, registration.view)
  })
})

function primitiveFactValue(value: unknown): string | null {
  if (value === null) return 'null'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function displayableEventDataFacts(event: AgentIdentityTimelineEvent) {
  return Object.entries(event.event_data)
    .map(([key, value]) => [key, primitiveFactValue(value)] as const)
    .filter((entry): entry is readonly [string, string] => entry[1] !== null)
    .slice(0, 6)
}

function FallbackTimelineEventView({ event, surface }: TimelineEventViewProps) {
  const displayableFacts = displayableEventDataFacts(event)
  const compact = surface === 'related'

  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`${compact ? 'text-xs' : 'text-sm'} font-semibold text-gray-100`}>
          {formatLabel(event.event_name)}
        </span>
        <span className="rounded bg-blue-900/50 px-2 py-0.5 text-[11px] text-blue-300">
          {formatLabel(event.source_type)}
        </span>
        {event.participant_role && (
          <span className="rounded bg-emerald-900/50 px-2 py-0.5 text-[11px] text-emerald-300">
            {formatLabel(event.participant_role)}
          </span>
        )}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
        <span className="inline-flex items-center gap-1">
          <Clock3 size={12} />
          {formatTime(event.occurred_at)}
        </span>
        <span className="inline-flex min-w-0 items-center gap-1">
          Source {event.source_type}:{event.source_id}
        </span>
        {event.correlation_id && (
          <span className="inline-flex min-w-0 items-center gap-1">
            <GitBranch size={12} />
            <span className="truncate">Correlation {event.correlation_id}</span>
          </span>
        )}
        {event.causation_id && (
          <span className="inline-flex min-w-0 items-center gap-1">
            <Link2 size={12} />
            <span className="truncate">Cause {event.causation_id}</span>
          </span>
        )}
      </div>
      {displayableFacts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {displayableFacts.map(([key, value]) => (
            <span
              key={`${event.event_id}-${key}`}
              className="inline-flex max-w-full items-center gap-1 rounded border border-gray-700/50 bg-gray-950/50 px-2 py-0.5 text-[11px] text-gray-300"
            >
              <span className="shrink-0 text-gray-500">{formatLabel(key)}</span>
              <span className="truncate font-mono">{value}</span>
            </span>
          ))}
        </div>
      )}
      {compact && (
        <div
          data-testid="related-event-id"
          title={event.event_id}
          className="mt-1 truncate font-mono text-[11px] text-gray-500"
        >
          {event.event_id}
        </div>
      )}
    </div>
  )
}

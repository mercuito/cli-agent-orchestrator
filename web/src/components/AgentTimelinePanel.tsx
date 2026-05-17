import { useEffect, useMemo, useState } from 'react'
import { api, AgentRelatedEvents, AgentStatus, AgentTimeline, AgentTimelineEvent } from '../api'
import { AlertCircle, Bot, ChevronDown, ChevronRight, Radio, Search } from 'lucide-react'
import {
  eventTimelineViewRegistry,
  type FocusTerminalReference,
  type OpenExternalReference,
} from './timelineEventViews'

const AGENT_TIMELINE_REFRESH_MS = 5000

function activeLabel(agent: AgentStatus): string {
  return agent.active ? 'Active' : 'Inactive'
}

function relatedEventCacheKey(agentId: string, eventId: string): string {
  return `${agentId}::${eventId}`
}

function eventTimeMillis(event: AgentTimelineEvent): number {
  const parsed = Date.parse(event.occurred_at)
  return Number.isNaN(parsed) ? 0 : parsed
}

function newestEventsFirst(events: AgentTimelineEvent[]): AgentTimelineEvent[] {
  return [...events].sort((left, right) => {
    const byTime = eventTimeMillis(right) - eventTimeMillis(left)
    return byTime || right.event_id.localeCompare(left.event_id)
  })
}

function AgentRosterItem({
  agent,
  selected,
  onSelect,
}: {
  agent: AgentStatus
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full text-left rounded-lg border p-3 transition-colors ${
        selected
          ? 'border-emerald-500/70 bg-emerald-950/30'
          : 'border-gray-700/40 bg-gray-900/50 hover:border-gray-600 hover:bg-gray-800/70'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Bot size={15} className={selected ? 'text-emerald-300' : 'text-gray-500'} />
            <span className="truncate text-sm font-semibold text-gray-100">
              {agent.display_name}
            </span>
          </div>
          <div className="mt-1 truncate font-mono text-xs text-gray-500">
            {agent.agent_id}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="rounded bg-gray-800 px-2 py-0.5 text-[11px] text-gray-300">
              {agent.session_name}
            </span>
            <span className="rounded bg-gray-800 px-2 py-0.5 text-[11px] text-gray-300">
              {agent.cli_provider}
            </span>
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${
          agent.active
            ? 'bg-emerald-900/60 text-emerald-300'
            : 'bg-gray-800 text-gray-400'
        }`}>
          {activeLabel(agent)}
        </span>
      </div>
    </button>
  )
}

function DetailValue({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 truncate rounded bg-gray-900/70 px-2.5 py-1.5 font-mono text-xs text-gray-300">
        {value || 'none'}
      </div>
    </div>
  )
}

function RelatedEventList({
  title,
  events,
  emptyLabel,
  onOpenExternalReference,
  onFocusTerminal,
}: {
  title: string
  events: AgentTimelineEvent[]
  emptyLabel: string
  onOpenExternalReference: OpenExternalReference
  onFocusTerminal?: FocusTerminalReference
}) {
  const sortedEvents = useMemo(() => newestEventsFirst(events), [events])
  const listId = `related-event-list-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`

  return (
    <div data-testid={listId}>
      <h5 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
        {title}
      </h5>
      {sortedEvents.length === 0 ? (
        <div className="rounded border border-gray-700/40 bg-gray-950/40 px-3 py-2 text-xs text-gray-500">
          {emptyLabel}
        </div>
      ) : (
        <div className="space-y-1.5">
          {sortedEvents.map(event => {
            const EventView = eventTimelineViewRegistry.viewFor(event.event_type_key)
            return (
              <div key={`${title}-${event.event_id}`} className="min-w-0 rounded border border-gray-700/40 bg-gray-950/50 px-3 py-2">
                <EventView
                  event={event}
                  surface="related"
                  onOpenExternalReference={onOpenExternalReference}
                  onFocusTerminal={onFocusTerminal}
                />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function TimelineRow({
  event,
  expanded,
  related,
  loading,
  error,
  onToggle,
  onOpenExternalReference,
  onFocusTerminal,
}: {
  event: AgentTimelineEvent
  expanded: boolean
  related: AgentRelatedEvents | null
  loading: boolean
  error: string | null
  onToggle: () => void
  onOpenExternalReference: OpenExternalReference
  onFocusTerminal?: FocusTerminalReference
}) {
  const EventView = eventTimelineViewRegistry.viewFor(event.event_type_key)

  return (
    <article className="rounded-lg border border-gray-700/40 bg-gray-900/55">
      <div className="grid gap-3 p-3 md:grid-cols-[minmax(0,1fr)_160px_160px] md:items-center">
        <EventView
          event={event}
          surface="main"
          onOpenExternalReference={onOpenExternalReference}
          onFocusTerminal={onFocusTerminal}
        />
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-gray-500">Event ID</div>
          <div
            data-testid="timeline-event-id"
            title={event.event_id}
            className="mt-1 truncate font-mono text-xs text-gray-300"
          >
            {event.event_id}
          </div>
        </div>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-label={`Inspect related events for ${event.event_id}`}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-gray-700/60 bg-gray-800/80 px-3 py-2 text-xs font-medium text-gray-300 transition-colors hover:border-emerald-700/60 hover:text-emerald-300"
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          Related
        </button>
      </div>
      {expanded && (
        <div className="border-t border-gray-700/40 p-3">
          {loading ? (
            <div className="text-sm text-gray-500">Loading related events...</div>
          ) : error ? (
            <div className="flex items-center gap-2 text-sm text-red-300">
              <AlertCircle size={14} />
              {error}
            </div>
          ) : related ? (
            <div data-testid="related-events-grid" className="grid gap-3 lg:grid-cols-2">
              <RelatedEventList
                title="Direct Cause"
                events={related.causation_events.direct_cause ? [related.causation_events.direct_cause] : []}
                emptyLabel="No direct cause recorded."
                onOpenExternalReference={onOpenExternalReference}
                onFocusTerminal={onFocusTerminal}
              />
              <RelatedEventList
                title="Direct Effects"
                events={related.causation_events.direct_effects}
                emptyLabel="No direct effects recorded."
                onOpenExternalReference={onOpenExternalReference}
                onFocusTerminal={onFocusTerminal}
              />
              <div className="lg:col-span-2 lg:mx-auto lg:w-full lg:max-w-md">
                <RelatedEventList
                  title="Shared Correlation Thread"
                  events={related.correlation_events}
                  emptyLabel="No shared correlation thread recorded."
                  onOpenExternalReference={onOpenExternalReference}
                  onFocusTerminal={onFocusTerminal}
                />
              </div>
            </div>
          ) : null}
        </div>
      )}
    </article>
  )
}

interface AgentTimelinePanelProps {
  onOpenExternalReference?: OpenExternalReference
  onFocusTerminal?: FocusTerminalReference
}

function openExternalReference(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

export function AgentTimelinePanel({
  onOpenExternalReference = openExternalReference,
  onFocusTerminal,
}: AgentTimelinePanelProps = {}) {
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [rosterLoading, setRosterLoading] = useState(true)
  const [rosterError, setRosterError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [timeline, setTimeline] = useState<AgentTimeline | null>(null)
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [timelineError, setTimelineError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null)
  const [relatedByEvent, setRelatedByEvent] = useState<Record<string, AgentRelatedEvents>>({})
  const [relatedLoadingKey, setRelatedLoadingKey] = useState<string | null>(null)
  const [relatedErrors, setRelatedErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    let cancelled = false
    setRosterLoading(true)
    setRosterError(null)
    api.listAgents()
      .then(result => {
        if (cancelled) return
        setAgents(result)
        setSelectedId(current => current ?? result[0]?.agent_id ?? null)
      })
      .catch(() => {
        if (!cancelled) setRosterError('Unable to load agents.')
      })
      .finally(() => {
        if (!cancelled) setRosterLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!selectedId) {
      setTimeline(null)
      return
    }
    let cancelled = false
    const fetchTimeline = async (initialLoad: boolean) => {
      if (initialLoad) {
        setTimelineLoading(true)
        setTimelineError(null)
      }
      try {
        const result = await api.getAgentTimeline(selectedId)
        if (cancelled) return
        setTimeline(result)
        setTimelineError(null)
      } catch {
        if (!cancelled && initialLoad) setTimelineError('Unable to load agent timeline.')
      } finally {
        if (!cancelled && initialLoad) setTimelineLoading(false)
      }
    }

    setTimeline(null)
    setExpandedEventId(null)
    setRelatedByEvent({})
    setRelatedErrors({})
    setRelatedLoadingKey(null)
    fetchTimeline(true)
    const interval = setInterval(() => {
      fetchTimeline(false)
    }, AGENT_TIMELINE_REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [selectedId])

  const filteredAgents = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return agents
    return agents.filter(agent =>
      agent.display_name.toLowerCase().includes(query) ||
      agent.agent_id.toLowerCase().includes(query) ||
      agent.session_name.toLowerCase().includes(query)
    )
  }, [agents, search])

  const selectedAgent = timeline?.agent ?? agents.find(agent => agent.agent_id === selectedId) ?? null
  const timelineEvents = useMemo(
    () => newestEventsFirst(timeline?.events ?? []),
    [timeline?.events],
  )

  const handleToggleRelated = async (eventId: string) => {
    if (!selectedId) return
    const cacheKey = relatedEventCacheKey(selectedId, eventId)
    const nextExpanded = expandedEventId === eventId ? null : eventId
    setExpandedEventId(nextExpanded)
    if (!nextExpanded || relatedByEvent[cacheKey]) return

    setRelatedLoadingKey(cacheKey)
    setRelatedErrors(prev => ({ ...prev, [cacheKey]: '' }))
    try {
      const related = await api.getAgentRelatedEvents(selectedId, eventId)
      setRelatedByEvent(prev => ({ ...prev, [cacheKey]: related }))
    } catch {
      setRelatedErrors(prev => ({
        ...prev,
        [cacheKey]: 'Unable to load related events.',
      }))
    } finally {
      setRelatedLoadingKey(current => current === cacheKey ? null : current)
    }
  }

  return (
    <section className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
      <div className="rounded-xl border border-gray-700/50 bg-gray-800/60 p-4">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-300">
              Agents ({agents.length})
            </h3>
            <p className="mt-1 text-xs text-gray-500">
              Configured agents independent of current terminals.
            </p>
          </div>
          <Radio size={16} className="mt-1 text-emerald-400" />
        </div>
        <div className="relative mb-3">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Search agents..."
            className="w-full rounded-lg border border-gray-700 bg-gray-900 py-2 pl-8 pr-3 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
          />
        </div>
        {rosterLoading ? (
          <div className="rounded-lg border border-gray-700/40 bg-gray-900/50 p-3 text-sm text-gray-500">
            Loading agents...
          </div>
        ) : rosterError ? (
          <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-3 text-sm text-red-300">
            {rosterError}
          </div>
        ) : filteredAgents.length === 0 ? (
          <div className="rounded-lg border border-gray-700/40 bg-gray-900/50 p-3 text-sm text-gray-500">
            No configured agents match this search.
          </div>
        ) : (
          <div className="space-y-2">
            {filteredAgents.map(agent => (
              <AgentRosterItem
                key={agent.agent_id}
                agent={agent}
                selected={agent.agent_id === selectedId}
                onSelect={() => setSelectedId(agent.agent_id)}
              />
            ))}
          </div>
        )}
      </div>

      <div className="space-y-4 min-w-0">
        <div className="rounded-xl border border-gray-700/50 bg-gray-800/60 p-4">
          {selectedAgent ? (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-lg font-semibold text-white">{selectedAgent.display_name}</h3>
                    <span className={`rounded-full px-2 py-0.5 text-xs ${
                      selectedAgent.active
                        ? 'bg-emerald-900/60 text-emerald-300'
                        : 'bg-gray-700 text-gray-400'
                    }`}>
                      {activeLabel(selectedAgent)}
                    </span>
                  </div>
                  <div className="mt-1 truncate font-mono text-xs text-gray-500">
                    {selectedAgent.agent_id}
                  </div>
                </div>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <DetailValue label="Session" value={selectedAgent.session_name} />
                <DetailValue label="Provider" value={selectedAgent.cli_provider} />
                <DetailValue label="Terminal" value={selectedAgent.active_terminal_id} />
                <DetailValue label="Workspace" value={selectedAgent.active_workspace_context_id} />
              </div>
            </>
          ) : (
            <div className="text-sm text-gray-500">Select an agent to inspect its timeline.</div>
          )}
        </div>

        <div className="rounded-xl border border-gray-700/50 bg-gray-800/60 p-4">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold uppercase tracking-wide text-gray-300">
                Agent Timeline
              </h4>
              <p className="mt-1 text-xs text-gray-500">
                Recent CAO events returned for the selected participant agent.
              </p>
            </div>
            {timeline && (
              <span className="rounded bg-gray-900 px-2.5 py-1 text-xs text-gray-400">
                {timeline.events.length} event{timeline.events.length === 1 ? '' : 's'}
              </span>
            )}
          </div>

          {timelineLoading ? (
            <div className="rounded-lg border border-gray-700/40 bg-gray-900/50 p-4 text-sm text-gray-500">
              Loading agent timeline...
            </div>
          ) : timelineError ? (
            <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4 text-sm text-red-300">
              {timelineError}
            </div>
          ) : timeline && timeline.events.length === 0 ? (
            <div className="rounded-lg border border-gray-700/40 bg-gray-900/50 p-4 text-sm text-gray-500">
              No recent activity to display for this agent.
            </div>
          ) : timeline ? (
            <div data-testid="agent-timeline" className="space-y-2">
              {timelineEvents.map(event => {
                const cacheKey = selectedId ? relatedEventCacheKey(selectedId, event.event_id) : event.event_id
                return (
                  <TimelineRow
                    key={event.event_id}
                    event={event}
                    expanded={expandedEventId === event.event_id}
                    related={relatedByEvent[cacheKey] ?? null}
                    loading={relatedLoadingKey === cacheKey}
                    error={relatedErrors[cacheKey] || null}
                    onToggle={() => handleToggleRelated(event.event_id)}
                    onOpenExternalReference={onOpenExternalReference}
                    onFocusTerminal={onFocusTerminal}
                  />
                )
              })}
            </div>
          ) : (
            <div className="rounded-lg border border-gray-700/40 bg-gray-900/50 p-4 text-sm text-gray-500">
              Select an agent to load its timeline.
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AgentIdentityTimelinePanel } from '../components/AgentIdentityTimelinePanel'
import { api, AgentIdentityRelatedEvents, AgentIdentityStatus, AgentIdentityTimeline } from '../api'
import {
  AGENT_RUNTIME_LIFECYCLE_EVENT,
  AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
  AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT,
  LINEAR_AGENT_MENTIONED_EVENT,
} from '../generated/caoEventPayloadTypes'

function identity(
  agent_identity_id: string,
  display_name: string,
  overrides: Partial<AgentIdentityStatus> = {},
): AgentIdentityStatus {
  return {
    agent_identity_id,
    display_name,
    agent_profile: `${agent_identity_id}-profile`,
    cli_provider: 'codex',
    active: false,
    active_terminal_id: null,
    active_workspace_context_id: null,
    last_active_at: null,
    ...overrides,
  }
}

function event(
  event_id: string,
  event_name: string,
  occurred_at: string,
  participant_role: string | null,
  overrides: Partial<AgentIdentityTimeline['events'][number]> = {},
): AgentIdentityTimeline['events'][number] {
  return {
    event_id,
    event_name,
    event_type_key: event_name,
    source_type: 'linear',
    source_id: event_id,
    occurred_at,
    correlation_id: null,
    causation_id: null,
    event_data: {},
    participant_role,
    ...overrides,
  }
}

const aria = identity('aria', 'Aria', {
  active: true,
  active_terminal_id: 'term-aria',
  active_workspace_context_id: 'wctx-aria',
  last_active_at: '2026-05-13T12:03:00',
})
const cael = identity('cael', 'Cael')
const unused = identity('unused', 'Unused Agent')

const mention = event(
  'linear:agent_mentioned:mention',
  'agent_mentioned',
  '2026-05-13T12:00:00',
  'mentioned',
  { correlation_id: 'thread-1' },
)
const delivery = event(
  'runtime:notification_delivery:delivery',
  'agent_runtime_notification_delivery',
  '2026-05-13T12:01:00',
  'delivery_target',
  {
    correlation_id: 'thread-1',
    causation_id: 'linear:agent_mentioned:mention',
    source_type: 'runtime',
  },
)
const broadcastForAria = event(
  'linear:agent_mentioned:broadcast',
  'agent_mentioned',
  '2026-05-13T12:02:00',
  'mentioned',
  { correlation_id: 'broadcast-thread' },
)
const broadcastForCael = {
  ...broadcastForAria,
  participant_role: 'observer',
}
const liveMention = event(
  'linear:agent_mentioned:live',
  'agent_mentioned',
  '2026-05-13T12:04:00',
  'mentioned',
  { correlation_id: 'thread-live' },
)
const workspaceRefreshId = 'workspace:context_refresh:non-participant'
const unknownAudit = event(
  'experimental:audit:event-1',
  'experimental_audit_event',
  '2026-05-13T12:05:00',
  'participant',
  {
    event_type_key: 'cao.experimental.AuditEvent',
    source_type: 'audit',
    source_id: 'audit-1',
    correlation_id: 'thread-audit',
    event_data: {
      audit_kind: 'workspace_scan',
      confidence: 0.92,
      nested_fact: { hidden: true },
      tags: ['alpha', 'beta'],
    },
  },
)
const relatedUnknownAudit = event(
  'experimental:audit:event-2',
  'experimental_audit_event',
  '2026-05-13T12:06:00',
  'effect_target',
  {
    event_type_key: 'cao.experimental.RelatedAuditEvent',
    source_type: 'audit',
    source_id: 'audit-2',
    correlation_id: 'thread-audit',
    causation_id: unknownAudit.event_id,
    event_data: {
      audit_kind: 'related_probe',
      confidence: 0.73,
    },
  },
)

const knownLinearMention = event(
  'linear:event:mention-ops-417',
  'agent_mentioned',
  '2026-05-13T12:00:00',
  'mentioned',
  {
    event_type_key: LINEAR_AGENT_MENTIONED_EVENT,
    source_type: 'linear',
    source_id: 'msg-ops-417',
    event_data: {
      issue_identifier: 'OPS-417',
      issue_title: 'Restore dashboard event detail',
      issue_url: 'https://linear.app/yards/issue/OPS-417/restore-dashboard-event-detail',
      app_user_name: 'Nia',
      message_body: 'Aria, can you trace the stuck inbox delivery?',
    },
  },
)

const knownLinearMentionWithoutIssueUrl = event(
  'linear:event:mention-no-url',
  'agent_mentioned',
  '2026-05-13T12:00:00',
  'mentioned',
  {
    event_type_key: LINEAR_AGENT_MENTIONED_EVENT,
    source_type: 'linear',
    source_id: 'msg-no-url',
    event_data: {
      issue_identifier: 'OPS-418',
      issue_title: 'Trace terminal focus',
      app_user_name: 'Nia',
      message_body: 'Aria, can you verify the terminal link?',
    },
  },
)

const knownRuntimeDelivery = event(
  'runtime:event:delivery-ops-417',
  'agent_runtime_notification_delivery',
  '2026-05-13T12:01:00',
  'delivery_target',
  {
    event_type_key: AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
    source_type: 'cao_runtime',
    source_id: 'notification:42',
    causation_id: knownLinearMention.event_id,
    event_data: {
      source_kind: 'linear_mention',
      message_body: 'Aria, can you trace the stuck inbox delivery?',
      terminal_id: 'term-aria-main',
      outcome: 'delivered',
      runtime_status: 'idle',
    },
  },
)

const knownWorkspaceSwitch = event(
  'runtime:event:workspace-switch',
  'agent_runtime_workspace_context_switch',
  '2026-05-13T12:02:00',
  'context_switch_agent',
  {
    event_type_key: AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT,
    source_type: 'cao_runtime',
    source_id: 'term-aria-main',
    event_data: {
      from_workspace_context_id: 'cli-agent-orchestrator',
      to_workspace_context_id: 'yards',
      terminal_id: 'term-aria-main',
      outcome: 'switched',
      runtime_status: 'idle',
    },
  },
)

const knownRuntimeLifecycle = event(
  'runtime:event:lifecycle-restarted',
  'agent_runtime_lifecycle',
  '2026-05-13T12:03:00',
  'lifecycle_agent',
  {
    event_type_key: AGENT_RUNTIME_LIFECYCLE_EVENT,
    source_type: 'cao_runtime',
    source_id: 'term-aria-main',
    event_data: {
      action: 'restarted',
      runtime_status: 'idle',
      terminal_id: 'term-aria-main',
      workspace_context_id: 'yards',
      ready: true,
      fresh: true,
    },
  },
)

const deliveryWithMissingOptionalFacts = event(
  'runtime:event:delivery-missing-optional',
  'agent_runtime_notification_delivery',
  '2026-05-13T12:04:00',
  'delivery_target',
  {
    event_type_key: AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
    source_type: 'cao_runtime',
    source_id: 'notification:43',
    event_data: {
      outcome: 'deferred',
      runtime_status: 'busy',
    },
  },
)

const timelines: Record<string, AgentIdentityTimeline> = {
  aria: {
    identity: aria,
    events: [mention, delivery, broadcastForAria],
  },
  cael: {
    identity: cael,
    events: [broadcastForCael],
  },
  unused: {
    identity: unused,
    events: [],
  },
}

const relatedForDelivery: AgentIdentityRelatedEvents = {
  event: delivery,
  correlation_events: [mention, delivery],
  causation_events: {
    direct_cause: mention,
    direct_effects: [],
  },
}

describe('AgentIdentityTimelinePanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api, 'listAgentIdentities').mockResolvedValue([aria, cael, unused])
    vi.spyOn(api, 'getAgentIdentityTimeline').mockImplementation(async (agentId) => {
      const timeline = timelines[agentId]
      if (!timeline) throw new Error(`unknown identity ${agentId}`)
      return timeline
    })
    vi.spyOn(api, 'getAgentIdentityRelatedEvents').mockResolvedValue(relatedForDelivery)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('lists configured identities and opens the selected identity timeline', async () => {
    render(<AgentIdentityTimelinePanel />)

    expect(await screen.findByRole('button', { name: /aria/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cael/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /unused agent/i })).toBeInTheDocument()
    expect(screen.getByText('term-aria')).toBeInTheDocument()

    const timeline = await screen.findByTestId('identity-timeline')
    expect(within(timeline).getAllByText('Agent Mentioned')).toHaveLength(2)
    expect(within(timeline).getByText('Agent Runtime Notification Delivery')).toBeInTheDocument()
    expect(within(timeline).getByText('2026-05-13 12:01:00')).toBeInTheDocument()
    expect(within(timeline).getByText('Delivery Target')).toBeInTheDocument()
    expect(screen.getAllByTestId('timeline-event-id').map((node) => node.textContent)).toEqual([
      'linear:agent_mentioned:broadcast',
      'runtime:notification_delivery:delivery',
      'linear:agent_mentioned:mention',
    ])
    expect(screen.queryByText(workspaceRefreshId)).not.toBeInTheDocument()
  })

  it('refreshes the watched identity timeline without surfacing non-participant workspace events', async () => {
    vi.useFakeTimers()
    let ariaTimelineFetches = 0
    vi.mocked(api.getAgentIdentityTimeline).mockImplementation(async (agentId) => {
      const timeline = timelines[agentId]
      if (!timeline) throw new Error(`unknown identity ${agentId}`)
      if (agentId !== 'aria') return timeline

      ariaTimelineFetches += 1
      if (ariaTimelineFetches === 1) return timeline

      return {
        identity: aria,
        events: [liveMention, ...timeline.events],
      }
    })

    render(<AgentIdentityTimelinePanel />)

    await act(async () => {})
    await act(async () => {})
    const timeline = screen.getByTestId('identity-timeline')
    expect(within(timeline).queryByText('linear:agent_mentioned:live')).not.toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })

    expect(within(timeline).getByText('linear:agent_mentioned:live')).toBeInTheDocument()
    expect(screen.getAllByTestId('timeline-event-id').map((node) => node.textContent)).toEqual([
      'linear:agent_mentioned:live',
      'linear:agent_mentioned:broadcast',
      'runtime:notification_delivery:delivery',
      'linear:agent_mentioned:mention',
    ])
    expect(screen.queryByText(workspaceRefreshId)).not.toBeInTheDocument()
  })

  it('replaces details and timeline when another identity is selected', async () => {
    render(<AgentIdentityTimelinePanel />)

    await screen.findByText('term-aria')
    fireEvent.click(screen.getByRole('button', { name: /cael/i }))

    await waitFor(() => {
      expect(api.getAgentIdentityTimeline).toHaveBeenLastCalledWith('cael')
    })
    expect(screen.getByRole('heading', { name: 'Cael' })).toBeInTheDocument()
    expect(screen.queryByText('term-aria')).not.toBeInTheDocument()
    expect(screen.getByTestId('timeline-event-id')).toHaveTextContent('linear:agent_mentioned:broadcast')
    expect(screen.getByText('Observer')).toBeInTheDocument()
    expect(screen.queryByText('Delivery Target')).not.toBeInTheDocument()
  })

  it('expands causation and correlation related event groups from the related endpoint', async () => {
    render(<AgentIdentityTimelinePanel />)

    await screen.findByText('Agent Runtime Notification Delivery')
    fireEvent.click(screen.getByRole('button', { name: /inspect related events for runtime:notification_delivery:delivery/i }))

    expect(api.getAgentIdentityRelatedEvents).toHaveBeenCalledWith(
      'aria',
      'runtime:notification_delivery:delivery',
    )
    expect(await screen.findByText('Direct Cause')).toBeInTheDocument()
    expect(screen.getByText('Shared Correlation Thread')).toBeInTheDocument()
    expect(screen.getAllByText('linear:agent_mentioned:mention').length).toBeGreaterThan(1)
    expect(screen.getAllByText('runtime:notification_delivery:delivery').length).toBeGreaterThan(1)
    const relatedGrid = screen.getByTestId('related-events-grid')
    expect(relatedGrid).toHaveClass('lg:grid-cols-2')
    const sharedThread = screen.getByTestId('related-event-list-shared-correlation-thread')
    expect(sharedThread.parentElement).toHaveClass('lg:col-span-2', 'lg:mx-auto')
    expect(within(sharedThread).getAllByTestId('related-event-id').map((node) => node.textContent)).toEqual([
      'runtime:notification_delivery:delivery',
      'linear:agent_mentioned:mention',
    ])
    expect(within(sharedThread).getAllByTestId('related-event-id')[0]).toHaveAttribute(
      'title',
      'runtime:notification_delivery:delivery',
    )
  })

  it('renders untaught event kinds through fallback views on the timeline and related panel', async () => {
    vi.mocked(api.getAgentIdentityTimeline).mockResolvedValue({
      identity: aria,
      events: [unknownAudit],
    })
    vi.mocked(api.getAgentIdentityRelatedEvents).mockResolvedValue({
      event: unknownAudit,
      correlation_events: [unknownAudit, relatedUnknownAudit],
      causation_events: {
        direct_cause: null,
        direct_effects: [relatedUnknownAudit],
      },
    })

    render(<AgentIdentityTimelinePanel />)

    expect(await screen.findByText('Experimental Audit Event')).toBeInTheDocument()
    expect(screen.getByText('Participant')).toBeInTheDocument()
    expect(screen.getByText('Correlation thread-audit')).toBeInTheDocument()
    expect(screen.getByText('Source audit:audit-1')).toBeInTheDocument()
    expect(screen.getByText('Audit Kind')).toBeInTheDocument()
    expect(screen.getByText('workspace_scan')).toBeInTheDocument()
    expect(screen.getByText('Confidence')).toBeInTheDocument()
    expect(screen.getByText('0.92')).toBeInTheDocument()
    expect(screen.queryByText('Nested Fact')).not.toBeInTheDocument()
    expect(screen.queryByText('Tags')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /inspect related events for experimental:audit:event-1/i }))

    expect(await screen.findByText('Direct Effects')).toBeInTheDocument()
    expect(screen.getAllByText('Effect Target').length).toBeGreaterThan(0)
    expect(screen.getAllByText('related_probe').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Cause experimental:audit:event-1').length).toBeGreaterThan(0)
  })

  it('renders taught Linear and runtime event kinds through registered typed views', async () => {
    vi.mocked(api.getAgentIdentityTimeline).mockResolvedValue({
      identity: aria,
      events: [
        knownLinearMention,
        knownRuntimeDelivery,
        knownWorkspaceSwitch,
        knownRuntimeLifecycle,
        deliveryWithMissingOptionalFacts,
        unknownAudit,
      ],
    })

    render(<AgentIdentityTimelinePanel />)

    const timeline = await screen.findByTestId('identity-timeline')
    expect(within(timeline).getByText('OPS-417')).toBeInTheDocument()
    expect(within(timeline).getByText('Restore dashboard event detail')).toBeInTheDocument()
    expect(within(timeline).getByText('Nia')).toBeInTheDocument()
    expect(within(timeline).getAllByText('Aria, can you trace the stuck inbox delivery?').length).toBeGreaterThan(1)
    expect(within(timeline).getByText('Linear issue')).toBeInTheDocument()

    expect(within(timeline).getByText('Linear Mention')).toBeInTheDocument()
    expect(within(timeline).getAllByText('term-aria-main').length).toBeGreaterThan(1)

    expect(within(timeline).getByText('cli-agent-orchestrator')).toBeInTheDocument()
    expect(within(timeline).getAllByText('yards').length).toBeGreaterThan(1)
    expect(within(timeline).getByText('switched')).toBeInTheDocument()

    expect(within(timeline).getByText('restarted')).toBeInTheDocument()
    expect(within(timeline).getByText('idle')).toBeInTheDocument()

    expect(within(timeline).getByText('Unknown source')).toBeInTheDocument()
    expect(within(timeline).getByText('No message text recorded')).toBeInTheDocument()
    expect(within(timeline).getByText('No terminal recorded')).toBeInTheDocument()
    expect(within(timeline).getByText('Experimental Audit Event')).toBeInTheDocument()
  })

  it('renders related events through the same taught views and fallback view as main rows', async () => {
    vi.mocked(api.getAgentIdentityTimeline).mockResolvedValue({
      identity: aria,
      events: [knownLinearMention],
    })
    vi.mocked(api.getAgentIdentityRelatedEvents).mockResolvedValue({
      event: knownLinearMention,
      correlation_events: [knownRuntimeDelivery, unknownAudit],
      causation_events: {
        direct_cause: null,
        direct_effects: [knownRuntimeDelivery, unknownAudit],
      },
    })

    render(<AgentIdentityTimelinePanel />)

    await screen.findByText('Nia mentioned this agent')
    fireEvent.click(screen.getByRole('button', { name: /inspect related events for linear:event:mention-ops-417/i }))

    const relatedGrid = await screen.findByTestId('related-events-grid')
    expect(within(relatedGrid).getAllByText('Mention delivered to terminal term-aria-main').length).toBeGreaterThan(0)
    expect(within(relatedGrid).getAllByText('Linear Mention').length).toBeGreaterThan(0)
    expect(within(relatedGrid).getAllByText('Aria, can you trace the stuck inbox delivery?').length).toBeGreaterThan(0)
    expect(within(relatedGrid).getAllByText('Experimental Audit Event').length).toBeGreaterThan(0)
  })

  it('opens the Linear issue external entity reference from authored event data', async () => {
    const openExternalReference = vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.mocked(api.getAgentIdentityTimeline).mockResolvedValue({
      identity: aria,
      events: [knownLinearMention],
    })

    render(<AgentIdentityTimelinePanel />)

    fireEvent.click(await screen.findByRole('button', { name: /open linear issue ops-417/i }))

    expect(openExternalReference).toHaveBeenCalledWith(
      'https://linear.app/yards/issue/OPS-417/restore-dashboard-event-detail',
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('keeps Linear issue context readable without a broken external reference when issue_url is absent', async () => {
    vi.mocked(api.getAgentIdentityTimeline).mockResolvedValue({
      identity: aria,
      events: [knownLinearMentionWithoutIssueUrl],
    })

    render(<AgentIdentityTimelinePanel />)

    const timeline = await screen.findByTestId('identity-timeline')
    expect(within(timeline).getByText('OPS-418')).toBeInTheDocument()
    expect(within(timeline).getByText('Trace terminal focus')).toBeInTheDocument()
    expect(within(timeline).queryByRole('button', { name: /open linear issue ops-418/i })).not.toBeInTheDocument()
  })

  it('focuses the runtime delivery terminal through the internal entity reference callback', async () => {
    const focusTerminal = vi.fn()
    vi.mocked(api.getAgentIdentityTimeline).mockResolvedValue({
      identity: aria,
      events: [knownRuntimeDelivery],
    })

    render(<AgentIdentityTimelinePanel onFocusTerminal={focusTerminal} />)

    fireEvent.click(await screen.findByRole('button', { name: /open terminal term-aria-main/i }))

    expect(focusTerminal).toHaveBeenCalledWith('term-aria-main')
  })

  it('does not reuse related-event results fetched under a different selected identity', async () => {
    let resolveAriaRelated: (related: AgentIdentityRelatedEvents) => void = () => {}
    vi.mocked(api.getAgentIdentityRelatedEvents).mockImplementation((agentId, eventId) => {
      if (agentId === 'aria' && eventId === 'linear:agent_mentioned:broadcast') {
        return new Promise(resolve => {
          resolveAriaRelated = resolve
        })
      }
      return Promise.resolve({
        event: broadcastForCael,
        correlation_events: [broadcastForCael],
        causation_events: {
          direct_cause: null,
          direct_effects: [],
        },
      })
    })

    render(<AgentIdentityTimelinePanel />)

    await screen.findByTestId('identity-timeline')
    fireEvent.click(screen.getByRole('button', { name: /inspect related events for linear:agent_mentioned:broadcast/i }))
    expect(api.getAgentIdentityRelatedEvents).toHaveBeenCalledWith(
      'aria',
      'linear:agent_mentioned:broadcast',
    )

    fireEvent.click(screen.getByRole('button', { name: /cael/i }))
    await waitFor(() => {
      expect(api.getAgentIdentityTimeline).toHaveBeenLastCalledWith('cael')
    })

    await act(async () => {
      resolveAriaRelated({
        event: broadcastForAria,
        correlation_events: [broadcastForAria],
        causation_events: {
          direct_cause: null,
          direct_effects: [],
        },
      })
    })

    fireEvent.click(screen.getByRole('button', { name: /inspect related events for linear:agent_mentioned:broadcast/i }))

    await waitFor(() => {
      expect(api.getAgentIdentityRelatedEvents).toHaveBeenCalledWith(
        'cael',
        'linear:agent_mentioned:broadcast',
      )
    })
  })

  it('shows no recent activity separately from loading and unreachable states', async () => {
    render(<AgentIdentityTimelinePanel />)

    await screen.findByRole('button', { name: /unused agent/i })
    fireEvent.click(screen.getByRole('button', { name: /unused agent/i }))

    expect(await screen.findByText(/no recent activity to display/i)).toBeInTheDocument()
    expect(screen.queryByText(/loading identity timeline/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/unable to load identity timeline/i)).not.toBeInTheDocument()
  })

  it('shows unreachable timeline state when the selected timeline cannot load', async () => {
    let rejectTimeline: (error: Error) => void = () => {}
    vi.mocked(api.getAgentIdentityTimeline).mockReturnValueOnce(
      new Promise((_, reject) => {
        rejectTimeline = reject
      }),
    )

    render(<AgentIdentityTimelinePanel />)

    expect(await screen.findByText(/loading identity timeline/i)).toBeInTheDocument()
    await act(async () => {
      rejectTimeline(new Error('network down'))
    })
    expect(await screen.findByText(/unable to load identity timeline/i)).toBeInTheDocument()
    expect(screen.queryByText(/no recent activity to display/i)).not.toBeInTheDocument()
  })
})

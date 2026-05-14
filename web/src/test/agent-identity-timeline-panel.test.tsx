import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AgentIdentityTimelinePanel } from '../components/AgentIdentityTimelinePanel'
import { api, AgentIdentityRelatedEvents, AgentIdentityStatus, AgentIdentityTimeline } from '../api'

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
const workspaceRefreshId = 'workspace:context_refresh:non-participant'

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
      'linear:agent_mentioned:mention',
      'runtime:notification_delivery:delivery',
      'linear:agent_mentioned:broadcast',
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

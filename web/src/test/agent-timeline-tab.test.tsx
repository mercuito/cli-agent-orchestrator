import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AgentTimelineTab } from '../components/agents-tab/AgentTimelineTab'
import { AgentDetailPanel } from '../components/agents-tab/AgentDetailPanel'
import { api, AgentRelatedEvents, AgentStatus, AgentTimeline } from '../api'
import {
  AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
  LINEAR_AGENT_MENTIONED_EVENT,
} from '../generated/caoEventPayloadTypes'

function agent(
  agent_id: string,
  display_name: string,
  overrides: Partial<AgentStatus> = {},
): AgentStatus {
  const session_name = `${agent_id}-session`
  return {
    agent_id,
    display_name,
    cli_provider: 'codex',
    workdir: '/repo',
    session_name,
    config: {
      id: agent_id,
      display_name,
      cli_provider: 'codex',
      workdir: '/repo',
      session_name,
      prompt: '# Agent\n',
      description: null,
      model: null,
      reasoning_effort: null,
      mcp_servers: {},
      tools: [],
      tool_aliases: {},
      tools_settings: {},
      cao_tools: null,
      skills: [],
      tags: [],
      resources: [],
      hooks: {},
      use_legacy_mcp_json: null,
      runtime_capabilities: null,
      codex_config: {},
      workspace: { team: null, derived_setup: null, diagnostics: [] },
      linear: null,
    },
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
  overrides: Partial<AgentTimeline['events'][number]> = {},
): AgentTimeline['events'][number] {
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

const aria = agent('aria', 'Aria', {
  active: true,
  active_terminal_id: 'term-aria',
})
const cael = agent('cael', 'Cael')

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
const liveMention = event(
  'linear:agent_mentioned:live',
  'agent_mentioned',
  '2026-05-13T12:04:00',
  'mentioned',
  { correlation_id: 'thread-live' },
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

const timelines: Record<string, AgentTimeline> = {
  aria: { agent: aria, events: [mention, delivery] },
  cael: { agent: cael, events: [] },
}

const relatedForDelivery: AgentRelatedEvents = {
  event: delivery,
  correlation_events: [mention, delivery],
  causation_events: {
    direct_cause: mention,
    direct_effects: [],
  },
}

describe('AgentTimelineTab', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api, 'getAgentTimeline').mockImplementation(async (agentId) => {
      const timeline = timelines[agentId]
      if (!timeline) throw new Error(`unknown agent ${agentId}`)
      return timeline
    })
    vi.spyOn(api, 'getAgentRelatedEvents').mockResolvedValue(relatedForDelivery)
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('fetches the timeline for the provided agent id and renders events newest-first', async () => {
    // Given / When
    render(<AgentTimelineTab agentId="aria" />)

    // Then
    expect(await screen.findByTestId('agent-timeline')).toBeInTheDocument()
    expect(api.getAgentTimeline).toHaveBeenCalledWith('aria')
    expect(screen.getAllByTestId('timeline-event-id').map(node => node.textContent)).toEqual([
      'runtime:notification_delivery:delivery',
      'linear:agent_mentioned:mention',
    ])
  })

  it('refetches the timeline when the agentId prop changes', async () => {
    // Given
    const { rerender } = render(<AgentTimelineTab agentId="aria" />)
    await screen.findByTestId('agent-timeline')

    // When
    rerender(<AgentTimelineTab agentId="cael" />)

    // Then
    await waitFor(() => {
      expect(api.getAgentTimeline).toHaveBeenLastCalledWith('cael')
    })
    expect(await screen.findByText(/no recent activity/i)).toBeInTheDocument()
  })

  it('auto-refreshes the timeline at the existing interval', async () => {
    // Given
    vi.useFakeTimers()
    let ariaFetches = 0
    vi.mocked(api.getAgentTimeline).mockImplementation(async (agentId) => {
      const timeline = timelines[agentId]
      if (!timeline) throw new Error(`unknown agent ${agentId}`)
      if (agentId !== 'aria') return timeline
      ariaFetches += 1
      if (ariaFetches === 1) return timeline
      return { agent: aria, events: [liveMention, ...timeline.events] }
    })
    render(<AgentTimelineTab agentId="aria" />)
    await act(async () => {})
    await act(async () => {})

    // When
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })

    // Then
    expect(screen.getAllByTestId('timeline-event-id').map(node => node.textContent)).toEqual([
      'linear:agent_mentioned:live',
      'runtime:notification_delivery:delivery',
      'linear:agent_mentioned:mention',
    ])
  })

  it('expands related events with Direct Cause, Direct Effects, and Shared Correlation Thread', async () => {
    // Given
    render(<AgentTimelineTab agentId="aria" />)
    await screen.findByText('Agent Runtime Notification Delivery')

    // When
    fireEvent.click(screen.getByRole('button', { name: /inspect related events for runtime:notification_delivery:delivery/i }))

    // Then
    expect(api.getAgentRelatedEvents).toHaveBeenCalledWith('aria', 'runtime:notification_delivery:delivery')
    expect(await screen.findByText('Direct Cause')).toBeInTheDocument()
    expect(screen.getByText('Direct Effects')).toBeInTheDocument()
    expect(screen.getByText('Shared Correlation Thread')).toBeInTheDocument()
    const relatedGrid = screen.getByTestId('related-events-grid')
    expect(relatedGrid).toHaveClass('lg:grid-cols-2')
  })

  it('opens external Linear issue references via the registered timeline event view', async () => {
    // Given
    vi.mocked(api.getAgentTimeline).mockResolvedValue({
      agent: aria,
      events: [knownLinearMention],
    })
    const openExternalReference = vi.fn()
    render(<AgentTimelineTab agentId="aria" onOpenExternalReference={openExternalReference} />)

    // When
    fireEvent.click(await screen.findByRole('button', { name: /open linear issue ops-417/i }))

    // Then
    expect(openExternalReference).toHaveBeenCalledWith(
      'https://linear.app/yards/issue/OPS-417/restore-dashboard-event-detail',
    )
  })

  it('focuses a runtime terminal reference via the onFocusTerminal seam', async () => {
    // Given
    vi.mocked(api.getAgentTimeline).mockResolvedValue({
      agent: aria,
      events: [knownRuntimeDelivery],
    })
    const focusTerminal = vi.fn()
    render(<AgentTimelineTab agentId="aria" onFocusTerminal={focusTerminal} />)

    // When
    fireEvent.click(await screen.findByRole('button', { name: /open terminal term-aria-main/i }))

    // Then
    expect(focusTerminal).toHaveBeenCalledWith('term-aria-main')
  })

  it('shows no-recent-activity state separately from loading and unreachable states', async () => {
    // Given / When
    render(<AgentTimelineTab agentId="cael" />)

    // Then
    expect(await screen.findByText(/no recent activity to display/i)).toBeInTheDocument()
    expect(screen.queryByText(/loading agent timeline/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/unable to load agent timeline/i)).not.toBeInTheDocument()
  })

  it('shows the unreachable state when the timeline fails to load', async () => {
    // Given
    let rejectTimeline: (error: Error) => void = () => {}
    vi.mocked(api.getAgentTimeline).mockReturnValueOnce(
      new Promise((_, reject) => {
        rejectTimeline = reject
      }),
    )

    // When
    render(<AgentTimelineTab agentId="aria" />)
    expect(await screen.findByText(/loading agent timeline/i)).toBeInTheDocument()
    await act(async () => {
      rejectTimeline(new Error('network down'))
    })

    // Then
    expect(await screen.findByText(/unable to load agent timeline/i)).toBeInTheDocument()
  })

  it('is wired into the AgentDetailPanel Timeline slot via the render prop seam', async () => {
    // Given
    const agentForPanel = agent('aria', 'Aria', { active: true, active_terminal_id: 'term-aria' })

    // When
    render(
      <AgentDetailPanel
        agent={agentForPanel}
        onStartAgent={vi.fn()}
        onOpenTerminal={vi.fn()}
        onStopAgent={vi.fn()}
        renderConfigTab={() => <div data-testid="config-tab" />}
        renderTimelineTab={a => <AgentTimelineTab agentId={a.agent_id} />}
      />,
    )
    fireEvent.click(screen.getByRole('tab', { name: 'Timeline' }))

    // Then
    const timeline = await screen.findByTestId('agent-timeline')
    expect(within(timeline).getAllByText('Agent Mentioned').length).toBeGreaterThan(0)
    expect(api.getAgentTimeline).toHaveBeenCalledWith('aria')
  })
})

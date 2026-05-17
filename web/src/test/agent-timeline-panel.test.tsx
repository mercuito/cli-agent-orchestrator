import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AgentTimelinePanel } from '../components/AgentTimelinePanel'
import { eventTimelineViewRegistry } from '../components/timelineEventViews'
import { api, AgentRelatedEvents, AgentStatus, AgentTimeline } from '../api'
import {
  AGENT_RUNTIME_LIFECYCLE_EVENT,
  AGENT_RUNTIME_NOTIFICATION_ACCEPTED_EVENT,
  AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
  AGENT_RUNTIME_WORKSPACE_CONTEXT_SWITCH_EVENT,
  CAO_EVENT_TYPE_KEYS,
  LINEAR_AGENT_SESSION_LIFECYCLE_ACTIVITY_EVENT,
  LINEAR_AGENT_SESSION_PROMPTED_EVENT,
  LINEAR_AGENT_SESSION_STOP_REQUESTED_EVENT,
  LINEAR_AGENT_MENTIONED_EVENT,
  LINEAR_ISSUE_CREATED_EVENT,
  LINEAR_ISSUE_DELEGATED_TO_AGENT_EVENT,
  RUNTIME_WORKSPACE_EVENT,
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
      workspace_context: { enabled: false, resolver_id: null },
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
  active_workspace_context_id: 'wctx-aria',
  last_active_at: '2026-05-13T12:03:00',
})
const cael = agent('cael', 'Cael')
const unused = agent('unused', 'Unused Agent')

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

const knownRuntimeAccepted = event(
  'runtime:event:notification-accepted',
  'agent_runtime_notification_accepted',
  '2026-05-13T12:04:00',
  'notification_target',
  {
    event_type_key: AGENT_RUNTIME_NOTIFICATION_ACCEPTED_EVENT,
    source_type: 'cao_runtime',
    source_id: 'notification:41',
    event_data: {
      inbox_notification_id: 41,
      inbox_receiver_id: 'aria',
      sender_id: 'linear-user-rj',
      source_kind: 'linear_mention',
      source_id: 'msg-accepted-41',
      workspace_context_id: 'yards',
    },
  },
)

const knownRuntimeWorkspace = event(
  'runtime:event:workspace-refresh',
  'runtime_workspace',
  '2026-05-13T12:05:00',
  'workspace_observer',
  {
    event_type_key: RUNTIME_WORKSPACE_EVENT,
    source_type: 'cao_runtime',
    source_id: 'workspace:yards',
    event_data: {
      workspace_context_id: 'yards',
      action: 'refresh',
      runtime_status: 'ready',
      error: 'none',
    },
  },
)

const knownLinearDelegated = event(
  'linear:event:issue-delegated',
  'issue_delegated_to_agent',
  '2026-05-13T12:06:00',
  'delegated',
  {
    event_type_key: LINEAR_ISSUE_DELEGATED_TO_AGENT_EVENT,
    source_type: 'linear',
    source_id: 'msg-delegated',
    event_data: {
      issue_identifier: 'OPS-501',
      issue_title: 'Delegate timeline triage',
      issue_state: 'In Progress',
      issue_url: 'https://linear.app/yards/issue/OPS-501/delegate-timeline-triage',
      agent_id: 'aria',
      app_user_name: 'RJ Wilson',
      message_body: 'Please take ownership of the timeline event presentation.',
    },
  },
)

const knownLinearPrompted = event(
  'linear:event:session-prompted',
  'agent_session_prompted',
  '2026-05-13T12:07:00',
  'prompted',
  {
    event_type_key: LINEAR_AGENT_SESSION_PROMPTED_EVENT,
    source_type: 'linear',
    source_id: 'msg-prompted',
    event_data: {
      issue_identifier: 'OPS-502',
      issue_title: 'Prompt active agent session',
      thread_id: 'thread-502',
      thread_url: 'https://linear.app/yards/thread/thread-502',
      agent_session_id: 'session-502',
      app_user_name: 'Nia',
      prompt_context: 'Follow up with the reviewer after tests pass.',
    },
  },
)

const knownLinearLifecycleActivity = event(
  'linear:event:session-lifecycle',
  'agent_session_lifecycle_activity',
  '2026-05-13T12:08:00',
  'lifecycle_activity',
  {
    event_type_key: LINEAR_AGENT_SESSION_LIFECYCLE_ACTIVITY_EVENT,
    source_type: 'linear',
    source_id: 'msg-lifecycle',
    event_data: {
      issue_identifier: 'OPS-503',
      issue_title: 'Track session lifecycle',
      agent_session_id: 'session-503',
      action: 'resume',
      message_kind: 'status_update',
      should_notify_agent: false,
      suppression_reason: 'agent already processing',
    },
  },
)

const knownLinearStopRequested = event(
  'linear:event:session-stop',
  'agent_session_stop_requested',
  '2026-05-13T12:09:00',
  'stop_requested',
  {
    event_type_key: LINEAR_AGENT_SESSION_STOP_REQUESTED_EVENT,
    source_type: 'linear',
    source_id: 'msg-stop',
    event_data: {
      issue_identifier: 'OPS-504',
      issue_title: 'Stop stale agent session',
      agent_session_id: 'session-504',
      app_user_name: 'RJ Wilson',
      action: 'stop',
      message_body: 'Stop this stale run before dispatching the new plan.',
    },
  },
)

const knownLinearIssueCreated = event(
  'linear:event:issue-created',
  'issue_created',
  '2026-05-13T12:10:00',
  'created_issue',
  {
    event_type_key: LINEAR_ISSUE_CREATED_EVENT,
    source_type: 'linear',
    source_id: 'OPS-505',
    event_data: {
      terminal_id: 'term-create-issue',
      agent_id: 'aria',
      tool_name: 'create_issue',
      issue: {
        identifier: 'OPS-505',
        title: 'Created from CAO timeline',
        state: 'Backlog',
        url: 'https://linear.app/yards/issue/OPS-505/created-from-cao-timeline',
      },
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

const timelines: Record<string, AgentTimeline> = {
  aria: {
    agent: aria,
    events: [mention, delivery, broadcastForAria],
  },
  cael: {
    agent: cael,
    events: [broadcastForCael],
  },
  unused: {
    agent: unused,
    events: [],
  },
}

const relatedForDelivery: AgentRelatedEvents = {
  event: delivery,
  correlation_events: [mention, delivery],
  causation_events: {
    direct_cause: mention,
    direct_effects: [],
  },
}

describe('AgentTimelinePanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api, 'listAgents').mockResolvedValue([aria, cael, unused])
    vi.spyOn(api, 'getAgentTimeline').mockImplementation(async (agentId) => {
      const timeline = timelines[agentId]
      if (!timeline) throw new Error(`unknown agent ${agentId}`)
      return timeline
    })
    vi.spyOn(api, 'getAgentRelatedEvents').mockResolvedValue(relatedForDelivery)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('registers a taught timeline view for every generated CAO event type key', () => {
    // Given
    const fallbackView = eventTimelineViewRegistry.viewFor('unknown.event.Type')

    // When
    const taughtViews = Object.values(CAO_EVENT_TYPE_KEYS).map(eventTypeKey =>
      eventTimelineViewRegistry.viewFor(eventTypeKey)
    )

    // Then
    taughtViews.forEach(view => {
      expect(view).not.toBe(fallbackView)
    })
  })

  it('lists configured agents and opens the selected agent timeline', async () => {
    render(<AgentTimelinePanel />)

    expect(await screen.findByRole('button', { name: /aria/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cael/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /unused agent/i })).toBeInTheDocument()
    expect(screen.getByText('term-aria')).toBeInTheDocument()

    const timeline = await screen.findByTestId('agent-timeline')
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

  it('refreshes the watched agent timeline without surfacing non-participant workspace events', async () => {
    vi.useFakeTimers()
    let ariaTimelineFetches = 0
    vi.mocked(api.getAgentTimeline).mockImplementation(async (agentId) => {
      const timeline = timelines[agentId]
      if (!timeline) throw new Error(`unknown agent ${agentId}`)
      if (agentId !== 'aria') return timeline

      ariaTimelineFetches += 1
      if (ariaTimelineFetches === 1) return timeline

      return {
        agent: aria,
        events: [liveMention, ...timeline.events],
      }
    })

    render(<AgentTimelinePanel />)

    await act(async () => {})
    await act(async () => {})
    const timeline = screen.getByTestId('agent-timeline')
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

  it('replaces details and timeline when another agent is selected', async () => {
    render(<AgentTimelinePanel />)

    await screen.findByText('term-aria')
    fireEvent.click(screen.getByRole('button', { name: /cael/i }))

    await waitFor(() => {
      expect(api.getAgentTimeline).toHaveBeenLastCalledWith('cael')
    })
    expect(screen.getByRole('heading', { name: 'Cael' })).toBeInTheDocument()
    expect(screen.queryByText('term-aria')).not.toBeInTheDocument()
    expect(screen.getByTestId('timeline-event-id')).toHaveTextContent('linear:agent_mentioned:broadcast')
    expect(screen.getByText('Observer')).toBeInTheDocument()
    expect(screen.queryByText('Delivery Target')).not.toBeInTheDocument()
  })

  it('expands causation and correlation related event groups from the related endpoint', async () => {
    render(<AgentTimelinePanel />)

    await screen.findByText('Agent Runtime Notification Delivery')
    fireEvent.click(screen.getByRole('button', { name: /inspect related events for runtime:notification_delivery:delivery/i }))

    expect(api.getAgentRelatedEvents).toHaveBeenCalledWith(
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
    vi.mocked(api.getAgentTimeline).mockResolvedValue({
      agent: aria,
      events: [unknownAudit],
    })
    vi.mocked(api.getAgentRelatedEvents).mockResolvedValue({
      event: unknownAudit,
      correlation_events: [unknownAudit, relatedUnknownAudit],
      causation_events: {
        direct_cause: null,
        direct_effects: [relatedUnknownAudit],
      },
    })

    render(<AgentTimelinePanel />)

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
    // Given
    vi.mocked(api.getAgentTimeline).mockResolvedValue({
      agent: aria,
      events: [
        knownLinearMention,
        knownLinearDelegated,
        knownLinearPrompted,
        knownLinearLifecycleActivity,
        knownLinearStopRequested,
        knownLinearIssueCreated,
        knownRuntimeAccepted,
        knownRuntimeDelivery,
        knownWorkspaceSwitch,
        knownRuntimeLifecycle,
        knownRuntimeWorkspace,
        deliveryWithMissingOptionalFacts,
        unknownAudit,
      ],
    })

    // When
    render(<AgentTimelinePanel />)

    // Then
    const timeline = await screen.findByTestId('agent-timeline')
    expect(within(timeline).getByText('OPS-417')).toBeInTheDocument()
    expect(within(timeline).getByText('Restore dashboard event detail')).toBeInTheDocument()
    expect(within(timeline).getAllByText('Nia').length).toBeGreaterThan(0)
    expect(within(timeline).getAllByText('Aria, can you trace the stuck inbox delivery?').length).toBeGreaterThan(1)
    expect(within(timeline).getByText('Linear issue')).toBeInTheDocument()

    expect(within(timeline).getByText('OPS-501')).toBeInTheDocument()
    expect(within(timeline).getByText('Delegate timeline triage')).toBeInTheDocument()
    expect(within(timeline).getAllByText('aria').length).toBeGreaterThan(0)
    expect(within(timeline).getByText('Please take ownership of the timeline event presentation.')).toBeInTheDocument()

    expect(within(timeline).getByText('thread-502')).toBeInTheDocument()
    expect(within(timeline).getByText('session-502')).toBeInTheDocument()
    expect(within(timeline).getByText('Follow up with the reviewer after tests pass.')).toBeInTheDocument()

    expect(within(timeline).getByText('session-503')).toBeInTheDocument()
    expect(within(timeline).getByText('resume')).toBeInTheDocument()
    expect(within(timeline).getByText('status_update')).toBeInTheDocument()
    expect(within(timeline).getByText('agent already processing')).toBeInTheDocument()

    expect(within(timeline).getByText('session-504')).toBeInTheDocument()
    expect(within(timeline).getByText('Stop this stale run before dispatching the new plan.')).toBeInTheDocument()

    expect(within(timeline).getByText('term-create-issue')).toBeInTheDocument()
    expect(within(timeline).getByText('create_issue')).toBeInTheDocument()
    expect(within(timeline).getByText('Created from CAO timeline')).toBeInTheDocument()

    expect(within(timeline).getByText('linear-user-rj')).toBeInTheDocument()
    expect(within(timeline).getByText('msg-accepted-41')).toBeInTheDocument()
    expect(within(timeline).getByText('Notification 41 accepted')).toBeInTheDocument()

    expect(within(timeline).getByText('Runtime refresh')).toBeInTheDocument()
    expect(within(timeline).getByText('none')).toBeInTheDocument()

    expect(within(timeline).getAllByText('Linear Mention').length).toBeGreaterThan(0)
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
    // Given
    vi.mocked(api.getAgentTimeline).mockResolvedValue({
      agent: aria,
      events: [knownLinearMention],
    })
    vi.mocked(api.getAgentRelatedEvents).mockResolvedValue({
      event: knownLinearMention,
      correlation_events: [knownRuntimeDelivery, knownLinearDelegated, knownRuntimeAccepted, unknownAudit],
      causation_events: {
        direct_cause: null,
        direct_effects: [knownRuntimeDelivery, knownLinearDelegated, knownRuntimeAccepted, unknownAudit],
      },
    })

    // When
    render(<AgentTimelinePanel />)

    await screen.findByText('Nia mentioned this agent')
    fireEvent.click(screen.getByRole('button', { name: /inspect related events for linear:event:mention-ops-417/i }))

    // Then
    const relatedGrid = await screen.findByTestId('related-events-grid')
    expect(within(relatedGrid).getAllByText('Mention delivered to terminal term-aria-main').length).toBeGreaterThan(0)
    expect(within(relatedGrid).getAllByText('Linear Mention').length).toBeGreaterThan(0)
    expect(within(relatedGrid).getAllByText('Aria, can you trace the stuck inbox delivery?').length).toBeGreaterThan(0)
    expect(within(relatedGrid).getAllByText('Delegate timeline triage').length).toBeGreaterThan(0)
    expect(within(relatedGrid).getAllByText('linear-user-rj').length).toBeGreaterThan(0)
    expect(within(relatedGrid).getAllByText('Experimental Audit Event').length).toBeGreaterThan(0)
  })

  it('opens the Linear issue external entity reference from authored event data', async () => {
    const openExternalReference = vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.mocked(api.getAgentTimeline).mockResolvedValue({
      agent: aria,
      events: [knownLinearMention],
    })

    render(<AgentTimelinePanel />)

    fireEvent.click(await screen.findByRole('button', { name: /open linear issue ops-417/i }))

    expect(openExternalReference).toHaveBeenCalledWith(
      'https://linear.app/yards/issue/OPS-417/restore-dashboard-event-detail',
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('keeps Linear issue context readable without a broken external reference when issue_url is absent', async () => {
    vi.mocked(api.getAgentTimeline).mockResolvedValue({
      agent: aria,
      events: [knownLinearMentionWithoutIssueUrl],
    })

    render(<AgentTimelinePanel />)

    const timeline = await screen.findByTestId('agent-timeline')
    expect(within(timeline).getByText('OPS-418')).toBeInTheDocument()
    expect(within(timeline).getByText('Trace terminal focus')).toBeInTheDocument()
    expect(within(timeline).queryByRole('button', { name: /open linear issue ops-418/i })).not.toBeInTheDocument()
  })

  it('focuses the runtime delivery terminal through the internal entity reference callback', async () => {
    const focusTerminal = vi.fn()
    vi.mocked(api.getAgentTimeline).mockResolvedValue({
      agent: aria,
      events: [knownRuntimeDelivery],
    })

    render(<AgentTimelinePanel onFocusTerminal={focusTerminal} />)

    fireEvent.click(await screen.findByRole('button', { name: /open terminal term-aria-main/i }))

    expect(focusTerminal).toHaveBeenCalledWith('term-aria-main')
  })

  it('does not reuse related-event results fetched under a different selected agent', async () => {
    let resolveAriaRelated: (related: AgentRelatedEvents) => void = () => {}
    vi.mocked(api.getAgentRelatedEvents).mockImplementation((agentId, eventId) => {
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

    render(<AgentTimelinePanel />)

    await screen.findByTestId('agent-timeline')
    fireEvent.click(screen.getByRole('button', { name: /inspect related events for linear:agent_mentioned:broadcast/i }))
    expect(api.getAgentRelatedEvents).toHaveBeenCalledWith(
      'aria',
      'linear:agent_mentioned:broadcast',
    )

    fireEvent.click(screen.getByRole('button', { name: /cael/i }))
    await waitFor(() => {
      expect(api.getAgentTimeline).toHaveBeenLastCalledWith('cael')
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
      expect(api.getAgentRelatedEvents).toHaveBeenCalledWith(
        'cael',
        'linear:agent_mentioned:broadcast',
      )
    })
  })

  it('shows no recent activity separately from loading and unreachable states', async () => {
    render(<AgentTimelinePanel />)

    await screen.findByRole('button', { name: /unused agent/i })
    fireEvent.click(screen.getByRole('button', { name: /unused agent/i }))

    expect(await screen.findByText(/no recent activity to display/i)).toBeInTheDocument()
    expect(screen.queryByText(/loading agent timeline/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/unable to load agent timeline/i)).not.toBeInTheDocument()
  })

  it('shows unreachable timeline state when the selected timeline cannot load', async () => {
    let rejectTimeline: (error: Error) => void = () => {}
    vi.mocked(api.getAgentTimeline).mockReturnValueOnce(
      new Promise((_, reject) => {
        rejectTimeline = reject
      }),
    )

    render(<AgentTimelinePanel />)

    expect(await screen.findByText(/loading agent timeline/i)).toBeInTheDocument()
    await act(async () => {
      rejectTimeline(new Error('network down'))
    })
    expect(await screen.findByText(/unable to load agent timeline/i)).toBeInTheDocument()
    expect(screen.queryByText(/no recent activity to display/i)).not.toBeInTheDocument()
  })
})

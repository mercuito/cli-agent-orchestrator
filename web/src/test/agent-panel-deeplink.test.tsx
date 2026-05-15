import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { AgentPanel } from '../components/AgentPanel'
import { AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT } from '../generated/caoEventPayloadTypes'

const terminalViewMock = vi.hoisted(() => vi.fn(() => <div data-testid="terminal-view" />))
const selectSession = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const showSnackbar = vi.hoisted(() => vi.fn())
const storeState = vi.hoisted(() => ({
  sessions: [] as Array<{ id: string; name: string; status: string }>,
  activeSession: null as string | null,
  activeSessionDetail: null as any,
}))
const getTerminal = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve({
      id: 'term-1',
      name: 'developer-1234',
      provider: 'codex',
      session_name: 'cao-linear-discovery-partner',
      agent_profile: 'developer',
      status: 'idle',
      last_active: null,
    }),
  ),
)
const getAgentRuntimeTerminal = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve({
      terminal: {
        id: 'term-2',
        name: 'developer-5678',
        provider: 'codex',
        session_name: 'cao-linear-discovery-partner',
        agent_profile: 'developer',
        status: 'idle',
        last_active: null,
      },
      terminal_token: 'runtime-token',
    }),
  ),
)
const listAgentIdentities = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve([
      {
        agent_identity_id: 'aria',
        display_name: 'Aria',
        agent_profile: 'partner',
        cli_provider: 'codex',
        active: false,
        active_terminal_id: null,
        active_workspace_context_id: null,
        last_active_at: null,
      },
    ]),
  ),
)
const getAgentIdentityTimeline = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve({
      identity: {
        agent_identity_id: 'aria',
        display_name: 'Aria',
        agent_profile: 'partner',
        cli_provider: 'codex',
        active: false,
        active_terminal_id: null,
        active_workspace_context_id: null,
        last_active_at: null,
      },
      events: [
        {
          event_id: 'linear:agent_mentioned:mention',
          event_name: 'agent_mentioned',
          event_type_key: 'LinearAgentMentionedEvent',
          source_type: 'linear',
          source_id: 'msg-1',
          occurred_at: '2026-05-13T12:00:00',
          correlation_id: null,
          causation_id: null,
          event_data: {},
          participant_role: 'mentioned',
        },
      ],
    }),
  ),
)

vi.mock('../components/TerminalView', () => ({
  TerminalView: terminalViewMock,
}))

vi.mock('../api', () => ({
  api: {
    listProviders: vi.fn(() => Promise.resolve([{ name: 'codex', binary: 'codex', installed: true }])),
    listProfiles: vi.fn(() => Promise.resolve([{ name: 'developer', description: 'Developer', source: 'built-in' }])),
    listAgentIdentities,
    getAgentIdentityTimeline,
    getAgentIdentityRelatedEvents: vi.fn(() => Promise.resolve({
      event: null,
      correlation_events: [],
      causation_events: { direct_cause: null, direct_effects: [] },
    })),
    getTerminal,
    getAgentRuntimeTerminal,
    getTerminalStatus: vi.fn(() => Promise.resolve('idle')),
    getWorkingDirectory: vi.fn(() => Promise.resolve({ working_directory: null })),
    listActiveMonitoringSessions: vi.fn(() => Promise.resolve([])),
    listActiveBatons: vi.fn(() => Promise.resolve([])),
  },
}))

vi.mock('../store', () => ({
  useStore: vi.fn((selector?: (state: any) => any) => {
    const state = {
      sessions: storeState.sessions,
      fetchSessions: vi.fn(),
      activeSession: storeState.activeSession,
      activeSessionDetail: storeState.activeSessionDetail,
      selectSession,
      createSession: vi.fn(),
      deleteSession: vi.fn(),
      terminalStatuses: {},
      activeMonitoringByTerminal: {},
      activeBatonsByHolder: {},
      setTerminalStatus: vi.fn(),
      setActiveMonitoringSessions: vi.fn(),
      setActiveBatons: vi.fn(),
      showSnackbar,
    }
    return selector ? selector(state) : state
  }),
}))

describe('AgentPanel', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    storeState.sessions = []
    storeState.activeSession = null
    storeState.activeSessionDetail = null
  })

  describe('identity timeline boundary', () => {
    it('renders the identity timeline panel through the Agents panel boundary', async () => {
      render(<AgentPanel />)

      expect(await screen.findByRole('button', { name: /aria/i })).toBeInTheDocument()
      expect(await screen.findByTestId('identity-timeline')).toBeInTheDocument()
      expect(screen.getByText('linear:agent_mentioned:mention')).toBeInTheDocument()
      expect(listAgentIdentities).toHaveBeenCalled()
      expect(getAgentIdentityTimeline).toHaveBeenCalledWith('aria')
    })
  })

  describe('terminal deep links', () => {
    it('passes the initial terminal token through to TerminalView', async () => {
      render(<AgentPanel initialTerminalId="term-1" initialTerminalToken="signed-token" />)

      await waitFor(() => {
        expect(terminalViewMock).toHaveBeenCalledWith(
          expect.objectContaining({
            terminalId: 'term-1',
            provider: 'codex',
            agentProfile: 'developer',
            terminalToken: 'signed-token',
          }),
          {},
        )
      })

      expect(getTerminal).toHaveBeenCalledWith('term-1')
      expect(selectSession).toHaveBeenCalledWith('cao-linear-discovery-partner')
    })

    it('resolves a durable agent deep link to the current terminal', async () => {
      render(<AgentPanel initialAgentId="discovery_partner" initialAgentToken="agent-token" />)

      await waitFor(() => {
        expect(terminalViewMock).toHaveBeenCalledWith(
          expect.objectContaining({
            terminalId: 'term-2',
            provider: 'codex',
            agentProfile: 'developer',
            terminalToken: 'runtime-token',
          }),
          {},
        )
      })

      expect(getAgentRuntimeTerminal).toHaveBeenCalledWith('discovery_partner', 'agent-token')
      expect(selectSession).toHaveBeenCalledWith('cao-linear-discovery-partner')
    })

    it('reports a consumed terminal deep link so parent tab remounts do not replay it', async () => {
      const onConsumed = vi.fn()

      render(
        <AgentPanel
          initialTerminalId="term-1"
          initialTerminalToken="signed-token"
          onInitialDeepLinkConsumed={onConsumed}
        />,
      )

      await waitFor(() => {
        expect(onConsumed).toHaveBeenCalledTimes(1)
      })
      expect(getTerminal).toHaveBeenCalledWith('term-1')
    })

    it('passes the session terminal token through when opening a listed terminal', async () => {
      storeState.activeSession = 'cao-linear-smoke-tester'
      storeState.activeSessionDetail = {
        session: { id: 'cao-linear-smoke-tester', name: 'cao-linear-smoke-tester', status: 'active' },
        terminals: [
          {
            id: 'term-3',
            tmux_session: 'cao-linear-smoke-tester',
            tmux_window: '0',
            provider: 'codex',
            agent_profile: 'linear_smoke_tester',
            agent_identity_id: 'linear_smoke_tester',
            terminal_token: 'session-terminal-token',
            last_active: null,
          },
        ],
      }

      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('button', { name: /open terminal/i }))

      await waitFor(() => {
        expect(terminalViewMock).toHaveBeenCalledWith(
          expect.objectContaining({
            terminalId: 'term-3',
            provider: 'codex',
            agentProfile: 'linear_smoke_tester',
            terminalToken: 'session-terminal-token',
          }),
          {},
        )
      })
    })

    it('focuses a runtime delivery terminal reference through the existing terminal open flow', async () => {
      getAgentIdentityTimeline.mockResolvedValueOnce({
        identity: {
          agent_identity_id: 'aria',
          display_name: 'Aria',
          agent_profile: 'partner',
          cli_provider: 'codex',
          active: false,
          active_terminal_id: null,
          active_workspace_context_id: null,
          last_active_at: null,
        },
        events: [
          {
            event_id: 'runtime:event:delivery-ops-417',
            event_name: 'agent_runtime_notification_delivery',
            event_type_key: AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
            source_type: 'cao_runtime',
            source_id: 'notification:42',
            occurred_at: '2026-05-13T12:01:00',
            correlation_id: null,
            causation_id: null,
            event_data: {
              source_kind: 'linear_mention',
              message_body: 'Aria, can you trace the stuck inbox delivery?',
              terminal_id: 'term-aria-main',
              outcome: 'delivered',
            },
            participant_role: 'delivery_target',
          },
        ],
      })
      getTerminal.mockResolvedValueOnce({
        id: 'term-aria-main',
        name: 'developer-aria',
        provider: 'codex',
        session_name: 'cao-linear-discovery-partner',
        agent_profile: 'developer',
        status: 'idle',
        last_active: null,
      })

      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('button', { name: /open terminal term-aria-main/i }))

      await waitFor(() => {
        expect(terminalViewMock).toHaveBeenCalledWith(
          expect.objectContaining({
            terminalId: 'term-aria-main',
            provider: 'codex',
            agentProfile: 'developer',
          }),
          {},
        )
      })
      expect(getTerminal).toHaveBeenCalledWith('term-aria-main')
      expect(selectSession).toHaveBeenCalledWith('cao-linear-discovery-partner')
    })
  })
})

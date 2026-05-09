import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { AgentPanel } from '../components/AgentPanel'

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

vi.mock('../components/TerminalView', () => ({
  TerminalView: terminalViewMock,
}))

vi.mock('../api', () => ({
  api: {
    listProviders: vi.fn(() => Promise.resolve([{ name: 'codex', binary: 'codex', installed: true }])),
    listProfiles: vi.fn(() => Promise.resolve([{ name: 'developer', description: 'Developer', source: 'built-in' }])),
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

describe('AgentPanel terminal deep links', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    storeState.sessions = []
    storeState.activeSession = null
    storeState.activeSessionDetail = null
  })

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
})

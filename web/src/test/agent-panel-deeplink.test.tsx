import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, waitFor, cleanup } from '@testing-library/react'
import { AgentPanel } from '../components/AgentPanel'

const terminalViewMock = vi.hoisted(() => vi.fn(() => <div data-testid="terminal-view" />))
const selectSession = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const showSnackbar = vi.hoisted(() => vi.fn())
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
  useStore: vi.fn(() => ({
    sessions: [],
    fetchSessions: vi.fn(),
    activeSession: null,
    activeSessionDetail: null,
    selectSession,
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    terminalStatuses: {},
    setTerminalStatus: vi.fn(),
    setActiveMonitoringSessions: vi.fn(),
    setActiveBatons: vi.fn(),
    showSnackbar,
  })),
}))

describe('AgentPanel terminal deep links', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
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
})

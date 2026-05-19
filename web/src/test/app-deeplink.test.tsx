import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

const agentPanelMock = vi.hoisted(() =>
  vi.fn(({ initialTerminalId, initialTerminalToken, onInitialDeepLinkConsumed }) => (
    <div>
      <div data-testid="agent-panel-terminal-id">{initialTerminalId ?? ''}</div>
      <div data-testid="agent-panel-terminal-token">{initialTerminalToken ?? ''}</div>
      <button type="button" onClick={onInitialDeepLinkConsumed}>
        consume deep link
      </button>
    </div>
  )),
)
const listAgents = vi.hoisted(() => vi.fn(() => Promise.resolve([])))

vi.mock('../components/AgentPanel', () => ({
  AgentPanel: agentPanelMock,
}))

vi.mock('../api', () => ({
  api: {
    listAgents,
  },
}))

vi.mock('../store', () => ({
  useStore: vi.fn((selector?: (state: any) => any) => {
    const state = {
      sessions: [{ id: 'cao-linear-discovery-partner', name: 'cao-linear-discovery-partner', status: 'active' }],
      connected: true,
      fetchSessions: vi.fn(),
      snackbar: null,
      hideSnackbar: vi.fn(),
    }
    return selector ? selector(state) : state
  }),
}))

describe('App deep links', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    listAgents.mockResolvedValue([])
    window.history.replaceState(null, '', '/')
  })

  it('does not replay a consumed terminal deep link when returning to the agents tab', async () => {
    window.history.replaceState(null, '', '/?terminal_id=term-1&terminal_token=signed-token')

    render(<App />)

    await waitFor(() => expect(listAgents).toHaveBeenCalled())

    expect(screen.getByTestId('agent-panel-terminal-id')).toHaveTextContent('term-1')
    expect(screen.getByTestId('agent-panel-terminal-token')).toHaveTextContent('signed-token')

    fireEvent.click(screen.getByRole('button', { name: /consume deep link/i }))
    fireEvent.click(screen.getByRole('tab', { name: /home/i }))
    fireEvent.click(screen.getByRole('tab', { name: /agents/i }))

    expect(screen.getByTestId('agent-panel-terminal-id')).toHaveTextContent('')
    expect(screen.getByTestId('agent-panel-terminal-token')).toHaveTextContent('')
  })

  it('does not show the session count as the agents tab badge', async () => {
    window.history.replaceState(null, '', '/?view=agents')

    render(<App />)

    await waitFor(() => expect(listAgents).toHaveBeenCalled())

    expect(screen.getByRole('tab', { name: /^agents$/i })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /agents\s+1/i })).not.toBeInTheDocument()
  })

  it('shows the configured agent count as the agents tab badge', async () => {
    listAgents.mockResolvedValue([{}, {}] as any)

    render(<App />)

    await waitFor(() => expect(screen.getByRole('tab', { name: /agents/i })).toHaveTextContent(/agents\s*2/i))
    expect(screen.queryByRole('tab', { name: /agents\s+1/i })).not.toBeInTheDocument()
  })
})

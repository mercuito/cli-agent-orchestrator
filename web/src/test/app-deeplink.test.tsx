import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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

vi.mock('../components/AgentPanel', () => ({
  AgentPanel: agentPanelMock,
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
    window.history.replaceState(null, '', '/')
  })

  it('does not replay a consumed terminal deep link when returning to the agents tab', () => {
    window.history.replaceState(null, '', '/?terminal_id=term-1&terminal_token=signed-token')

    render(<App />)

    expect(screen.getByTestId('agent-panel-terminal-id')).toHaveTextContent('term-1')
    expect(screen.getByTestId('agent-panel-terminal-token')).toHaveTextContent('signed-token')

    fireEvent.click(screen.getByRole('button', { name: /consume deep link/i }))
    fireEvent.click(screen.getByRole('tab', { name: /home/i }))
    fireEvent.click(screen.getByRole('tab', { name: /agents/i }))

    expect(screen.getByTestId('agent-panel-terminal-id')).toHaveTextContent('')
    expect(screen.getByTestId('agent-panel-terminal-token')).toHaveTextContent('')
  })
})

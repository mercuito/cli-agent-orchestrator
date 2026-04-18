import { describe, it, expect, vi, beforeEach, afterAll } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { StatusBadge } from '../components/StatusBadge'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { ConfirmModal } from '../components/ConfirmModal'
import { MonitoringIndicator } from '../components/MonitoringIndicator'
import { useStore } from '../store'

describe('StatusBadge', () => {
  it('renders idle status', () => {
    render(<StatusBadge status="idle" />)
    expect(screen.getByText('Idle')).toBeInTheDocument()
  })

  it('renders processing status', () => {
    render(<StatusBadge status="processing" />)
    expect(screen.getByText('Processing')).toBeInTheDocument()
  })

  it('renders completed status', () => {
    render(<StatusBadge status="completed" />)
    expect(screen.getByText('Completed')).toBeInTheDocument()
  })

  it('renders error status', () => {
    render(<StatusBadge status="error" />)
    expect(screen.getByText('Error')).toBeInTheDocument()
  })

  it('renders waiting_user_answer status', () => {
    render(<StatusBadge status="waiting_user_answer" />)
    expect(screen.getByText('Awaiting Input')).toBeInTheDocument()
  })

  it('renders null status as unknown', () => {
    render(<StatusBadge status={null} />)
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })
})

describe('MonitoringIndicator', () => {
  function mockSession(overrides: Partial<import('../api').MonitoringSession> = {}): import('../api').MonitoringSession {
    return {
      id: 'sess-1',
      terminal_id: 'term-x',
      peer_terminal_ids: [],
      label: null,
      started_at: new Date().toISOString(),
      ended_at: null,
      status: 'active',
      ...overrides,
    }
  }

  beforeEach(() => {
    useStore.setState({ activeMonitoringByTerminal: {} })
  })

  it('renders nothing when the terminal is not monitored', () => {
    const { container } = render(<MonitoringIndicator terminalId="term-x" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders an indicator when the terminal is monitored', () => {
    useStore.setState({
      activeMonitoringByTerminal: { 'term-x': mockSession() },
    })
    render(<MonitoringIndicator terminalId="term-x" />)
    expect(screen.getByLabelText(/being monitored/i)).toBeInTheDocument()
  })

  it('reacts to store changes without remounting', () => {
    render(<MonitoringIndicator terminalId="term-x" />)
    expect(screen.queryByLabelText(/being monitored/i)).not.toBeInTheDocument()

    act(() => {
      useStore.setState({
        activeMonitoringByTerminal: { 'term-x': mockSession() },
      })
    })
    expect(screen.getByLabelText(/being monitored/i)).toBeInTheDocument()

    act(() => {
      useStore.setState({ activeMonitoringByTerminal: {} })
    })
    expect(screen.queryByLabelText(/being monitored/i)).not.toBeInTheDocument()
  })

  it('shows indicator for the right terminal only', () => {
    useStore.setState({
      activeMonitoringByTerminal: { 'term-a': mockSession({ terminal_id: 'term-a' }) },
    })
    const { container: aEl } = render(<MonitoringIndicator terminalId="term-a" />)
    const { container: bEl } = render(<MonitoringIndicator terminalId="term-b" />)
    expect(aEl).not.toBeEmptyDOMElement()
    expect(bEl).toBeEmptyDOMElement()
  })

  it('tooltip shows the session label', () => {
    useStore.setState({
      activeMonitoringByTerminal: {
        'term-x': mockSession({ label: 'review-v2' }),
      },
    })
    render(<MonitoringIndicator terminalId="term-x" />)
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent('Label:')
    expect(tooltip).toHaveTextContent('review-v2')
  })

  it('tooltip falls back to short session id when label is null', () => {
    useStore.setState({
      activeMonitoringByTerminal: {
        'term-x': mockSession({ id: '068d4299-0f97-4b34-b29c-05555995be21', label: null }),
      },
    })
    render(<MonitoringIndicator terminalId="term-x" />)
    const tooltip = screen.getByRole('tooltip')
    // First 8 chars of the uuid — enough to disambiguate without being noisy
    expect(tooltip).toHaveTextContent('068d4299')
  })

  it('tooltip shows "all" for empty peer set', () => {
    useStore.setState({
      activeMonitoringByTerminal: {
        'term-x': mockSession({ peer_terminal_ids: [] }),
      },
    })
    render(<MonitoringIndicator terminalId="term-x" />)
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent('Peers:')
    expect(tooltip).toHaveTextContent('all')
  })

  it('tooltip lists peers when scoped', () => {
    useStore.setState({
      activeMonitoringByTerminal: {
        'term-x': mockSession({ peer_terminal_ids: ['rev-1', 'rev-2'] }),
      },
    })
    render(<MonitoringIndicator terminalId="term-x" />)
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent('rev-1, rev-2')
  })

  it('tooltip shows relative start time', () => {
    const started = new Date(Date.now() - 5 * 60 * 1000).toISOString()  // 5 min ago
    useStore.setState({
      activeMonitoringByTerminal: {
        'term-x': mockSession({ started_at: started }),
      },
    })
    render(<MonitoringIndicator terminalId="term-x" />)
    expect(screen.getByRole('tooltip')).toHaveTextContent(/5m ago/)
  })
})

describe('ErrorBoundary', () => {
  // Suppress console.error for intentional error throws
  const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

  afterAll(() => consoleSpy.mockRestore())

  function ThrowingComponent(): JSX.Element {
    throw new Error('Test error')
  }

  it('catches errors and shows fallback', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
  })

  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Hello</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })
})

describe('ConfirmModal', () => {
  it('renders when open', () => {
    render(
      <ConfirmModal
        open={true}
        title="Delete Item"
        message="Are you sure?"
        details={[]}
        confirmLabel="Delete"
        variant="danger"
        loading={false}
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText('Delete Item')).toBeInTheDocument()
    expect(screen.getByText('Are you sure?')).toBeInTheDocument()
    expect(screen.getByText('Delete')).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(
      <ConfirmModal
        open={false}
        title="Delete Item"
        message="Are you sure?"
        details={[]}
        confirmLabel="Delete"
        variant="danger"
        loading={false}
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.queryByText('Delete Item')).not.toBeInTheDocument()
  })

  it('shows details when provided', () => {
    render(
      <ConfirmModal
        open={true}
        title="Confirm"
        message="Check details"
        details={[{ label: 'Name', value: 'test-flow' }, { label: 'Schedule', value: '0 9 * * *' }]}
        confirmLabel="OK"
        variant="danger"
        loading={false}
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('test-flow')).toBeInTheDocument()
    expect(screen.getByText('Schedule')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    render(
      <ConfirmModal
        open={true}
        title="Deleting"
        message="Please wait"
        details={[]}
        confirmLabel="Delete"
        variant="danger"
        loading={true}
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    )
    const button = screen.getByText('Closing...').closest('button')
    expect(button).toBeDisabled()
  })
})

import { describe, it, expect, vi, beforeEach, afterAll } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { StatusBadge } from '../components/StatusBadge'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { ConfirmModal } from '../components/ConfirmModal'
import { MonitoringIndicator } from '../components/MonitoringIndicator'
import { MonitoringButton } from '../components/MonitoringButton'
import { useStore } from '../store'
import { api } from '../api'

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
      label: null,
      started_at: new Date().toISOString(),
      ended_at: null,
      status: 'active',
      ...overrides,
    }
  }

  function hoverAndGetTooltip() {
    const trigger = screen.getByLabelText(/being monitored/i)
    fireEvent.mouseEnter(trigger)
    return screen.getByRole('tooltip')
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

  it('tooltip only renders when hovered or focused', () => {
    useStore.setState({
      activeMonitoringByTerminal: { 'term-x': mockSession() },
    })
    render(<MonitoringIndicator terminalId="term-x" />)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    fireEvent.mouseEnter(screen.getByLabelText(/being monitored/i))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()

    fireEvent.mouseLeave(screen.getByLabelText(/being monitored/i))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
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
    const tooltip = hoverAndGetTooltip()
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
    const tooltip = hoverAndGetTooltip()
    expect(tooltip).toHaveTextContent('068d4299')
  })

  it('tooltip shows relative start time', () => {
    const started = new Date(Date.now() - 5 * 60 * 1000).toISOString()
    useStore.setState({
      activeMonitoringByTerminal: {
        'term-x': mockSession({ started_at: started }),
      },
    })
    render(<MonitoringIndicator terminalId="term-x" />)
    expect(hoverAndGetTooltip()).toHaveTextContent(/5m ago/)
  })

  it('tooltip does NOT render a peer list', () => {
    // Peer scoping moved to query time on /log — the session itself
    // has no peer set to display, so the "Peers:" line is gone.
    useStore.setState({
      activeMonitoringByTerminal: { 'term-x': mockSession() },
    })
    render(<MonitoringIndicator terminalId="term-x" />)
    const tooltip = hoverAndGetTooltip()
    expect(tooltip.textContent).not.toMatch(/peers:/i)
  })
})

describe('MonitoringButton', () => {
  function mockSession(overrides: Partial<import('../api').MonitoringSession> = {}): import('../api').MonitoringSession {
    return {
      id: 'sess-1',
      terminal_id: 'term-x',
      label: null,
      started_at: new Date().toISOString(),
      ended_at: null,
      status: 'active',
      ...overrides,
    }
  }

  beforeEach(() => {
    useStore.setState({
      activeMonitoringByTerminal: {},
      snackbar: null,
    })
    vi.restoreAllMocks()
  })

  it('renders a Monitor button when the terminal has no active session', () => {
    render(<MonitoringButton terminalId="term-x" />)
    expect(screen.getByRole('button', { name: /^monitor$/i })).toBeInTheDocument()
  })

  it('renders a Stop button when the terminal has an active session', () => {
    useStore.setState({
      activeMonitoringByTerminal: { 'term-x': mockSession() },
    })
    render(<MonitoringButton terminalId="term-x" />)
    expect(screen.getByRole('button', { name: /^stop$/i })).toBeInTheDocument()
  })

  it('clicking Monitor calls startMonitoring with terminal_id and a dashboard-HHmmss label', async () => {
    const spy = vi.spyOn(api, 'startMonitoring').mockResolvedValue(mockSession())

    render(<MonitoringButton terminalId="term-x" />)
    fireEvent.click(screen.getByRole('button', { name: /^monitor$/i }))

    // Allow the async handler to resolve
    await Promise.resolve()

    expect(spy).toHaveBeenCalledTimes(1)
    const [terminalId, label] = spy.mock.calls[0]
    expect(terminalId).toBe('term-x')
    // Label should match dashboard-HHmmss — 6 digits after the prefix
    expect(label).toMatch(/^dashboard-\d{6}$/)
  })

  it('clicking Stop calls endMonitoring with the active session id', async () => {
    useStore.setState({
      activeMonitoringByTerminal: {
        'term-x': mockSession({ id: 'sess-to-end' }),
      },
    })
    const spy = vi.spyOn(api, 'endMonitoring').mockResolvedValue({
      ...mockSession({ id: 'sess-to-end' }),
      status: 'ended' as const,
      ended_at: new Date().toISOString(),
    })

    render(<MonitoringButton terminalId="term-x" />)
    fireEvent.click(screen.getByRole('button', { name: /^stop$/i }))
    await Promise.resolve()

    expect(spy).toHaveBeenCalledWith('sess-to-end')
  })

  it('start error surfaces as a snackbar', async () => {
    vi.spyOn(api, 'startMonitoring').mockRejectedValue(new Error('500 server broke'))
    render(<MonitoringButton terminalId="term-x" />)
    fireEvent.click(screen.getByRole('button', { name: /^monitor$/i }))
    await new Promise(r => setTimeout(r, 0))

    const snackbar = useStore.getState().snackbar
    expect(snackbar?.type).toBe('error')
    expect(snackbar?.message.toLowerCase()).toContain('failed to start monitoring')
  })

  it('stop error surfaces as a snackbar', async () => {
    useStore.setState({
      activeMonitoringByTerminal: { 'term-x': mockSession() },
    })
    vi.spyOn(api, 'endMonitoring').mockRejectedValue(new Error('404 missing'))
    render(<MonitoringButton terminalId="term-x" />)
    fireEvent.click(screen.getByRole('button', { name: /^stop$/i }))
    await new Promise(r => setTimeout(r, 0))

    const snackbar = useStore.getState().snackbar
    expect(snackbar?.type).toBe('error')
    expect(snackbar?.message.toLowerCase()).toContain('failed to stop monitoring')
  })

  it('button is disabled while the request is in flight', async () => {
    // Never-resolving promise so we can inspect the in-flight state
    let _resolve: ((s: any) => void) = () => {}
    vi.spyOn(api, 'startMonitoring').mockImplementation(
      () => new Promise(r => { _resolve = r }) as Promise<any>
    )

    render(<MonitoringButton terminalId="term-x" />)
    const btn = screen.getByRole('button', { name: /^monitor$/i })
    fireEvent.click(btn)
    // After click, button must be disabled (prevents double-submit)
    expect(btn).toBeDisabled()

    // Resolve to keep the test environment clean
    act(() => { _resolve(mockSession()) })
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

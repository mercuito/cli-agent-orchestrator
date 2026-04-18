import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useStore } from '../store'
import { MonitoringSession } from '../api'

function mockSession(overrides: Partial<MonitoringSession> = {}): MonitoringSession {
  return {
    id: overrides.id || 'sess-1',
    terminal_id: overrides.terminal_id || 'term-a',
    label: overrides.label !== undefined ? overrides.label : null,
    started_at: overrides.started_at || '2026-04-18T10:00:00',
    ended_at: overrides.ended_at !== undefined ? overrides.ended_at : null,
    status: overrides.status || 'active',
  }
}

describe('Store', () => {
  beforeEach(() => {
    // Reset store state between tests
    useStore.setState({
      sessions: [],
      activeSession: null,
      activeSessionDetail: null,
      terminalStatuses: {},
      activeMonitoringByTerminal: {},
      snackbar: null,
    })
  })

  it('has correct initial state', () => {
    const state = useStore.getState()
    expect(state.sessions).toEqual([])
    expect(state.activeSession).toBeNull()
    expect(state.activeSessionDetail).toBeNull()
    expect(state.terminalStatuses).toEqual({})
    expect(state.activeMonitoringByTerminal).toEqual({})
    expect(state.snackbar).toBeNull()
  })

  it('sets terminal status', () => {
    const { setTerminalStatus } = useStore.getState()
    setTerminalStatus('term-1', 'idle')
    expect(useStore.getState().terminalStatuses['term-1']).toBe('idle')
  })

  it('sets multiple terminal statuses independently', () => {
    const { setTerminalStatus } = useStore.getState()
    setTerminalStatus('term-1', 'idle')
    setTerminalStatus('term-2', 'processing')
    const statuses = useStore.getState().terminalStatuses
    expect(statuses['term-1']).toBe('idle')
    expect(statuses['term-2']).toBe('processing')
  })

  it('shows and clears snackbar', () => {
    const { showSnackbar } = useStore.getState()
    showSnackbar({ type: 'success', message: 'Test message' })
    expect(useStore.getState().snackbar).toEqual({ type: 'success', message: 'Test message' })

    useStore.setState({ snackbar: null })
    expect(useStore.getState().snackbar).toBeNull()
  })

  it('maps active monitoring sessions by terminal_id', () => {
    const { setActiveMonitoringSessions } = useStore.getState()
    const a = mockSession({ id: 's-a', terminal_id: 'term-a', label: 'x' })
    const b = mockSession({ id: 's-b', terminal_id: 'term-b' })
    setActiveMonitoringSessions([a, b])
    const map = useStore.getState().activeMonitoringByTerminal
    expect(map['term-a']).toEqual(a)
    expect(map['term-b']).toEqual(b)
  })

  it('replaces the monitoring map rather than merging', () => {
    const { setActiveMonitoringSessions } = useStore.getState()
    setActiveMonitoringSessions([
      mockSession({ id: 's-a', terminal_id: 'a' }),
      mockSession({ id: 's-b', terminal_id: 'b' }),
    ])
    setActiveMonitoringSessions([mockSession({ id: 's-c', terminal_id: 'c' })])
    // A session ending must cause its terminal to stop appearing — merge
    // semantics would leak ended sessions into the display forever.
    expect(Object.keys(useStore.getState().activeMonitoringByTerminal)).toEqual(['c'])
  })

  it('empty list clears all entries', () => {
    const { setActiveMonitoringSessions } = useStore.getState()
    setActiveMonitoringSessions([mockSession()])
    setActiveMonitoringSessions([])
    expect(useStore.getState().activeMonitoringByTerminal).toEqual({})
  })

  it('shows error snackbar', () => {
    const { showSnackbar } = useStore.getState()
    showSnackbar({ type: 'error', message: 'Something failed' })
    expect(useStore.getState().snackbar).toEqual({ type: 'error', message: 'Something failed' })
  })
})

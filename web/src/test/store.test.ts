import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useStore } from '../store'
import { Baton, MonitoringSession } from '../api'

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

function mockBaton(overrides: Partial<Baton> = {}): Baton {
  return {
    id: overrides.id || 'baton-1',
    title: overrides.title || 'Review implementation',
    status: overrides.status || 'active',
    originator_id: overrides.originator_id || 'term-origin',
    current_holder_id: overrides.current_holder_id !== undefined ? overrides.current_holder_id : 'term-a',
    return_stack: overrides.return_stack || [],
    expected_next_action: overrides.expected_next_action !== undefined ? overrides.expected_next_action : 'review the patch',
    created_at: overrides.created_at || '2026-05-04T10:00:00',
    updated_at: overrides.updated_at || '2026-05-04T10:05:00',
    last_nudged_at: overrides.last_nudged_at !== undefined ? overrides.last_nudged_at : null,
    completed_at: overrides.completed_at !== undefined ? overrides.completed_at : null,
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
      activeBatonsByHolder: {},
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
    expect(state.activeBatonsByHolder).toEqual({})
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

  it('groups active batons by current_holder_id', () => {
    const { setActiveBatons } = useStore.getState()
    const a1 = mockBaton({ id: 'baton-a1', current_holder_id: 'term-a' })
    const a2 = mockBaton({ id: 'baton-a2', current_holder_id: 'term-a' })
    const b1 = mockBaton({ id: 'baton-b1', current_holder_id: 'term-b' })

    setActiveBatons([a1, a2, b1])

    expect(useStore.getState().activeBatonsByHolder).toEqual({
      'term-a': [a1, a2],
      'term-b': [b1],
    })
  })

  it('replaces the baton holder map rather than merging', () => {
    const { setActiveBatons } = useStore.getState()
    setActiveBatons([
      mockBaton({ id: 'baton-a', current_holder_id: 'term-a' }),
      mockBaton({ id: 'baton-b', current_holder_id: 'term-b' }),
    ])
    setActiveBatons([mockBaton({ id: 'baton-c', current_holder_id: 'term-c' })])

    expect(Object.keys(useStore.getState().activeBatonsByHolder)).toEqual(['term-c'])
  })

  it('skips batons without a current holder', () => {
    const { setActiveBatons } = useStore.getState()
    setActiveBatons([
      mockBaton({ id: 'orphanish', current_holder_id: null }),
      mockBaton({ id: 'held', current_holder_id: 'term-a' }),
    ])

    expect(useStore.getState().activeBatonsByHolder).toEqual({
      'term-a': [mockBaton({ id: 'held', current_holder_id: 'term-a' })],
    })
  })

  it('shows error snackbar', () => {
    const { showSnackbar } = useStore.getState()
    showSnackbar({ type: 'error', message: 'Something failed' })
    expect(useStore.getState().snackbar).toEqual({ type: 'error', message: 'Something failed' })
  })
})

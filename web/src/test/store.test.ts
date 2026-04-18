import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useStore } from '../store'

describe('Store', () => {
  beforeEach(() => {
    // Reset store state between tests
    useStore.setState({
      sessions: [],
      activeSession: null,
      activeSessionDetail: null,
      terminalStatuses: {},
      monitoredTerminalIds: {},
      snackbar: null,
    })
  })

  it('has correct initial state', () => {
    const state = useStore.getState()
    expect(state.sessions).toEqual([])
    expect(state.activeSession).toBeNull()
    expect(state.activeSessionDetail).toBeNull()
    expect(state.terminalStatuses).toEqual({})
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

  it('sets monitored terminal ids from an active-session list', () => {
    const { setMonitoredTerminalIds } = useStore.getState()
    setMonitoredTerminalIds(['term-a', 'term-b'])
    const ids = useStore.getState().monitoredTerminalIds
    expect(ids).toEqual({ 'term-a': true, 'term-b': true })
  })

  it('replaces the monitored set rather than merging', () => {
    const { setMonitoredTerminalIds } = useStore.getState()
    setMonitoredTerminalIds(['a', 'b'])
    setMonitoredTerminalIds(['c'])
    // A session ending must cause its terminal to stop appearing — merge
    // semantics would leak ended sessions into the display forever.
    expect(useStore.getState().monitoredTerminalIds).toEqual({ c: true })
  })

  it('empty list clears all entries', () => {
    const { setMonitoredTerminalIds } = useStore.getState()
    setMonitoredTerminalIds(['a'])
    setMonitoredTerminalIds([])
    expect(useStore.getState().monitoredTerminalIds).toEqual({})
  })

  it('shows error snackbar', () => {
    const { showSnackbar } = useStore.getState()
    showSnackbar({ type: 'error', message: 'Something failed' })
    expect(useStore.getState().snackbar).toEqual({ type: 'error', message: 'Something failed' })
  })
})

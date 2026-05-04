import { create } from 'zustand'
import { api, Baton, MonitoringSession, Session, SessionDetail, TerminalMeta } from './api'

// Only trigger React re-renders when data actually changed
function jsonEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

interface Snackbar {
  type: 'success' | 'error' | 'info'
  message: string
}

interface Store {
  sessions: Session[]
  activeSession: string | null
  activeSessionDetail: SessionDetail | null
  connected: boolean
  snackbar: Snackbar | null
  terminalStatuses: Record<string, string>
  /** Map of terminal_id → its active monitoring session (if any). Under
   *  the single-session model at most one session per terminal can be
   *  active at a time (see ``create_session`` idempotency on the backend),
   *  so a single-value map is all we need. Replaced wholesale each poll
   *  via setActiveMonitoringSessions. */
  activeMonitoringByTerminal: Record<string, MonitoringSession>
  /** Map of terminal_id -> active batons currently held by that terminal.
   *  Unlike monitoring, a terminal can hold several batons, so each value is
   *  an array. Replaced wholesale each poll so completed/transferred batons
   *  disappear promptly. */
  activeBatonsByHolder: Record<string, Baton[]>

  fetchSessions: () => Promise<void>
  selectSession: (name: string | null) => Promise<void>
  createSession: (provider: string, agentProfile: string, workingDirectory?: string) => Promise<void>
  deleteSession: (name: string) => Promise<void>
  showSnackbar: (snackbar: Snackbar) => void
  hideSnackbar: () => void
  setConnected: (connected: boolean) => void
  setTerminalStatus: (id: string, status: string) => void
  clearTerminalStatuses: (ids: string[]) => void
  setActiveMonitoringSessions: (sessions: MonitoringSession[]) => void
  setActiveBatons: (batons: Baton[]) => void
}

export const useStore = create<Store>((set, get) => ({
  sessions: [],
  activeSession: null,
  activeSessionDetail: null,
  connected: false,
  snackbar: null,
  terminalStatuses: {},
  activeMonitoringByTerminal: {},
  activeBatonsByHolder: {},

  fetchSessions: async () => {
    try {
      const sessions = await api.listSessions()
      const prev = get()
      if (!prev.connected || !jsonEqual(prev.sessions, sessions)) {
        set({ sessions, connected: true })
      }
    } catch {
      if (get().connected) set({ connected: false })
    }
  },

  selectSession: async (name) => {
    if (!name) {
      set({ activeSession: null, activeSessionDetail: null })
      return
    }
    set({ activeSession: name })
    try {
      const detail = await api.getSession(name)
      if (!jsonEqual(get().activeSessionDetail, detail)) {
        set({ activeSessionDetail: detail })
      }
    } catch {
      set({ activeSessionDetail: null })
    }
  },

  createSession: async (provider, agentProfile, workingDirectory) => {
    try {
      await api.createSession(provider, agentProfile, undefined, workingDirectory)
      get().showSnackbar({ type: 'success', message: 'Session created' })
      await get().fetchSessions()
    } catch (e: any) {
      get().showSnackbar({ type: 'error', message: e.message || 'Failed to create session' })
    }
  },

  deleteSession: async (name) => {
    try {
      await api.deleteSession(name)
      get().showSnackbar({ type: 'success', message: `Deleted ${name}` })
      if (get().activeSession === name) {
        set({ activeSession: null, activeSessionDetail: null })
      }
      await get().fetchSessions()
    } catch (e: any) {
      get().showSnackbar({ type: 'error', message: e.message || 'Failed to delete session' })
    }
  },

  showSnackbar: (snackbar) => set({ snackbar }),
  hideSnackbar: () => set({ snackbar: null }),
  setConnected: (connected) => set({ connected }),
  setTerminalStatus: (id, status) =>
    set(state => {
      if (state.terminalStatuses[id] === status) return state
      return { terminalStatuses: { ...state.terminalStatuses, [id]: status } }
    }),
  clearTerminalStatuses: (ids) =>
    set(state => {
      const next: Record<string, string> = {}
      for (const id of ids) {
        if (state.terminalStatuses[id]) next[id] = state.terminalStatuses[id]
      }
      if (Object.keys(next).length === Object.keys(state.terminalStatuses).length) return state
      return { terminalStatuses: next }
    }),
  setActiveMonitoringSessions: (sessions) =>
    set(state => {
      // Replace, don't merge: a session ending should drop from the map
      // on the next poll. One session per terminal under the single-session
      // model — if the server ever returns multiples (shouldn't happen),
      // last one wins and we accept it rather than special-casing.
      const next: Record<string, MonitoringSession> = {}
      for (const s of sessions) next[s.terminal_id] = s
      if (jsonEqual(state.activeMonitoringByTerminal, next)) return state
      return { activeMonitoringByTerminal: next }
    }),
  setActiveBatons: (batons) =>
    set(state => {
      const next: Record<string, Baton[]> = {}
      for (const baton of batons) {
        if (!baton.current_holder_id) continue
        if (!next[baton.current_holder_id]) next[baton.current_holder_id] = []
        next[baton.current_holder_id].push(baton)
      }
      if (jsonEqual(state.activeBatonsByHolder, next)) return state
      return { activeBatonsByHolder: next }
    }),
}))

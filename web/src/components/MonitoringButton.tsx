import { useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'

/** Generate a label like ``dashboard-123456`` (HHmmss of the local clock).
 *  Marks the session as operator-initiated and disambiguates rapid clicks
 *  from the same minute. Uniqueness isn't required — session id is the key. */
function defaultLabel(): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  const now = new Date()
  return `dashboard-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
}

/**
 * Single-click Monitor / Stop button for a terminal row.
 *
 * The button reflects the store's ``activeMonitoringByTerminal`` state: if
 * no session is active on this terminal, shows ``Monitor`` and starts one
 * on click. If a session is active, shows ``Stop`` and ends it on click.
 * A ~3s poll flips the state automatically after each action, so we don't
 * mutate the store optimistically.
 *
 * Matches the model in docs/plans/monitoring-sessions.md: one active
 * session per terminal, idempotent start, query-time filtering (so no
 * options to configure at start time).
 */
export function MonitoringButton({ terminalId }: { terminalId: string }) {
  const session = useStore(s => s.activeMonitoringByTerminal[terminalId])
  const showSnackbar = useStore(s => s.showSnackbar)
  const [inFlight, setInFlight] = useState(false)

  const isActive = Boolean(session)

  async function handleStart() {
    setInFlight(true)
    try {
      await api.startMonitoring(terminalId, defaultLabel())
    } catch (e: any) {
      showSnackbar({
        type: 'error',
        message: `Failed to start monitoring: ${e?.message ?? 'unknown error'}`,
      })
    } finally {
      setInFlight(false)
    }
  }

  async function handleStop() {
    if (!session) return
    setInFlight(true)
    try {
      await api.endMonitoring(session.id)
    } catch (e: any) {
      showSnackbar({
        type: 'error',
        message: `Failed to stop monitoring: ${e?.message ?? 'unknown error'}`,
      })
    } finally {
      setInFlight(false)
    }
  }

  if (isActive) {
    return (
      <button
        onClick={handleStop}
        disabled={inFlight}
        className="px-2.5 py-1.5 text-xs font-medium rounded-lg transition-colors bg-red-600/20 hover:bg-red-600/30 text-red-300 border border-red-600/40 disabled:opacity-40 disabled:cursor-not-allowed"
        title="Stop monitoring this agent"
      >
        Stop
      </button>
    )
  }
  return (
    <button
      onClick={handleStart}
      disabled={inFlight}
      className="px-2.5 py-1.5 text-xs font-medium rounded-lg transition-colors bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 border border-sky-600/40 disabled:opacity-40 disabled:cursor-not-allowed"
      title="Start monitoring this agent"
    >
      Monitor
    </button>
  )
}

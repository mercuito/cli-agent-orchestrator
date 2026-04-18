import { Eye } from 'lucide-react'
import { useStore } from '../store'

/**
 * Tiny visual indicator rendered next to a terminal's status badge when a
 * monitoring session is currently targeting that terminal.
 *
 * Reads the ``monitoredTerminalIds`` map from the Zustand store so the
 * parent doesn't have to thread a prop through every render site. Renders
 * nothing when the terminal is not monitored — callers can unconditionally
 * drop it next to every status badge.
 */
export function MonitoringIndicator({ terminalId }: { terminalId: string }) {
  const isMonitored = useStore(state => !!state.monitoredTerminalIds[terminalId])
  if (!isMonitored) return null
  return (
    <span
      aria-label="Being monitored"
      title="Being monitored"
      className="inline-flex items-center justify-center text-sky-400"
    >
      <Eye size={12} />
    </span>
  )
}

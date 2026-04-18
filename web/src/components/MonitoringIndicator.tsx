import { Eye } from 'lucide-react'
import { useStore } from '../store'

/** Compact relative-time formatter. Returns values like "3s ago", "5m ago",
 *  "2h ago", "1d ago". Assumes the timestamp is close enough to "now" that
 *  week-plus resolution isn't needed (monitoring sessions are typically
 *  minutes-to-hours scale). */
function relativeAgo(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'unknown'
  const sec = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

/**
 * Visual indicator rendered next to a terminal's status badge when a
 * monitoring session is currently targeting that terminal.
 *
 * Visual: eye icon ("being watched") + small pulsing red dot ("recording
 * now"), borrowing the recording-LED convention. On hover, a styled tooltip
 * shows the session's label, age, and peer scope so the operator can tell
 * at a glance what's being captured without opening anything.
 *
 * Reads ``activeMonitoringByTerminal`` from the Zustand store so the parent
 * doesn't have to thread a prop through every render site. Renders nothing
 * when the terminal is not monitored — callers can drop it next to every
 * status badge unconditionally.
 */
export function MonitoringIndicator({ terminalId }: { terminalId: string }) {
  const session = useStore(s => s.activeMonitoringByTerminal[terminalId])
  if (!session) return null

  const label = session.label || session.id.slice(0, 8)
  const peers =
    session.peer_terminal_ids.length === 0
      ? 'all'
      : session.peer_terminal_ids.join(', ')

  return (
    <span
      aria-label="Being monitored"
      className="group relative inline-flex items-center justify-center text-sky-400"
    >
      <Eye size={14} />
      <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />

      {/* Tooltip. Always in the DOM so tests and screen readers can reach
          it; Tailwind hides it visually until the parent is hovered. */}
      <span
        role="tooltip"
        className="absolute hidden group-hover:flex flex-col bottom-full left-1/2 -translate-x-1/2 mb-1.5 whitespace-nowrap bg-gray-900 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs shadow-lg pointer-events-none z-10"
      >
        <span className="font-semibold text-gray-100 mb-0.5">Being monitored</span>
        <span className="text-gray-400">
          Label: <span className="text-gray-100">{label}</span>
        </span>
        <span className="text-gray-400">
          Started: <span className="text-gray-100">{relativeAgo(session.started_at)}</span>
        </span>
        <span className="text-gray-400">
          Peers: <span className="text-gray-100">{peers}</span>
        </span>
      </span>
    </span>
  )
}

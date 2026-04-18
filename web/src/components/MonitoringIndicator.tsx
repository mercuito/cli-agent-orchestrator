import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Eye } from 'lucide-react'
import { useStore } from '../store'
import type { MonitoringSession } from '../api'

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

function SessionDetail({ session }: { session: MonitoringSession }) {
  const label = session.label || session.id.slice(0, 8)
  const peers =
    session.peer_terminal_ids.length === 0
      ? 'all'
      : session.peer_terminal_ids.join(', ')
  return (
    <>
      <span className="text-gray-400">
        Label: <span className="text-gray-100">{label}</span>
      </span>
      <span className="text-gray-400">
        Started: <span className="text-gray-100">{relativeAgo(session.started_at)}</span>
      </span>
      <span className="text-gray-400">
        Peers: <span className="text-gray-100">{peers}</span>
      </span>
    </>
  )
}

interface TooltipPos {
  top: number
  left: number
  /** True if the tooltip should render above the trigger; false → below.
   *  Chosen based on available viewport space at show time. */
  above: boolean
}

/**
 * Visual indicator rendered next to a terminal's status badge when one or
 * more monitoring sessions are currently targeting that terminal.
 *
 * Visual: eye icon ("being watched") + small pulsing red dot ("recording
 * now"). On hover, a styled tooltip surfaces every active session's
 * metadata. When more than one session is active on the same terminal
 * (design decision #10 in the monitoring plan), the tooltip shows a count
 * header and lists each session separated by a divider.
 *
 * The tooltip renders via a React portal into document.body with ``fixed``
 * positioning. This is required because the dashboard's session card has
 * ``overflow-hidden`` (to clip content against its rounded corners), which
 * would otherwise clip the tooltip. Portal + fixed escapes every ancestor
 * clipping context.
 *
 * Reads ``activeMonitoringByTerminal`` from the Zustand store so the parent
 * doesn't have to thread a prop through every render site. Renders nothing
 * when the terminal has no active monitoring — callers can drop it next to
 * every status badge unconditionally.
 */
export function MonitoringIndicator({ terminalId }: { terminalId: string }) {
  const sessions = useStore(s => s.activeMonitoringByTerminal[terminalId])
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [pos, setPos] = useState<TooltipPos | null>(null)

  if (!sessions || sessions.length === 0) return null

  function showTooltip() {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    // Pick the side with more room. A rough 200px max-height heuristic —
    // enough for ~4 sessions at current layout; flips to below if the
    // trigger is near the viewport top.
    const above = rect.top > 200
    setPos({
      top: above ? rect.top - 6 : rect.bottom + 6,
      left: rect.left + rect.width / 2,
      above,
    })
  }

  function hideTooltip() {
    setPos(null)
  }

  return (
    <>
      <span
        ref={triggerRef}
        aria-label="Being monitored"
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        tabIndex={0}
        className="relative inline-flex items-center justify-center text-sky-400 outline-none"
      >
        <Eye size={14} />
        <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
      </span>

      {pos &&
        createPortal(
          <span
            role="tooltip"
            style={{
              top: pos.top,
              left: pos.left,
              transform: pos.above
                ? 'translate(-50%, -100%)'
                : 'translate(-50%, 0)',
            }}
            className="fixed flex flex-col bg-gray-900 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs shadow-lg pointer-events-none z-50 whitespace-nowrap"
          >
            <span className="font-semibold text-gray-100 mb-0.5">
              Being monitored
              {sessions.length > 1 && (
                <span className="font-normal text-gray-400"> ({sessions.length} active)</span>
              )}
            </span>
            {sessions.map((session, i) => (
              <div
                key={session.id}
                className={`flex flex-col ${i > 0 ? 'border-t border-gray-700 mt-1 pt-1' : ''}`}
              >
                <SessionDetail session={session} />
              </div>
            ))}
          </span>,
          document.body
        )}
    </>
  )
}

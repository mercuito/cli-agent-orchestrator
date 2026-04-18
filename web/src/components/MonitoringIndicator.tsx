import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Eye } from 'lucide-react'
import { useStore } from '../store'

/** Compact relative-time formatter — "3s ago", "5m ago", "2h ago", "1d ago".
 *  Monitoring sessions are typically minutes-to-hours scale, so a single-unit
 *  approximation is enough. */
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

interface TooltipPos {
  top: number
  left: number
  above: boolean
}

/**
 * Visual indicator rendered next to a terminal's status badge when a
 * monitoring session is currently recording that terminal.
 *
 * Visual: eye icon + pulsing red dot — the recording-LED metaphor. On
 * hover, a styled tooltip shows the session's label and age.
 *
 * Rendered via a React portal with fixed positioning so it escapes the
 * dashboard's ``overflow-hidden`` session card. See
 * docs/plans/monitoring-sessions.md.
 */
export function MonitoringIndicator({ terminalId }: { terminalId: string }) {
  const session = useStore(s => s.activeMonitoringByTerminal[terminalId])
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [pos, setPos] = useState<TooltipPos | null>(null)

  if (!session) return null

  const label = session.label || session.id.slice(0, 8)

  function showTooltip() {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const above = rect.top > 120
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
            <span className="font-semibold text-gray-100 mb-0.5">Being monitored</span>
            <span className="text-gray-400">
              Label: <span className="text-gray-100">{label}</span>
            </span>
            <span className="text-gray-400">
              Started: <span className="text-gray-100">{relativeAgo(session.started_at)}</span>
            </span>
          </span>,
          document.body
        )}
    </>
  )
}

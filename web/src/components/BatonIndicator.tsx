import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Flag } from 'lucide-react'
import { Baton } from '../api'
import { useStore } from '../store'

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

function shortId(id: string | null | undefined): string {
  if (!id) return 'none'
  return id.length > 12 ? id.slice(0, 12) : id
}

interface TooltipPos {
  top: number
  left: number
  above: boolean
}

function BatonSummary({ baton }: { baton: Baton }) {
  const returnChain = baton.return_stack.length
    ? baton.return_stack.map(shortId).join(' -> ')
    : 'empty'

  return (
    <span className="block border-t border-amber-900/40 first:border-t-0 pt-2 first:pt-0 mt-2 first:mt-0">
      <span className="block font-semibold text-gray-100 truncate">{baton.title}</span>
      <span className="block text-gray-400">
        Holder: <span className="text-gray-100 font-mono">{shortId(baton.current_holder_id)}</span>
      </span>
      <span className="block text-gray-400">
        Originator: <span className="text-gray-100 font-mono">{shortId(baton.originator_id)}</span>
      </span>
      <span className="block text-gray-400">
        Expected: <span className="text-gray-100">{baton.expected_next_action || 'unspecified'}</span>
      </span>
      <span className="block text-gray-400">
        Return: <span className="text-gray-100 font-mono">{returnChain}</span>
      </span>
      <span className="block text-gray-400">
        Updated: <span className="text-gray-100">{relativeAgo(baton.updated_at)}</span>
      </span>
    </span>
  )
}

export function BatonIndicator({ terminalId }: { terminalId: string }) {
  const batons = useStore(s => s.activeBatonsByHolder[terminalId] || [])
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [pos, setPos] = useState<TooltipPos | null>(null)

  if (!batons.length) return null

  const count = batons.length
  const label = count === 1 ? 'Holding 1 baton' : `Holding ${count} batons`
  const visibleBatons = batons.slice(0, 3)
  const hiddenCount = Math.max(0, batons.length - visibleBatons.length)

  function showTooltip() {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const above = rect.top > 180
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
        aria-label={label}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        tabIndex={0}
        className="relative inline-flex items-center justify-center text-amber-300 outline-none"
      >
        <Flag size={14} />
        {count > 1 && (
          <span className="absolute -top-2 -right-2 min-w-4 h-4 px-1 rounded-full bg-amber-500 text-[10px] leading-4 text-gray-950 font-semibold text-center">
            {count}
          </span>
        )}
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
            className="fixed block w-72 max-w-[calc(100vw-2rem)] bg-gray-950 border border-amber-800/70 rounded-md px-3 py-2 text-xs shadow-lg pointer-events-none z-50"
          >
            <span className="block font-semibold text-amber-200 mb-1">
              {label}
            </span>
            {visibleBatons.map(baton => (
              <BatonSummary key={baton.id} baton={baton} />
            ))}
            {hiddenCount > 0 && (
              <span className="block text-gray-500 mt-2">+{hiddenCount} more</span>
            )}
          </span>,
          document.body
        )}
    </>
  )
}

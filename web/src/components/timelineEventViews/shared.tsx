import type { ReactNode } from 'react'

export function stringFact(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

export function booleanFact(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

export function primitiveFact(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

export function objectFact(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

export function objectStringFact(value: unknown, ...keys: string[]): string | null {
  const object = objectFact(value)
  if (!object) return null
  for (const key of keys) {
    const fact = primitiveFact(object[key])
    if (fact) return fact
  }
  return null
}

export function firstFact(...values: unknown[]): string | null {
  for (const value of values) {
    const fact = primitiveFact(value)
    if (fact) return fact
  }
  return null
}

export function labelize(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

export function Snippet({ text }: { text: string }) {
  return (
    <div className="mt-2 max-w-3xl rounded border border-gray-700/50 bg-gray-950/50 px-3 py-1.5 text-xs text-gray-300">
      {text}
    </div>
  )
}

export function DetailPill({
  label,
  value,
  tone = 'gray',
}: {
  label: string
  value: string
  tone?: 'gray' | 'blue' | 'emerald' | 'amber' | 'purple'
}) {
  const tones = {
    gray: 'border-gray-700/60 bg-gray-950/50 text-gray-300',
    blue: 'border-blue-800/60 bg-blue-950/40 text-blue-200',
    emerald: 'border-emerald-800/60 bg-emerald-950/40 text-emerald-200',
    amber: 'border-amber-800/60 bg-amber-950/40 text-amber-200',
    purple: 'border-purple-800/60 bg-purple-950/40 text-purple-200',
  }
  return (
    <span className={`inline-flex max-w-full items-center gap-1 rounded border px-2 py-0.5 text-[11px] ${tones[tone]}`}>
      <span className="shrink-0 opacity-70">{label}</span>
      <span className="truncate font-mono">{value}</span>
    </span>
  )
}

export function EntityReferenceButton({
  label,
  ariaLabel,
  icon,
  onClick,
}: {
  label: string
  ariaLabel: string
  icon: JSX.Element
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={onClick}
      className="inline-flex max-w-full items-center gap-1.5 rounded border border-emerald-800/60 bg-emerald-950/40 px-2 py-0.5 text-[11px] font-medium text-emerald-200 transition-colors hover:border-emerald-600 hover:bg-emerald-900/60"
    >
      {icon}
      <span className="truncate">{label}</span>
    </button>
  )
}

export function ViewShell({
  icon,
  title,
  children,
}: {
  icon: JSX.Element
  title: string
  children: ReactNode
}) {
  return (
    <div className="min-w-0">
      <div className="flex min-w-0 items-center gap-2">
        <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded bg-gray-950/80 text-emerald-300">
          {icon}
        </span>
        <span className="truncate text-sm font-semibold text-gray-100">{title}</span>
      </div>
      <div className="mt-1.5 flex min-w-0 flex-wrap gap-1.5">
        {children}
      </div>
    </div>
  )
}

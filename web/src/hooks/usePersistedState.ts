import { useEffect, useRef, useState } from 'react'

/**
 * Like `useState`, but persists the value to localStorage under `key`.
 *
 * Reads the stored value on mount. Writes on every update. Safely no-ops if
 * `localStorage` is unavailable (SSR, privacy modes) or the stored value is
 * malformed — falls back to `initialValue`.
 */
export function usePersistedState<T>(
  key: string,
  initialValue: T,
): [T, (value: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key)
      if (raw === null) return initialValue
      return JSON.parse(raw) as T
    } catch {
      return initialValue
    }
  })

  // Avoid writing the initial value back on the first render if nothing changed.
  const firstRender = useRef(true)
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // localStorage disabled/full — drop the write silently.
    }
  }, [key, value])

  return [value, setValue]
}

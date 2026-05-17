import { useEffect, useState } from 'react'
import { api, ProviderSchema } from '../api'

/**
 * Provider-schema fetcher with a session-level cache.
 *
 * The first consumer in the session triggers a single ``GET /providers``
 * request. Subsequent consumers reuse the same in-flight promise (during
 * loading) or the cached array (after success). The cache lives for the
 * lifetime of the JS module — there is no manual invalidation today
 * because provider capability is a build-time property of the backend.
 *
 * Loading is blocking, not racing: components rendering off this hook
 * see ``status: 'loading'`` until the request resolves and must NOT
 * render dropdowns from a falsy "no providers known" state. That
 * pattern is fragile and prohibited by the agent-config-editor plan.
 */
export interface ProviderSchemaState {
  status: 'loading' | 'ready' | 'error'
  schemas: ProviderSchema[] | null
  error: string | null
}

type Listener = (state: ProviderSchemaState) => void

let cachedState: ProviderSchemaState = {
  status: 'loading',
  schemas: null,
  error: null,
}
let inflight: Promise<ProviderSchema[]> | null = null
const listeners = new Set<Listener>()

function notify(): void {
  for (const listener of listeners) listener(cachedState)
}

function startFetch(): Promise<ProviderSchema[]> {
  if (inflight) return inflight
  inflight = api
    .listProviders()
    .then(schemas => {
      cachedState = { status: 'ready', schemas, error: null }
      notify()
      return schemas
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to load providers'
      cachedState = { status: 'error', schemas: null, error: message }
      notify()
      // Allow a future retry by clearing the in-flight handle. Successful
      // results stay cached forever (until reload).
      inflight = null
      throw error
    })
  return inflight
}

/**
 * React hook returning the current provider-schema cache state. The first
 * caller in the session triggers one network request; subsequent callers
 * subscribe to the same cache and never re-fetch.
 */
export function useProviderSchema(): ProviderSchemaState {
  const [state, setState] = useState<ProviderSchemaState>(cachedState)

  useEffect(() => {
    listeners.add(setState)
    if (cachedState.status === 'loading' && inflight === null) {
      startFetch().catch(() => {
        // Errors propagate through ``cachedState.error``; swallow here
        // so React doesn't see an unhandled rejection.
      })
    } else {
      // Re-deliver the current cache to a late subscriber so it doesn't
      // stay stuck on its initial ``loading`` snapshot.
      setState(cachedState)
    }
    return () => {
      listeners.delete(setState)
    }
  }, [])

  return state
}

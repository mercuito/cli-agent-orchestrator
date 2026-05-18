import { useEffect, useState } from 'react'
import { api, ProviderCatalog } from '../api'

export interface ProviderCatalogState {
  status: 'idle' | 'loading' | 'ready' | 'error'
  catalog: ProviderCatalog | null
  error: string | null
}

const inflight = new Map<string, Promise<ProviderCatalog>>()

const idleState: ProviderCatalogState = {
  status: 'idle',
  catalog: null,
  error: null,
}

function startFetch(providerName: string): Promise<ProviderCatalog> {
  const existing = inflight.get(providerName)
  if (existing) return existing

  const request = api
    .getProviderCatalog(providerName)
    .finally(() => {
      inflight.delete(providerName)
    })
  inflight.set(providerName, request)
  return request
}

export function useProviderCatalog(
  providerName: string | null,
  enabled: boolean,
): ProviderCatalogState {
  const [state, setState] = useState<ProviderCatalogState>(() =>
    providerName && enabled
      ? { status: 'loading', catalog: null, error: null }
      : idleState,
  )

  useEffect(() => {
    if (!providerName || !enabled) {
      setState(idleState)
      return
    }

    let cancelled = false
    setState({
      status: 'loading',
      catalog: null,
      error: null,
    })

    startFetch(providerName)
      .then(catalog => {
        if (cancelled) return
        setState({
          status: 'ready',
          catalog,
          error: null,
        })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : 'Failed to load provider catalog'
        setState({
          status: 'error',
          catalog: null,
          error: message,
        })
      })

    return () => {
      cancelled = true
    }
  }, [enabled, providerName])

  return state
}

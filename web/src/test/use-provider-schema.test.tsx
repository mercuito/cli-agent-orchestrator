import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import type { ProviderSchema } from '../api'

const SAMPLE_SCHEMAS: ProviderSchema[] = [
  {
    name: 'claude_code',
    binary: 'claude',
    installed: true,
    model_catalog_available: true,
  },
  {
    name: 'codex',
    binary: 'codex',
    installed: true,
    model_catalog_available: true,
  },
]

/**
 * The hook keeps a module-level cache that lives for the lifetime of the
 * loaded JS — by design, since provider capability is a build-time
 * property. Tests use ``vi.resetModules`` so each scenario starts with a
 * fresh cache without exposing a test-only reset on the module surface.
 */
async function loadFreshHook() {
  vi.resetModules()
  return await import('../hooks/useProviderSchema')
}

describe('useProviderSchema', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders loading until the network call resolves', async () => {
    const { useProviderSchema } = await loadFreshHook()
    const { api } = await import('../api')
    const listProviders = vi
      .spyOn(api, 'listProviders')
      .mockResolvedValueOnce(SAMPLE_SCHEMAS)

    const { result } = renderHook(() => useProviderSchema())

    expect(result.current.status).toBe('loading')

    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current.schemas).toEqual(SAMPLE_SCHEMAS)
    expect(listProviders).toHaveBeenCalledTimes(1)
  })

  it('reuses one in-flight fetch across multiple consumers', async () => {
    const { useProviderSchema } = await loadFreshHook()
    const { api } = await import('../api')
    const listProviders = vi
      .spyOn(api, 'listProviders')
      .mockResolvedValueOnce(SAMPLE_SCHEMAS)

    const first = renderHook(() => useProviderSchema())
    const second = renderHook(() => useProviderSchema())

    await waitFor(() => expect(first.result.current.status).toBe('ready'))
    await waitFor(() => expect(second.result.current.status).toBe('ready'))

    expect(first.result.current.schemas).toEqual(SAMPLE_SCHEMAS)
    expect(second.result.current.schemas).toEqual(SAMPLE_SCHEMAS)
    // Only one network call happened — the second consumer subscribed
    // to the same in-flight promise.
    expect(listProviders).toHaveBeenCalledTimes(1)
  })

  it('reuses the resolved cache for a later consumer without re-fetching', async () => {
    const { useProviderSchema } = await loadFreshHook()
    const { api } = await import('../api')
    const listProviders = vi
      .spyOn(api, 'listProviders')
      .mockResolvedValueOnce(SAMPLE_SCHEMAS)

    const first = renderHook(() => useProviderSchema())
    await waitFor(() => expect(first.result.current.status).toBe('ready'))

    const second = renderHook(() => useProviderSchema())

    expect(second.result.current.status).toBe('ready')
    expect(second.result.current.schemas).toEqual(SAMPLE_SCHEMAS)
    expect(listProviders).toHaveBeenCalledTimes(1)
  })

  it('surfaces network errors in the hook state without throwing', async () => {
    const { useProviderSchema } = await loadFreshHook()
    const { api } = await import('../api')
    vi.spyOn(api, 'listProviders').mockRejectedValueOnce(
      new Error('500 Internal Server Error'),
    )

    const { result } = renderHook(() => useProviderSchema())

    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toContain('500 Internal Server Error')
    expect(result.current.schemas).toBeNull()
  })
})

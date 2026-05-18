import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import type { ProviderCatalog } from '../api'

const CLAUDE_CATALOG: ProviderCatalog = {
  provider_type: 'claude_code',
  models: [
    {
      id: 'claude-opus-4-7',
      display_name: 'Claude Opus 4.7',
      reasoning_efforts: ['low', 'medium', 'high', 'max'],
      thinking_supported: true,
      max_input_tokens: 200000,
      max_output_tokens: 64000,
    },
  ],
  discovered_at: '2026-05-17T10:00:00Z',
  source: 'anthropic-api',
}

async function loadFreshHook() {
  vi.resetModules()
  return await import('../hooks/useProviderCatalog')
}

describe('useProviderCatalog', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('stays idle when catalog loading is disabled', async () => {
    const { useProviderCatalog } = await loadFreshHook()
    const { api } = await import('../api')
    const getProviderCatalog = vi.spyOn(api, 'getProviderCatalog')

    const { result } = renderHook(() => useProviderCatalog('codex', false))

    expect(result.current.status).toBe('idle')
    expect(result.current.catalog).toBeNull()
    expect(getProviderCatalog).not.toHaveBeenCalled()
  })

  it('deduplicates one in-flight catalog request per provider', async () => {
    const { useProviderCatalog } = await loadFreshHook()
    const { api } = await import('../api')
    const getProviderCatalog = vi
      .spyOn(api, 'getProviderCatalog')
      .mockResolvedValueOnce(CLAUDE_CATALOG)

    const first = renderHook(() => useProviderCatalog('claude_code', true))
    const second = renderHook(() => useProviderCatalog('claude_code', true))

    await waitFor(() => expect(first.result.current.status).toBe('ready'))
    await waitFor(() => expect(second.result.current.status).toBe('ready'))

    expect(first.result.current.catalog).toEqual(CLAUDE_CATALOG)
    expect(second.result.current.catalog).toEqual(CLAUDE_CATALOG)
    expect(getProviderCatalog).toHaveBeenCalledTimes(1)
    expect(getProviderCatalog).toHaveBeenCalledWith('claude_code')
  })

  it('surfaces catalog errors through hook state', async () => {
    const { useProviderCatalog } = await loadFreshHook()
    const { api } = await import('../api')
    vi.spyOn(api, 'getProviderCatalog').mockRejectedValueOnce(
      new Error('503 credentials missing'),
    )

    const { result } = renderHook(() => useProviderCatalog('claude_code', true))

    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toContain('503 credentials missing')
    expect(result.current.catalog).toBeNull()
  })
})

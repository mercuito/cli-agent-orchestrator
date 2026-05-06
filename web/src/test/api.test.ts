import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api } from '../api'

describe('API wrapper', () => {
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  function mockResponse(data: unknown, status = 200) {
    mockFetch.mockResolvedValueOnce({
      ok: status >= 200 && status < 300,
      status,
      statusText: status === 200 ? 'OK' : 'Error',
      json: () => Promise.resolve(data),
    })
  }

  it('startMonitoring POSTs terminal_id + label', async () => {
    const session = {
      id: 's1', terminal_id: 't1', label: 'dashboard-123456',
      started_at: '2026-04-18T10:00:00', ended_at: null, status: 'active',
    }
    mockResponse(session, 201)
    const result = await api.startMonitoring('t1', 'dashboard-123456')
    expect(result).toEqual(session)
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('/monitoring/sessions')
    expect(opts.method).toBe('POST')
    expect(JSON.parse(opts.body)).toEqual({
      terminal_id: 't1',
      label: 'dashboard-123456',
    })
  })

  it('startMonitoring sends label: null when not provided', async () => {
    mockResponse({ id: 's1' }, 201)
    await api.startMonitoring('t1')
    const [, opts] = mockFetch.mock.calls[0]
    const body = JSON.parse(opts.body)
    expect(body).toEqual({ terminal_id: 't1', label: null })
  })

  it('endMonitoring POSTs to /end endpoint', async () => {
    const ended = { id: 's1', ended_at: '2026-04-18T10:05:00', status: 'ended' }
    mockResponse(ended)
    const result = await api.endMonitoring('s1')
    expect(result).toEqual(ended)
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('/monitoring/sessions/s1/end')
    expect(opts.method).toBe('POST')
  })

  it('listActiveMonitoringSessions fetches active-scoped endpoint', async () => {
    const sessions = [
      { id: 's1', terminal_id: 't1', label: null, started_at: '2026-04-18T10:00:00', ended_at: null, status: 'active' },
    ]
    mockResponse(sessions)
    const result = await api.listActiveMonitoringSessions()
    expect(result).toEqual(sessions)
    // Must scope to status=active so the client only sees currently-monitored agents
    expect(mockFetch).toHaveBeenCalledWith(
      '/monitoring/sessions?status=active',
      expect.any(Object)
    )
  })

  it('listActiveBatons fetches the active baton list', async () => {
    const batons = [
      {
        id: 'baton-1',
        title: 'Review implementation',
        status: 'active',
        originator_id: 'term-origin',
        current_holder_id: 'term-reviewer',
        return_stack: ['term-author'],
        expected_next_action: 'review the patch',
        created_at: '2026-05-04T10:00:00',
        updated_at: '2026-05-04T10:05:00',
        last_nudged_at: null,
        completed_at: null,
      },
    ]
    mockResponse(batons)
    const result = await api.listActiveBatons()
    expect(result).toEqual(batons)
    expect(mockFetch).toHaveBeenCalledWith('/batons', expect.any(Object))
  })

  it('getBaton fetches a baton by id', async () => {
    mockResponse({ id: 'baton-1', title: 'Review implementation' })
    const result = await api.getBaton('baton-1')
    expect(result.id).toBe('baton-1')
    expect(mockFetch).toHaveBeenCalledWith('/batons/baton-1', expect.any(Object))
  })

  it('listBatonEvents fetches baton audit events', async () => {
    const events = [
      {
        event_type: 'passed',
        actor_id: 'term-author',
        from_holder_id: 'term-author',
        to_holder_id: 'term-reviewer',
        message: 'Please review',
        created_at: '2026-05-04T10:05:00',
      },
    ]
    mockResponse(events)
    const result = await api.listBatonEvents('baton-1')
    expect(result).toEqual(events)
    expect(mockFetch).toHaveBeenCalledWith('/batons/baton-1/events', expect.any(Object))
  })

  it('listSessions fetches /sessions', async () => {
    const sessions = [{ id: 's1', name: 'test', status: 'active' }]
    mockResponse(sessions)
    const result = await api.listSessions()
    expect(result).toEqual(sessions)
    expect(mockFetch).toHaveBeenCalledWith('/sessions', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })

  it('listProfiles fetches /agents/profiles', async () => {
    const profiles = [{ name: 'dev', description: 'Developer', source: 'built-in' }]
    mockResponse(profiles)
    const result = await api.listProfiles()
    expect(result).toEqual(profiles)
  })

  it('listProviders fetches /agents/providers', async () => {
    const providers = [{ name: 'kiro_cli', binary: 'kiro-cli', installed: true }]
    mockResponse(providers)
    const result = await api.listProviders()
    expect(result).toEqual(providers)
  })

  it('createSession sends POST with params', async () => {
    const terminal = { id: 't1', name: 'dev', provider: 'kiro_cli', session_name: 's1' }
    mockResponse(terminal)
    await api.createSession('kiro_cli', 'developer')
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/sessions?provider=kiro_cli&agent_profile=developer'),
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('createSession includes working directory when provided', async () => {
    mockResponse({ id: 't1' })
    await api.createSession('kiro_cli', 'developer', undefined, '/home/user/project')
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('working_directory='),
      expect.any(Object)
    )
  })

  it('getTerminal fetches terminal metadata', async () => {
    const terminal = {
      id: 't1',
      name: 't1',
      provider: 'codex',
      session_name: 'cao-linear-discovery-partner',
      agent_profile: 'discovery_partner',
    }
    mockResponse(terminal)
    const result = await api.getTerminal('t1')
    expect(result).toEqual(terminal)
    expect(mockFetch).toHaveBeenCalledWith('/terminals/t1', expect.any(Object))
  })

  it('getAgentRuntimeTerminal includes agent dashboard token when provided', async () => {
    mockResponse({ terminal: { id: 't1' }, terminal_token: 'terminal-token' })

    await api.getAgentRuntimeTerminal('discovery_partner', 'agent-token')

    expect(mockFetch).toHaveBeenCalledWith(
      '/agents/runtime/discovery_partner/terminal?agent_token=agent-token',
      expect.any(Object),
    )
  })

  it('deleteSession sends DELETE', async () => {
    mockResponse({ success: true, deleted: [], errors: [] })
    await api.deleteSession('s1')
    expect(mockFetch).toHaveBeenCalledWith('/sessions/s1', expect.objectContaining({ method: 'DELETE' }))
  })

  it('sendInput sends POST with message', async () => {
    mockResponse({ success: true })
    await api.sendInput('t1', 'hello')
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/terminals/t1/input?message=hello'),
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('getTerminalOutput fetches with mode', async () => {
    mockResponse({ output: 'test output', mode: 'last' })
    const result = await api.getTerminalOutput('t1', 'last')
    expect(result.output).toBe('test output')
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/terminals/t1/output?mode=last'),
      expect.any(Object)
    )
  })

  it('listFlows fetches /flows', async () => {
    const flows = [{ name: 'test-flow', schedule: '0 9 * * *', enabled: true }]
    mockResponse(flows)
    const result = await api.listFlows()
    expect(result).toEqual(flows)
  })

  it('createFlow sends POST with JSON body', async () => {
    const flow = { name: 'new-flow', schedule: '0 9 * * *', agent_profile: 'dev', prompt_template: 'Do stuff' }
    mockResponse(flow)
    await api.createFlow(flow)
    expect(mockFetch).toHaveBeenCalledWith(
      '/flows',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(flow),
      })
    )
  })

  it('enableFlow sends POST', async () => {
    mockResponse({ success: true })
    await api.enableFlow('my-flow')
    expect(mockFetch).toHaveBeenCalledWith('/flows/my-flow/enable', expect.objectContaining({ method: 'POST' }))
  })

  it('disableFlow sends POST', async () => {
    mockResponse({ success: true })
    await api.disableFlow('my-flow')
    expect(mockFetch).toHaveBeenCalledWith('/flows/my-flow/disable', expect.objectContaining({ method: 'POST' }))
  })

  it('runFlow sends POST with long timeout', async () => {
    mockResponse({ executed: true })
    await api.runFlow('my-flow')
    expect(mockFetch).toHaveBeenCalledWith('/flows/my-flow/run', expect.objectContaining({ method: 'POST' }))
  })

  it('deleteFlow sends DELETE', async () => {
    mockResponse({ success: true })
    await api.deleteFlow('my-flow')
    expect(mockFetch).toHaveBeenCalledWith('/flows/my-flow', expect.objectContaining({ method: 'DELETE' }))
  })

  it('throws on non-OK response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: () => Promise.resolve({}),
    })
    await expect(api.listSessions()).rejects.toThrow('500 Internal Server Error')
  })

  it('exitTerminal sends POST', async () => {
    mockResponse({ success: true })
    await api.exitTerminal('t1')
    expect(mockFetch).toHaveBeenCalledWith('/terminals/t1/exit', expect.objectContaining({ method: 'POST' }))
  })

  it('deleteTerminal sends DELETE', async () => {
    mockResponse({ success: true })
    await api.deleteTerminal('t1')
    expect(mockFetch).toHaveBeenCalledWith('/terminals/t1', expect.objectContaining({ method: 'DELETE' }))
  })
})

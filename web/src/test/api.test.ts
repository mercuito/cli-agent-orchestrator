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

  it('listAgents fetches the committed agent roster endpoint', async () => {
    const agents = [
      {
        agent_id: 'aria',
        display_name: 'Aria',
        cli_provider: 'codex',
        workdir: '/repo',
        session_name: 'aria-session',
        config: {
          id: 'aria',
          display_name: 'Aria',
          cli_provider: 'codex',
          workdir: '/repo',
          session_name: 'aria-session',
        },
        active: false,
        active_terminal_id: null,
        active_workspace_context_id: null,
        last_active_at: null,
      },
    ]
    mockResponse(agents)

    const result = await api.listAgents()

    expect(result).toEqual(agents)
    expect(mockFetch).toHaveBeenCalledWith('/agents', expect.any(Object))
  })

  it('createAgent POSTs durable agent config to /agents', async () => {
    const agent = {
      agent_id: 'new-agent',
      display_name: 'New Agent',
      cli_provider: 'codex',
      workdir: '/repo',
      session_name: 'new-agent',
      config: {},
      active: false,
      active_terminal_id: null,
      active_workspace_context_id: null,
      last_active_at: null,
    }
    mockResponse(agent, 201)

    const result = await api.createAgent({
      id: 'new-agent',
      display_name: 'New Agent',
      cli_provider: 'codex',
      workdir: '/repo',
    })

    expect(result).toEqual(agent)
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('/agents')
    expect(opts.method).toBe('POST')
    expect(JSON.parse(opts.body)).toEqual({
      id: 'new-agent',
      display_name: 'New Agent',
      cli_provider: 'codex',
      workdir: '/repo',
    })
  })

  it('updateAgent PUTs durable agent config to an encoded agent endpoint', async () => {
    const agent = {
      agent_id: 'linear/ops',
      display_name: 'Linear Ops',
      cli_provider: 'codex',
      workdir: '/repo',
      session_name: 'linear-ops',
      config: {},
      active: false,
      active_terminal_id: null,
      active_workspace_context_id: null,
      last_active_at: null,
    }
    mockResponse(agent)

    const result = await api.updateAgent('linear/ops', {
      display_name: 'Linear Ops',
      model: 'gpt-5.4',
    })

    expect(result).toEqual(agent)
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('/agents/linear%2Fops')
    expect(opts.method).toBe('PUT')
    expect(JSON.parse(opts.body)).toEqual({
      display_name: 'Linear Ops',
      model: 'gpt-5.4',
    })
  })

  it('updateAgent preserves server validation detail on failed responses', async () => {
    mockResponse({ detail: 'agents.aria.display_name must be a non-empty string' }, 400)

    await expect(api.updateAgent('aria', { display_name: '' })).rejects.toThrow(
      '400 Error: agents.aria.display_name must be a non-empty string',
    )
  })

  it('getAgentTimeline URL-encodes the selected agent id', async () => {
    const timeline = {
      agent: {
        agent_id: 'aria/linear',
        display_name: 'Aria',
        cli_provider: 'codex',
        workdir: '/repo',
        session_name: 'aria-session',
        config: {
          id: 'aria/linear',
          display_name: 'Aria',
          cli_provider: 'codex',
          workdir: '/repo',
          session_name: 'aria-session',
        },
        active: true,
        active_terminal_id: 'term-1',
        active_workspace_context_id: 'wctx-1',
        last_active_at: '2026-05-13T12:00:00',
      },
      events: [],
    }
    mockResponse(timeline)

    const result = await api.getAgentTimeline('aria/linear')

    expect(result).toEqual(timeline)
    expect(mockFetch).toHaveBeenCalledWith(
      '/agents/aria%2Flinear/timeline',
      expect.any(Object),
    )
  })

  it('getAgentRelatedEvents URL-encodes agent and event ids', async () => {
    const related = {
      event: {
        event_id: 'linear:agent_mentioned:event/1',
        event_name: 'agent_mentioned',
        event_type_key: 'LinearAgentMentionedEvent',
        source_type: 'linear',
        source_id: 'msg-1',
        occurred_at: '2026-05-13T12:00:00',
        correlation_id: 'thread-1',
        causation_id: null,
        event_data: {
          issue_identifier: 'CAO-96',
          message_body: 'Please implement CAO-96.',
        },
        participant_role: null,
      },
      correlation_events: [],
      causation_events: {
        direct_cause: null,
        direct_effects: [],
      },
    }
    mockResponse(related)

    const result = await api.getAgentRelatedEvents(
      'aria/linear',
      'linear:agent_mentioned:event/1',
    )

    expect(result).toEqual(related)
    expect(mockFetch).toHaveBeenCalledWith(
      '/agents/aria%2Flinear/events/linear%3Aagent_mentioned%3Aevent%2F1/related',
      expect.any(Object),
    )
  })

  it('getAgentTimeline preserves typed event data in returned rows', async () => {
    const timeline = {
      agent: {
        agent_id: 'aria',
        display_name: 'Aria',
        cli_provider: 'codex',
        workdir: '/repo',
        session_name: 'aria-session',
        config: {
          id: 'aria',
          display_name: 'Aria',
          cli_provider: 'codex',
          workdir: '/repo',
          session_name: 'aria-session',
        },
        active: true,
        active_terminal_id: 'term-1',
        active_workspace_context_id: 'wctx-1',
        last_active_at: '2026-05-13T12:00:00',
      },
      events: [
        {
          event_id: 'experimental:audit:event-1',
          event_name: 'experimental_audit_event',
          event_type_key: 'cao.experimental.AuditEvent',
          source_type: 'audit',
          source_id: 'audit-1',
          occurred_at: '2026-05-13T12:05:00',
          correlation_id: 'thread-audit',
          causation_id: null,
          event_data: {
            audit_kind: 'workspace_scan',
            confidence: 0.92,
          },
          participant_role: 'participant',
        },
      ],
    }
    mockResponse(timeline)

    const result = await api.getAgentTimeline('aria')

    expect(result.events[0].event_data).toEqual({
      audit_kind: 'workspace_scan',
      confidence: 0.92,
    })
  })

  it('getTerminal fetches terminal metadata', async () => {
    const terminal = {
      id: 't1',
      name: 't1',
      provider: 'codex',
      session_name: 'cao-linear-discovery-partner',
      agent_id: 'discovery_partner',
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
    const flow = { name: 'new-flow', schedule: '0 9 * * *', agent_id: 'dev', prompt_template: 'Do stuff' }
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

  it('listProviders fetches the provider capability schema', async () => {
    const schemas = [
      {
        name: 'claude_code',
        binary: 'claude',
        installed: true,
        supported_reasoning_efforts: ['low', 'medium', 'high'],
        suggested_models: ['claude-opus-4-7'],
      },
      {
        name: 'codex',
        binary: 'codex',
        installed: false,
        supported_reasoning_efforts: null,
        suggested_models: null,
      },
    ]
    mockResponse(schemas)

    const result = await api.listProviders()

    expect(result).toEqual(schemas)
    expect(mockFetch).toHaveBeenCalledWith('/providers', expect.any(Object))
  })
})

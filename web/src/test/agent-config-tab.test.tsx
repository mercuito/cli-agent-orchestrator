import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { AgentStatus, ProviderCatalog, ProviderSchema } from '../api'

const updateAgent = vi.hoisted(() => vi.fn())
const listProviders = vi.hoisted(() => vi.fn())
const getProviderCatalog = vi.hoisted(() => vi.fn())
const listWorkspaceTeams = vi.hoisted(() => vi.fn())

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    api: {
      updateAgent: (...args: unknown[]) => updateAgent(...args),
      listProviders: (...args: unknown[]) => listProviders(...args),
      getProviderCatalog: (...args: unknown[]) => getProviderCatalog(...args),
      listWorkspaceTeams: (...args: unknown[]) => listWorkspaceTeams(...args),
    },
  }
})

const SCHEMAS: ProviderSchema[] = [
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
  {
    name: 'q_cli',
    binary: 'q',
    installed: true,
    model_catalog_available: false,
  },
]

const CLAUDE_CATALOG: ProviderCatalog = {
  provider_type: 'claude_code',
  discovered_at: '2026-05-17T10:00:00Z',
  source: 'anthropic-api',
  models: [
    {
      id: 'claude-opus-4-7',
      display_name: 'Claude Opus 4.7',
      reasoning_efforts: ['low', 'medium', 'high', 'max'],
      thinking_supported: true,
      max_input_tokens: 200000,
      max_output_tokens: 64000,
    },
    {
      id: 'claude-sonnet-4-6',
      display_name: 'Claude Sonnet 4.6',
      reasoning_efforts: ['low', 'medium', 'high'],
      thinking_supported: true,
      max_input_tokens: 200000,
      max_output_tokens: 64000,
    },
  ],
}

function ariaStatus(overrides: Partial<AgentStatus['config']> = {}): AgentStatus {
  return {
    agent_id: 'aria',
    display_name: 'Aria',
    cli_provider: 'claude_code',
    workdir: '/repo',
    session_name: 'aria-session',
    config: {
      id: 'aria',
      display_name: 'Aria',
      cli_provider: 'claude_code',
      workdir: '/repo',
      session_name: 'aria-session',
      prompt: '# Agent\n',
      description: 'Works Linear issues',
      model: 'claude-opus-4-7',
      reasoning_effort: 'medium',
      mcp_servers: { cao: { command: 'cao-mcp-server' } },
      tools: ['bash'],
      tool_aliases: { shell: 'bash' },
      tools_settings: { bash: { timeout_ms: 1000 } },
      cao_tools: ['send_message'],
      skills: ['coding-discipline'],
      tags: [],
      resources: [],
      hooks: { post_start: ['echo ready'] },
      use_legacy_mcp_json: null,
      runtime_capabilities: null,
      codex_config: {},
      workspace: { team: null, derived_setup: null, diagnostics: [] },
      linear: {
        app_key: 'aria',
        client_id: 'linear-client',
        client_secret_configured: true,
        webhook_secret_configured: false,
        oauth_redirect_uri: 'https://cao.test/linear/oauth/callback',
        access_token_configured: true,
        refresh_token_configured: true,
        token_expires_at: null,
        app_user_id: 'linear-user',
        app_user_name: 'Linear Bot',
        oauth_state_configured: true,
        tool_access: [
          {
            access_id: 'workflow',
            tools: ['cao_linear.get_issue'],
            issues: ['CAO-1'],
            create_team_ids: ['TEAM'],
            create_project_ids: [],
            create_parent_issues: [],
            allow_top_level_create: false,
            update_fields: ['title'],
            reason: 'assigned work',
          },
        ],
      },
      ...overrides,
    },
    active: false,
    active_terminal_id: null,
    active_workspace_context_id: null,
    last_active_at: null,
  }
}

async function loadConfigTab() {
  // Fresh module each scenario so the provider-schema cache restarts.
  vi.resetModules()
  return await import('../components/agents-tab/AgentConfigTab')
}

async function loadDetailPanel() {
  return await import('../components/agents-tab/AgentDetailPanel')
}

beforeEach(() => {
  vi.resetModules()
  listProviders.mockReset()
  getProviderCatalog.mockReset()
  updateAgent.mockReset()
  listWorkspaceTeams.mockReset()
  listProviders.mockResolvedValue(SCHEMAS)
  getProviderCatalog.mockResolvedValue(CLAUDE_CATALOG)
  listWorkspaceTeams.mockResolvedValue([
    {
      id: 'cao_delivery',
      display_name: 'CAO Delivery',
      workspace_setup: 'linear_delivery_setup',
      members: ['aria'],
      diagnostics: [],
    },
    {
      id: 'research',
      display_name: 'Research',
      workspace_setup: 'research_setup',
      members: [],
      diagnostics: [],
    },
  ])
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('AgentConfigTab', () => {
  it('shows loading until the provider schema resolves', async () => {
    let resolveProviders: (value: ProviderSchema[]) => void = () => {}
    listProviders.mockReturnValueOnce(
      new Promise<ProviderSchema[]>(resolve => {
        resolveProviders = resolve
      }),
    )
    const { AgentConfigTab } = await loadConfigTab()

    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    expect(screen.getByText(/loading provider schema/i)).toBeInTheDocument()

    resolveProviders(SCHEMAS)

    await waitFor(() =>
      expect(screen.queryByText(/loading provider schema/i)).not.toBeInTheDocument(),
    )
  })

  it('renders structured field values, raw TOML, prompt, and Linear secrets in read mode', async () => {
    const { AgentConfigTab } = await loadConfigTab()

    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    await screen.findByRole('button', { name: /edit aria/i })

    // Structured field values rendered as labeled text.
    const structuredSection = screen.getByRole('region', { name: /structured fields/i })
    expect(structuredSection).toHaveTextContent('Aria')
    expect(structuredSection).toHaveTextContent('claude_code')
    expect(structuredSection).toHaveTextContent('claude-opus-4-7')
    expect(structuredSection).toHaveTextContent('medium')

    // Raw TOML preserves workdir and session_name (escape-hatch fields).
    expect(screen.getByText(/workdir = "\/repo"/)).toBeInTheDocument()
    expect(screen.getByText(/session_name = "aria-session"/)).toBeInTheDocument()
    expect(screen.getByText(/\[mcp_servers.cao\]/)).toBeInTheDocument()

    // Prompt and Linear secrets summary still render.
    expect(screen.getByText('# Agent')).toBeInTheDocument()
    expect(screen.getByText(/\[linear\]/)).toBeInTheDocument()
    expect(screen.getAllByText('••••••••').length).toBeGreaterThan(0)
    expect(screen.getByText(/Access token: Managed by OAuth callback/)).toBeInTheDocument()
  })

  it('updates the read-only derived setup field from the selected team while editing', async () => {
    const { AgentConfigTab } = await loadConfigTab()

    render(
      <AgentConfigTab
        agent={ariaStatus({ workspace: { team: 'cao_delivery', derived_setup: 'linear_delivery_setup', diagnostics: [] } })}
        onAgentUpdated={vi.fn()}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
    const setupInput = screen.getByLabelText('aria derived workspace setup') as HTMLInputElement

    expect(setupInput.value).toBe('linear_delivery_setup')
    expect(setupInput.disabled).toBe(true)

    fireEvent.change(screen.getByLabelText('aria workspace team'), {
      target: { value: 'research' },
    })

    expect(setupInput.value).toBe('research_setup')
    expect(setupInput.disabled).toBe(true)
  })

  it('flips structured fields into inputs and dropdowns in edit mode', async () => {
    const { AgentConfigTab } = await loadConfigTab()

    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))

    expect(screen.getByLabelText('aria display_name')).toHaveValue('Aria')
    expect(screen.getByLabelText('aria description')).toHaveValue('Works Linear issues')
    const providerSelect = screen.getByLabelText('aria cli_provider') as HTMLSelectElement
    expect(providerSelect.value).toBe('claude_code')
    expect(Array.from(providerSelect.options).map(option => option.value)).toEqual([
      'claude_code',
      'codex',
      'q_cli',
    ])
    const modelSelect = screen.getByLabelText('aria model') as HTMLSelectElement
    expect(modelSelect.tagName).toBe('SELECT')
    expect(modelSelect).toHaveValue('claude-opus-4-7')
    await waitFor(() => expect(getProviderCatalog).toHaveBeenCalledWith('claude_code'))
    expect(Array.from(modelSelect.options).map(option => option.value)).toEqual([
      '',
      'claude-opus-4-7',
      'claude-sonnet-4-6',
    ])
    const effortSelect = screen.getByLabelText('aria reasoning_effort') as HTMLSelectElement
    expect(effortSelect.value).toBe('medium')
    expect(Array.from(effortSelect.options).map(option => option.value)).toEqual([
      '',
      'low',
      'medium',
      'high',
      'max',
    ])
    expect(effortSelect.disabled).toBe(false)
  })

  it('disables model and reasoning_effort with tooltips when the selected provider has no catalog', async () => {
    const { AgentConfigTab } = await loadConfigTab()

    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
    fireEvent.change(screen.getByLabelText('aria cli_provider'), {
      target: { value: 'q_cli' },
    })

    const modelSelect = screen.getByLabelText('aria model') as HTMLSelectElement
    expect(modelSelect.disabled).toBe(true)
    expect(modelSelect).toHaveAttribute(
      'title',
      'q_cli has no loaded model catalog with model options',
    )

    const effortSelect = screen.getByLabelText('aria reasoning_effort') as HTMLSelectElement
    expect(effortSelect.disabled).toBe(true)
    expect(effortSelect).toHaveAttribute(
      'title',
      'q_cli has no loaded model catalog with reasoning_effort options',
    )
  })

  it('refreshes reasoning_effort options when the selected model changes', async () => {
    const { AgentConfigTab } = await loadConfigTab()

    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
    await waitFor(() => expect(getProviderCatalog).toHaveBeenCalledWith('claude_code'))

    fireEvent.change(screen.getByLabelText('aria model'), {
      target: { value: 'claude-sonnet-4-6' },
    })

    const effortSelect = screen.getByLabelText('aria reasoning_effort') as HTMLSelectElement
    expect(effortSelect.value).toBe('medium')
    expect(Array.from(effortSelect.options).map(option => option.value)).toEqual([
      '',
      'low',
      'medium',
      'high',
    ])
  })

  it('clears reasoning_effort when the selected model does not support the current value', async () => {
    const updated: AgentStatus = ariaStatus({
      model: 'claude-sonnet-4-6',
      reasoning_effort: null,
    })
    updateAgent.mockResolvedValueOnce(updated)
    const { AgentConfigTab } = await loadConfigTab()

    render(
      <AgentConfigTab
        agent={ariaStatus({ reasoning_effort: 'max' })}
        onAgentUpdated={vi.fn()}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
    await waitFor(() => expect(getProviderCatalog).toHaveBeenCalledWith('claude_code'))

    fireEvent.change(screen.getByLabelText('aria model'), {
      target: { value: 'claude-sonnet-4-6' },
    })

    const effortSelect = screen.getByLabelText('aria reasoning_effort') as HTMLSelectElement
    expect(effortSelect.value).toBe('')
    expect(Array.from(effortSelect.options).map(option => option.value)).toEqual([
      '',
      'low',
      'medium',
      'high',
    ])

    fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

    await waitFor(() => {
      expect(updateAgent).toHaveBeenCalledWith(
        'aria',
        expect.objectContaining({
          model: 'claude-sonnet-4-6',
          reasoning_effort: null,
        }),
      )
    })
  })

  it('does not keep an unsupported saved reasoning_effort for the selected model', async () => {
    const updated: AgentStatus = ariaStatus({
      model: 'claude-sonnet-4-6',
      reasoning_effort: null,
    })
    updateAgent.mockResolvedValueOnce(updated)
    const { AgentConfigTab } = await loadConfigTab()

    render(
      <AgentConfigTab
        agent={ariaStatus({
          model: 'claude-sonnet-4-6',
          reasoning_effort: 'max',
        })}
        onAgentUpdated={vi.fn()}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
    await waitFor(() => expect(getProviderCatalog).toHaveBeenCalledWith('claude_code'))

    const effortSelect = screen.getByLabelText('aria reasoning_effort') as HTMLSelectElement
    await waitFor(() => expect(effortSelect.value).toBe(''))
    expect(Array.from(effortSelect.options).map(option => option.value)).toEqual([
      '',
      'low',
      'medium',
      'high',
    ])

    fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

    await waitFor(() => {
      expect(updateAgent).toHaveBeenCalledWith(
        'aria',
        expect.objectContaining({
          model: 'claude-sonnet-4-6',
          reasoning_effort: null,
        }),
      )
    })
  })

  it('saves the structured form values merged with the raw TOML and prompt', async () => {
    const updated: AgentStatus = ariaStatus({ model: 'claude-sonnet-4-6' })
    updateAgent.mockResolvedValueOnce(updated)
    const onUpdated = vi.fn()
    const { AgentConfigTab } = await loadConfigTab()

    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={onUpdated} />)

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
    fireEvent.change(screen.getByLabelText('aria model'), {
      target: { value: 'claude-sonnet-4-6' },
    })
    fireEvent.change(screen.getByLabelText('aria prompt.md'), {
      target: { value: '# Updated\n' },
    })

    fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

    await waitFor(() => {
      expect(updateAgent).toHaveBeenCalledWith(
        'aria',
        expect.objectContaining({
          display_name: 'Aria',
          cli_provider: 'claude_code',
          model: 'claude-sonnet-4-6',
          reasoning_effort: 'medium',
          prompt: '# Updated\n',
        }),
      )
    })
    expect(onUpdated).toHaveBeenCalledWith(updated)
  })

  it('clears reasoning_effort when the selected provider does not support it', async () => {
    // ``q_cli`` is the example non-supporting provider (audited launch path
    // does not consume ``reasoning_effort``).
    const updated: AgentStatus = ariaStatus({
      cli_provider: 'q_cli',
      reasoning_effort: null,
    })
    updateAgent.mockResolvedValueOnce(updated)
    const { AgentConfigTab } = await loadConfigTab()

    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
    fireEvent.change(screen.getByLabelText('aria cli_provider'), {
      target: { value: 'q_cli' },
    })
    fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

    await waitFor(() => {
      expect(updateAgent).toHaveBeenCalledWith(
        'aria',
        expect.objectContaining({
          cli_provider: 'q_cli',
          reasoning_effort: null,
        }),
      )
    })
  })

  it('surfaces server validation errors inline and via onSaveError', async () => {
    updateAgent.mockRejectedValueOnce(
      new Error(
        '400 Bad Request: agents.aria.reasoning_effort is set to \'ultra\' but provider \'claude_code\' only supports [\'low\', \'medium\', \'high\']',
      ),
    )
    const onSaveError = vi.fn()
    const { AgentConfigTab } = await loadConfigTab()

    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} onSaveError={onSaveError} />)

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
    fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

    // The error message contains "reasoning_effort", so the row for
    // that field renders the alert.
    const alerts = await screen.findAllByRole('alert')
    expect(alerts.some(node => node.textContent?.includes('reasoning_effort'))).toBe(true)
    expect(onSaveError).toHaveBeenCalledWith(expect.stringContaining('reasoning_effort'))
  })

  it('renders an error state if the provider schema fails to load', async () => {
    listProviders.mockReset()
    listProviders.mockRejectedValueOnce(new Error('500 Internal Server Error'))
    const { AgentConfigTab } = await loadConfigTab()

    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/500 Internal Server Error/)
  })

  it('discards in-progress edit drafts when the selected agent changes', async () => {
    const { AgentConfigTab } = await loadConfigTab()

    const agent = ariaStatus()
    const { rerender } = render(<AgentConfigTab agent={agent} onAgentUpdated={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
    expect(screen.getByLabelText('aria display_name')).toBeInTheDocument()

    const cael: AgentStatus = { ...agent, agent_id: 'cael', display_name: 'Cael' }
    rerender(<AgentConfigTab agent={cael} onAgentUpdated={vi.fn()} />)

    expect(screen.queryByLabelText('aria display_name')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('cael display_name')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit cael/i })).toBeInTheDocument()
  })

  it('is wired into the AgentDetailPanel Config slot via the render prop seam', async () => {
    const { AgentConfigTab } = await loadConfigTab()
    const { AgentDetailPanel } = await loadDetailPanel()

    render(
      <AgentDetailPanel
        agent={ariaStatus()}
        onStartAgent={vi.fn()}
        onOpenTerminal={vi.fn()}
        onStopAgent={vi.fn()}
        renderConfigTab={a => <AgentConfigTab agent={a} onAgentUpdated={vi.fn()} />}
        renderTimelineTab={() => <div data-testid="timeline-tab" />}
      />,
    )

    expect(await screen.findByRole('button', { name: /edit aria/i })).toBeInTheDocument()
  })
})

describe('AgentConfigTab raw TOML disclosure', () => {
  it('renders the raw TOML inside a collapsible disclosure that defaults to collapsed', async () => {
    const { AgentConfigTab } = await loadConfigTab()
    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    await screen.findByRole('button', { name: /edit aria/i })

    const summary = screen.getByText(/raw agent.toml/i)
    const disclosure = summary.closest('details')
    expect(disclosure).not.toBeNull()
    expect(disclosure?.open).toBe(false)
  })

  it('omits structured-form keys and id from the raw textarea in edit mode', async () => {
    const { AgentConfigTab } = await loadConfigTab()
    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))

    const textarea = screen.getByLabelText('aria agent.toml') as HTMLTextAreaElement
    const text = textarea.value
    // ``id`` is owned by the directory name; structured-form keys are
    // owned by the structured form. Editing them in raw would either
    // corrupt the save (id) or double-edit them with the structured
    // form (display_name, cli_provider, model, description,
    // reasoning_effort), so the raw textarea hides those keys.
    expect(text).not.toMatch(/^id\s*=/m)
    expect(text).not.toMatch(/^display_name\s*=/m)
    expect(text).not.toMatch(/^cli_provider\s*=/m)
    expect(text).not.toMatch(/^description\s*=/m)
    expect(text).not.toMatch(/^model\s*=/m)
    expect(text).not.toMatch(/^reasoning_effort\s*=/m)
    // ``workdir`` and ``session_name`` REMAIN as escape-hatch fields.
    expect(text).toMatch(/workdir\s*=/)
    expect(text).toMatch(/session_name\s*=/)
  })

  it('save merges structured + raw cleanly with no dropped or duplicated keys', async () => {
    updateAgent.mockResolvedValueOnce(ariaStatus())
    const { AgentConfigTab } = await loadConfigTab()
    render(<AgentConfigTab agent={ariaStatus()} onAgentUpdated={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))

    // Edit a structured field (display_name) AND an unstructured field
    // (a tools entry in raw TOML) at the same time.
    fireEvent.change(screen.getByLabelText('aria display_name'), {
      target: { value: 'Aria Renamed' },
    })
    const textarea = screen.getByLabelText('aria agent.toml') as HTMLTextAreaElement
    fireEvent.change(textarea, {
      target: { value: textarea.value.replace('tools = ["bash"]', 'tools = ["bash", "edit"]') },
    })

    fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

    await waitFor(() => expect(updateAgent).toHaveBeenCalled())
    const [, body] = updateAgent.mock.calls[0]
    expect(body.display_name).toBe('Aria Renamed')
    expect(body.tools).toEqual(['bash', 'edit'])
    // ``id`` was excluded from the raw textarea, so the save body must
    // not carry it either.
    expect('id' in body).toBe(false)
  })
})

describe('AgentDetailPanel header', () => {
  it('exposes id and workdir in the read-only header area', async () => {
    const { AgentDetailPanel } = await loadDetailPanel()

    render(
      <AgentDetailPanel
        agent={ariaStatus()}
        onStartAgent={vi.fn()}
        onOpenTerminal={vi.fn()}
        onStopAgent={vi.fn()}
        renderConfigTab={() => <div />}
        renderTimelineTab={() => <div />}
      />,
    )

    // ``id`` and ``workdir`` are the immutable identity context; the
    // header surfaces them so the operator always knows which agent
    // and project they're configuring.
    expect(screen.getByText('aria')).toBeInTheDocument()
    expect(screen.getByText('/repo')).toBeInTheDocument()
    expect(screen.queryByText('aria-session')).not.toBeInTheDocument()
  })
})

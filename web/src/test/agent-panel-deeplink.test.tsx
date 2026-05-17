import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { AgentPanel } from '../components/AgentPanel'
import { AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT } from '../generated/caoEventPayloadTypes'

const terminalViewMock = vi.hoisted(() => vi.fn(() => <div data-testid="terminal-view" />))
const selectSession = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const showSnackbar = vi.hoisted(() => vi.fn())
const storeState = vi.hoisted(() => ({
  sessions: [] as Array<{ id: string; name: string; status: string }>,
  activeSession: null as string | null,
  activeSessionDetail: null as any,
}))
const agentStatus = vi.hoisted(() => (agentId: string, displayName: string) => ({
  agent_id: agentId,
  display_name: displayName,
  cli_provider: 'codex',
  workdir: '/repo',
  session_name: `${agentId}-session`,
  config: {
    id: agentId,
    display_name: displayName,
    cli_provider: 'codex',
    workdir: '/repo',
    session_name: `${agentId}-session`,
    prompt: '# Agent\n',
    description: 'Works Linear issues',
    model: 'gpt-5.2',
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
    workspace_context: { enabled: false, resolver_id: null },
    linear: {
      app_key: agentId,
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
  },
  active: false,
  active_terminal_id: null,
  active_workspace_context_id: null,
  last_active_at: null,
}))
const getTerminal = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve({
      id: 'term-1',
      name: 'developer-1234',
      provider: 'codex',
      session_name: 'cao-linear-discovery-partner',
      agent_id: 'developer',
      status: 'idle',
      last_active: null,
    }),
  ),
)
const getAgentRuntimeTerminal = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve({
      terminal: {
        id: 'term-2',
        name: 'developer-5678',
        provider: 'codex',
        session_name: 'cao-linear-discovery-partner',
        agent_id: 'developer',
        status: 'idle',
        last_active: null,
      },
      terminal_token: 'runtime-token',
    }),
  ),
)
const listAgents = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve([
      agentStatus('aria', 'Aria'),
    ]),
  ),
)
const updateAgent = vi.hoisted(() =>
  vi.fn((agentId: string, body: any) =>
    Promise.resolve({
      ...agentStatus(agentId, body.display_name || 'Aria'),
      config: {
        ...agentStatus(agentId, body.display_name || 'Aria').config,
        ...body,
      },
    }),
  ),
)
const createAgent = vi.hoisted(() =>
  vi.fn((body: any) => Promise.resolve(agentStatus(body.id, body.display_name || body.id))),
)
const startAgent = vi.hoisted(() => vi.fn())
const stopAgent = vi.hoisted(() => vi.fn(() => Promise.resolve({ success: true })))
const getAgentTimeline = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve({
      agent: agentStatus('aria', 'Aria'),
      events: [
        {
          event_id: 'linear:agent_mentioned:mention',
          event_name: 'agent_mentioned',
          event_type_key: 'LinearAgentMentionedEvent',
          source_type: 'linear',
          source_id: 'msg-1',
          occurred_at: '2026-05-13T12:00:00',
          correlation_id: null,
          causation_id: null,
          event_data: {},
          participant_role: 'mentioned',
        },
      ],
    }),
  ),
)

vi.mock('../components/TerminalView', () => ({
  TerminalView: terminalViewMock,
}))

vi.mock('../api', () => ({
  api: {
    listProviders: vi.fn(() => Promise.resolve([{ name: 'codex', binary: 'codex', installed: true }])),
    listAgents,
    updateAgent,
    createAgent,
    startAgent,
    stopAgent,
    getAgentTimeline,
    getAgentRelatedEvents: vi.fn(() => Promise.resolve({
      event: null,
      correlation_events: [],
      causation_events: { direct_cause: null, direct_effects: [] },
    })),
    getTerminal,
    getAgentRuntimeTerminal,
    getTerminalStatus: vi.fn(() => Promise.resolve('idle')),
    getWorkingDirectory: vi.fn(() => Promise.resolve({ working_directory: null })),
    listActiveMonitoringSessions: vi.fn(() => Promise.resolve([])),
    listActiveBatons: vi.fn(() => Promise.resolve([])),
  },
}))

vi.mock('../store', () => ({
  useStore: vi.fn((selector?: (state: any) => any) => {
    const state = {
      sessions: storeState.sessions,
      fetchSessions: vi.fn(),
      activeSession: storeState.activeSession,
      activeSessionDetail: storeState.activeSessionDetail,
      selectSession,
      createSession: vi.fn(),
      deleteSession: vi.fn(),
      terminalStatuses: {},
      activeMonitoringByTerminal: {},
      activeBatonsByHolder: {},
      setTerminalStatus: vi.fn(),
      setActiveMonitoringSessions: vi.fn(),
      setActiveBatons: vi.fn(),
      showSnackbar,
    }
    return selector ? selector(state) : state
  }),
}))

describe('AgentPanel', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    listAgents.mockImplementation(() => Promise.resolve([agentStatus('aria', 'Aria')]))
    storeState.sessions = []
    storeState.activeSession = null
    storeState.activeSessionDetail = null
  })

  describe('agent timeline boundary', () => {
    it('renders the agent timeline panel through the Agents panel Timeline tab', async () => {
      render(<AgentPanel />)

      expect((await screen.findAllByRole('button', { name: /aria/i })).length).toBeGreaterThan(0)
      fireEvent.click(screen.getByRole('tab', { name: 'Timeline' }))

      expect(await screen.findByTestId('agent-timeline')).toBeInTheDocument()
      expect(screen.getByText('linear:agent_mentioned:mention')).toBeInTheDocument()
      expect(listAgents).toHaveBeenCalled()
      expect(getAgentTimeline).toHaveBeenCalledWith('aria')
    })
  })

  describe('unified detail panel layout', () => {
    it('selecting an agent in the roster updates the detail panel for that agent', async () => {
      // Given
      listAgents.mockResolvedValue([
        agentStatus('aria', 'Aria'),
        agentStatus('cael', 'Cael'),
      ] as any)
      render(<AgentPanel />)
      await screen.findByRole('heading', { name: 'Aria' })

      // When
      fireEvent.click(screen.getByRole('button', { name: /cael/i }))

      // Then
      expect(await screen.findByRole('heading', { name: 'Cael' })).toBeInTheDocument()
    })

    it('switching tabs preserves the agent selection', async () => {
      // Given
      render(<AgentPanel />)
      await screen.findByRole('heading', { name: 'Aria' })

      // When
      fireEvent.click(screen.getByRole('tab', { name: 'Timeline' }))

      // Then
      expect(await screen.findByTestId('agent-timeline')).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Aria' })).toBeInTheDocument()
    })

    it('switching agents preserves the active tab', async () => {
      // Given
      listAgents.mockResolvedValue([
        agentStatus('aria', 'Aria'),
        agentStatus('cael', 'Cael'),
      ] as any)
      render(<AgentPanel />)
      await screen.findByRole('heading', { name: 'Aria' })
      fireEvent.click(screen.getByRole('tab', { name: 'Timeline' }))
      await screen.findByTestId('agent-timeline')

      // When
      fireEvent.click(screen.getByRole('button', { name: /cael/i }))

      // Then
      await waitFor(() => {
        expect(getAgentTimeline).toHaveBeenCalledWith('cael')
      })
      expect(screen.getByRole('tab', { name: 'Timeline' })).toHaveAttribute('aria-selected', 'true')
    })

    it('renders exactly one Agents roster on the page', async () => {
      // Given / When
      render(<AgentPanel />)
      await screen.findByRole('heading', { name: 'Aria' })

      // Then
      expect(screen.getAllByRole('heading', { name: /Agents \(\d+\)/ })).toHaveLength(1)
    })

    it('stops a running agent through api.stopAgent and refreshes the roster', async () => {
      // Given
      listAgents
        .mockResolvedValueOnce([
          { ...agentStatus('aria', 'Aria'), active: true, active_terminal_id: 'term-live' } as any,
        ])
        .mockResolvedValue([agentStatus('aria', 'Aria')] as any)
      render(<AgentPanel />)
      await screen.findByRole('heading', { name: 'Aria' })

      // When
      fireEvent.click(screen.getByRole('button', { name: /stop aria/i }))

      // Then
      await waitFor(() => {
        expect(stopAgent).toHaveBeenCalledWith('aria')
      })
    })
  })

  describe('durable agent configuration', () => {
    it('renders the selected agent status and full agent.toml fields inline', async () => {
      render(<AgentPanel />)

      expect(await screen.findByRole('heading', { name: /agent.toml/i })).toBeInTheDocument()
      expect(screen.getAllByText('Stopped').length).toBeGreaterThan(0)
      expect(screen.getByText(/workdir = "\/repo"/)).toBeInTheDocument()
      expect(screen.getByText(/session_name = "aria-session"/)).toBeInTheDocument()
      expect(screen.getByText(/cli_provider = "codex"/)).toBeInTheDocument()
      expect(screen.getByText(/model = "gpt-5.2"/)).toBeInTheDocument()
      expect(screen.getByText(/\[mcp_servers.cao\]/)).toBeInTheDocument()
      expect(screen.getByText(/tools = \["bash"\]/)).toBeInTheDocument()
      expect(screen.getByText(/tool_aliases = \{ shell = "bash" \}/)).toBeInTheDocument()
      expect(screen.getByText(/tools_settings = \{ bash = \{ timeout_ms = 1000 \} \}/)).toBeInTheDocument()
      expect(screen.getByText(/hooks = \{ post_start = \["echo ready"\] \}/)).toBeInTheDocument()
      expect(screen.getByText(/\[linear\]/)).toBeInTheDocument()
      expect(screen.getByText(/\[linear.tool_access.workflow\]/)).toBeInTheDocument()
      expect(screen.getByText('# Agent')).toBeInTheDocument()
      expect(screen.getAllByText('••••••••').length).toBeGreaterThan(0)
      expect(screen.getByText(/Access token: Managed by OAuth callback/)).toBeInTheDocument()
    })

    it('reveals configured Linear secret status without exposing token values', async () => {
      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('button', { name: /reveal client secret/i }))

      expect(screen.getByText('Configured on server')).toBeInTheDocument()
      expect(screen.getByText(/Refresh token: Managed by OAuth callback/)).toBeInTheDocument()
    })

    it('saves prompt, MCP, and tools edits through the durable agent update API', async () => {
      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
      const editor = screen.getByLabelText('aria agent.toml') as HTMLTextAreaElement
      fireEvent.change(editor, {
        target: {
          value: editor.value
            .replace('model = "gpt-5.2"', 'model = "gpt-5.4"')
            .replace('tools = ["bash"]', 'tools = ["bash", "apply_patch"]')
            .replace('command = "cao-mcp-server"', 'command = "cao-mcp-server"\nargs = ["--stdio"]'),
        },
      })
      fireEvent.change(screen.getByLabelText('aria prompt.md'), {
        target: { value: '# Updated Agent\nUse the MCP server.\n' },
      })
      fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

      await waitFor(() => {
        expect(updateAgent).toHaveBeenCalledWith('aria', expect.objectContaining({
          model: 'gpt-5.4',
          prompt: '# Updated Agent\nUse the MCP server.\n',
          tools: ['bash', 'apply_patch'],
          mcp_servers: {
            cao: {
              command: 'cao-mcp-server',
              args: ['--stdio'],
            },
          },
        }))
      })
      expect(await screen.findByText(/model = "gpt-5.4"/)).toBeInTheDocument()
      expect(screen.getByText(/tools = \["bash", "apply_patch"\]/)).toBeInTheDocument()
      expect(screen.getByText(/# Updated Agent/)).toBeInTheDocument()
    })

    it('saves Linear binding and tool-access edits through the durable agent update API', async () => {
      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
      const editor = screen.getByLabelText('aria agent.toml') as HTMLTextAreaElement
      fireEvent.change(editor, {
        target: {
          value: editor.value
            .replace('app_key = "aria"', 'app_key = "aria-prod"')
            .replace('issues = ["CAO-1"]', 'issues = ["CAO-2"]')
            .replace('reason = "assigned work"', 'reason = "reviewed access"'),
        },
      })
      fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

      await waitFor(() => {
        expect(updateAgent).toHaveBeenCalledWith('aria', expect.objectContaining({
          linear: expect.objectContaining({
            app_key: 'aria-prod',
            tool_access: [
              expect.objectContaining({
                access_id: 'workflow',
                issues: ['CAO-2'],
                reason: 'reviewed access',
              }),
            ],
          }),
        }))
      })
    })

    it('surfaces save failures inline against the editor', async () => {
      updateAgent.mockRejectedValueOnce(new Error('400 Bad Request: linear.tool_access.workflow.tools is required'))
      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('button', { name: /edit aria/i }))
      fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

      expect(await screen.findByRole('alert')).toHaveTextContent('linear.tool_access.workflow.tools is required')
      expect(showSnackbar).toHaveBeenCalledWith(expect.objectContaining({
        type: 'error',
        message: expect.stringContaining('linear.tool_access.workflow.tools is required'),
      }))
    })

    it('offers a separate create-agent entry in the spawn modal', async () => {
      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('button', { name: /spawn agent/i }))
      fireEvent.click(screen.getByRole('button', { name: /create new agent/i }))
      fireEvent.change(screen.getByLabelText('Agent ID'), { target: { value: 'new-agent' } })
      fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'New Agent' } })
      fireEvent.change(screen.getByLabelText('Workdir'), { target: { value: '/tmp/new-agent' } })
      fireEvent.click(screen.getByRole('button', { name: /create agent/i }))

      await waitFor(() => {
        expect(createAgent).toHaveBeenCalledWith(expect.objectContaining({
          id: 'new-agent',
          display_name: 'New Agent',
          cli_provider: 'codex',
          workdir: '/tmp/new-agent',
        }))
      })
      expect(await screen.findByLabelText('new-agent agent.toml')).toBeInTheDocument()
    })

    it('disables already-running agents in the spawn modal with the running terminal in the tooltip', async () => {
      listAgents.mockResolvedValue([
        {
          ...agentStatus('aria', 'Aria'),
          active: true,
          active_terminal_id: 'term-live',
        },
      ] as any)
      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('button', { name: /spawn agent/i }))
      const runningAgent = await screen.findByTitle('Already running: term-live')
      fireEvent.click(runningAgent)

      expect(runningAgent).toBeDisabled()
      expect(startAgent).not.toHaveBeenCalled()
    })
  })

  describe('terminal deep links', () => {
    it('passes the initial terminal token through to TerminalView', async () => {
      render(<AgentPanel initialTerminalId="term-1" initialTerminalToken="signed-token" />)

      await waitFor(() => {
        expect(terminalViewMock).toHaveBeenCalledWith(
          expect.objectContaining({
            terminalId: 'term-1',
            provider: 'codex',
            agentId: 'developer',
            terminalToken: 'signed-token',
          }),
          {},
        )
      })

      expect(getTerminal).toHaveBeenCalledWith('term-1')
      expect(selectSession).toHaveBeenCalledWith('cao-linear-discovery-partner')
    })

    it('resolves a durable agent deep link to the current terminal', async () => {
      render(<AgentPanel initialAgentId="discovery_partner" initialAgentToken="agent-token" />)

      await waitFor(() => {
        expect(terminalViewMock).toHaveBeenCalledWith(
          expect.objectContaining({
            terminalId: 'term-2',
            provider: 'codex',
            agentId: 'developer',
            terminalToken: 'runtime-token',
          }),
          {},
        )
      })

      expect(getAgentRuntimeTerminal).toHaveBeenCalledWith('discovery_partner', 'agent-token')
      expect(selectSession).toHaveBeenCalledWith('cao-linear-discovery-partner')
    })

    it('reports a consumed terminal deep link so parent tab remounts do not replay it', async () => {
      const onConsumed = vi.fn()

      render(
        <AgentPanel
          initialTerminalId="term-1"
          initialTerminalToken="signed-token"
          onInitialDeepLinkConsumed={onConsumed}
        />,
      )

      await waitFor(() => {
        expect(onConsumed).toHaveBeenCalledTimes(1)
      })
      expect(getTerminal).toHaveBeenCalledWith('term-1')
    })

    it('passes the session terminal token through when opening a listed terminal', async () => {
      storeState.activeSession = 'cao-linear-smoke-tester'
      storeState.activeSessionDetail = {
        session: { id: 'cao-linear-smoke-tester', name: 'cao-linear-smoke-tester', status: 'active' },
        terminals: [
          {
            id: 'term-3',
            tmux_session: 'cao-linear-smoke-tester',
            tmux_window: '0',
            provider: 'codex',
            agent_id: 'linear_smoke_tester',
            terminal_token: 'session-terminal-token',
            last_active: null,
          },
        ],
      }

      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('button', { name: /open terminal/i }))

      await waitFor(() => {
        expect(terminalViewMock).toHaveBeenCalledWith(
          expect.objectContaining({
            terminalId: 'term-3',
            provider: 'codex',
            agentId: 'linear_smoke_tester',
            terminalToken: 'session-terminal-token',
          }),
          {},
        )
      })
    })

    it('focuses a runtime delivery terminal reference through the existing terminal open flow', async () => {
      getAgentTimeline.mockResolvedValueOnce({
        agent: agentStatus('aria', 'Aria'),
        events: [
          {
            event_id: 'runtime:event:delivery-ops-417',
            event_name: 'agent_runtime_notification_delivery',
            event_type_key: AGENT_RUNTIME_NOTIFICATION_DELIVERY_EVENT,
            source_type: 'cao_runtime',
            source_id: 'notification:42',
            occurred_at: '2026-05-13T12:01:00',
            correlation_id: null,
            causation_id: null,
            event_data: {
              source_kind: 'linear_mention',
              message_body: 'Aria, can you trace the stuck inbox delivery?',
              terminal_id: 'term-aria-main',
              outcome: 'delivered',
            },
            participant_role: 'delivery_target',
          },
        ],
      })
      getTerminal.mockResolvedValueOnce({
        id: 'term-aria-main',
        name: 'developer-aria',
        provider: 'codex',
        session_name: 'cao-linear-discovery-partner',
        agent_id: 'developer',
        status: 'idle',
        last_active: null,
      })

      render(<AgentPanel />)

      fireEvent.click(await screen.findByRole('tab', { name: 'Timeline' }))
      fireEvent.click(await screen.findByRole('button', { name: /open terminal term-aria-main/i }))

      await waitFor(() => {
        expect(terminalViewMock).toHaveBeenCalledWith(
          expect.objectContaining({
            terminalId: 'term-aria-main',
            provider: 'codex',
            agentId: 'developer',
          }),
          {},
        )
      })
      expect(getTerminal).toHaveBeenCalledWith('term-aria-main')
      expect(selectSession).toHaveBeenCalledWith('cao-linear-discovery-partner')
    })
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AgentConfigTab } from '../components/agents-tab/AgentConfigTab'
import { AgentDetailPanel } from '../components/agents-tab/AgentDetailPanel'
import type { AgentStatus } from '../api'

const updateAgent = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  api: {
    updateAgent: (...args: unknown[]) => updateAgent(...args),
  },
}))

function ariaStatus(): AgentStatus {
  return {
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
    },
    active: false,
    active_terminal_id: null,
    active_workspace_context_id: null,
    last_active_at: null,
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('AgentConfigTab', () => {
  it('renders the agent.toml view, prompt.md, and Linear secrets summary', () => {
    // Given
    const agent = ariaStatus()

    // When
    render(<AgentConfigTab agent={agent} onAgentUpdated={vi.fn()} />)

    // Then
    expect(screen.getByText(/workdir = "\/repo"/)).toBeInTheDocument()
    expect(screen.getByText(/model = "gpt-5.2"/)).toBeInTheDocument()
    expect(screen.getByText(/\[mcp_servers.cao\]/)).toBeInTheDocument()
    expect(screen.getByText(/\[linear\]/)).toBeInTheDocument()
    expect(screen.getByText('# Agent')).toBeInTheDocument()
    expect(screen.getAllByText('••••••••').length).toBeGreaterThan(0)
    expect(screen.getByText(/Access token: Managed by OAuth callback/)).toBeInTheDocument()
  })

  it('reveals Linear secret status without exposing token values', () => {
    // Given
    const agent = ariaStatus()
    render(<AgentConfigTab agent={agent} onAgentUpdated={vi.fn()} />)

    // When
    fireEvent.click(screen.getByRole('button', { name: /reveal client secret/i }))

    // Then
    expect(screen.getByText('Configured on server')).toBeInTheDocument()
  })

  it('saves edits through the public updateAgent API and reports the new status', async () => {
    // Given
    const agent = ariaStatus()
    const updatedAgent: AgentStatus = {
      ...agent,
      config: { ...agent.config, model: 'gpt-5.4' },
    }
    updateAgent.mockResolvedValueOnce(updatedAgent)
    const onUpdated = vi.fn()
    render(<AgentConfigTab agent={agent} onAgentUpdated={onUpdated} />)
    fireEvent.click(screen.getByRole('button', { name: /edit aria/i }))
    const editor = screen.getByLabelText('aria agent.toml') as HTMLTextAreaElement
    fireEvent.change(editor, {
      target: { value: editor.value.replace('model = "gpt-5.2"', 'model = "gpt-5.4"') },
    })
    fireEvent.change(screen.getByLabelText('aria prompt.md'), {
      target: { value: '# Updated\n' },
    })

    // When
    fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

    // Then
    await waitFor(() => {
      expect(updateAgent).toHaveBeenCalledWith(
        'aria',
        expect.objectContaining({ model: 'gpt-5.4', prompt: '# Updated\n' }),
      )
    })
    expect(onUpdated).toHaveBeenCalledWith(updatedAgent)
  })

  it('surfaces save failures inline against the editor and reports the message', async () => {
    // Given
    const agent = ariaStatus()
    updateAgent.mockRejectedValueOnce(new Error('400 Bad Request: linear.tool_access.workflow.tools is required'))
    const onSaveError = vi.fn()
    render(<AgentConfigTab agent={agent} onAgentUpdated={vi.fn()} onSaveError={onSaveError} />)
    fireEvent.click(screen.getByRole('button', { name: /edit aria/i }))

    // When
    fireEvent.click(screen.getByRole('button', { name: /save aria/i }))

    // Then
    expect(await screen.findByRole('alert')).toHaveTextContent('linear.tool_access.workflow.tools is required')
    expect(onSaveError).toHaveBeenCalledWith(expect.stringContaining('linear.tool_access.workflow.tools is required'))
  })

  it('discards in-progress edit drafts when the selected agent changes', () => {
    // Given
    const agent = ariaStatus()
    const { rerender } = render(<AgentConfigTab agent={agent} onAgentUpdated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /edit aria/i }))
    expect(screen.getByLabelText('aria agent.toml')).toBeInTheDocument()

    // When
    const cael: AgentStatus = { ...agent, agent_id: 'cael', display_name: 'Cael' }
    rerender(<AgentConfigTab agent={cael} onAgentUpdated={vi.fn()} />)

    // Then
    expect(screen.queryByLabelText('aria agent.toml')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('cael agent.toml')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit cael/i })).toBeInTheDocument()
  })

  it('is wired into the AgentDetailPanel Config slot via the render prop seam', () => {
    // Given
    const agent = ariaStatus()

    // When
    render(
      <AgentDetailPanel
        agent={agent}
        onStartAgent={vi.fn()}
        onStopAgent={vi.fn()}
        renderConfigTab={a => <AgentConfigTab agent={a} onAgentUpdated={vi.fn()} />}
        renderTimelineTab={() => <div data-testid="timeline-tab" />}
      />,
    )

    // Then
    expect(screen.getByRole('button', { name: /edit aria/i })).toBeInTheDocument()
    expect(screen.getByText(/\[linear\]/)).toBeInTheDocument()
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { AgentDetailPanel } from '../components/agents-tab/AgentDetailPanel'
import type { AgentStatus } from '../api'

function agentStatus(overrides: Partial<AgentStatus> = {}): AgentStatus {
  const agent_id = overrides.agent_id ?? 'aria'
  const display_name = overrides.display_name ?? 'Aria'
  return {
    agent_id,
    display_name,
    cli_provider: 'codex',
    workdir: '/repo',
    session_name: `${agent_id}-session`,
    config: {
      id: agent_id,
      display_name,
      cli_provider: 'codex',
      workdir: '/repo',
      session_name: `${agent_id}-session`,
      prompt: '# Agent\n',
      description: null,
      model: null,
      reasoning_effort: null,
      mcp_servers: {},
      tools: [],
      tool_aliases: {},
      tools_settings: {},
      cao_tools: null,
      skills: [],
      tags: [],
      resources: [],
      hooks: {},
      use_legacy_mcp_json: null,
      runtime_capabilities: null,
      codex_config: {},
      workspace: { team: null, derived_workspace: null, diagnostics: [] },
    },
    active: false,
    active_terminal_id: null,
    active_workspace_context_id: null,
    mcp_tool_surface: { schema_version: 'cao-agent-mcp-surface.v1', tools: [] },
    last_active_at: null,
    ...overrides,
  }
}

const renderConfigTab = vi.fn((agent: AgentStatus) => (
  <div data-testid="config-tab">config for {agent.agent_id}</div>
))
const renderTimelineTab = vi.fn((agent: AgentStatus) => (
  <div data-testid="timeline-tab">timeline for {agent.agent_id}</div>
))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('AgentDetailPanel', () => {
  describe('status header', () => {
    it('renders running agent header with terminal id, Open Terminal, and Stop buttons', () => {
      // Given
      const agent = agentStatus({
        active: true,
        active_terminal_id: 'term-aria-main',
        active_workspace_context_id: 'wctx_aria_default',
      })
      const onStart = vi.fn()
      const onOpenTerminal = vi.fn()
      const onStop = vi.fn()

      // When
      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={onStart}
          onOpenTerminal={onOpenTerminal}
          onStopAgent={onStop}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )

      // Then
      expect(screen.getByRole('heading', { name: 'Aria' })).toBeInTheDocument()
      expect(screen.getByText('aria')).toBeInTheDocument()
      expect(screen.getByText('Running')).toBeInTheDocument()
      expect(screen.getByText('term-aria-main')).toBeInTheDocument()
      expect(screen.getByText('wctx_aria_default')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /open terminal for aria/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /stop aria/i })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /start aria/i })).not.toBeInTheDocument()
    })

    it('opens the running agent terminal through the provided handler', () => {
      // Given
      const agent = agentStatus({
        active: true,
        active_terminal_id: 'term-aria-main',
      })
      const onOpenTerminal = vi.fn()

      // When
      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={vi.fn()}
          onOpenTerminal={onOpenTerminal}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )
      fireEvent.click(screen.getByRole('button', { name: /open terminal for aria/i }))

      // Then
      expect(onOpenTerminal).toHaveBeenCalledWith('aria')
    })

    it('renders actionable workspace diagnostics and hides pruning diagnostics', () => {
      render(
        <AgentDetailPanel
          agent={agentStatus({ derived_workspace_id: 'cao_delivery' })}
          workspaceDiagnostics={[
            {
              code: 'pruned_provider_identity',
              message: 'Workspace team cao_delivery pruned example tool access for discovery',
              team_id: 'cao_delivery',
              workspace_id: 'cao_default',
              agent_id: 'aria',
              provider_name: 'example',
            },
            {
              code: 'unavailable_provider',
              message: 'Workspace team cao_delivery workspace cao_default requires unavailable provider example',
              team_id: 'cao_delivery',
              workspace_id: 'cao_default',
              agent_id: null,
              provider_name: 'example',
            },
          ]}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )

      expect(screen.queryByText(/pruned example tool access/)).not.toBeInTheDocument()
      expect(screen.getByText(/requires unavailable provider example/)).toBeInTheDocument()
    })

    it('renders current MCP tool access as the primary available tools section', () => {
      // Given
      const agent = agentStatus({
        active: true,
        active_terminal_id: 'term-aria-main',
        mcp_tool_surface: {
          schema_version: 'cao-agent-mcp-surface.v1',
          tools: [
            {
              source: { kind: 'cao_builtin', name: 'cao' },
              name: 'send_message',
              description: 'Send a message to another CAO agent.',
            },
            {
              source: { kind: 'provider', name: 'example' },
              name: 'cao_example.get_item',
              description: 'Read an example work item.',
            },
          ],
        },
      })

      // When
      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )

      // Then
      expect(screen.getByText('Available tools')).toBeInTheDocument()
      expect(screen.queryByText('ToolService access')).not.toBeInTheDocument()
      expect(screen.queryByText('cao_example.get_item')).not.toBeInTheDocument()

      fireEvent.click(screen.getByText('Available tools'))

      expect(screen.getByText('send_message')).toBeInTheDocument()
      expect(screen.getByText('cao_example.get_item')).toBeInTheDocument()
      expect(screen.getByText('cao builtin / cao')).toBeInTheDocument()
      expect(screen.getByText('provider / example')).toBeInTheDocument()
      expect(screen.getByText(/running terminal may need a restart/i)).toBeInTheDocument()
      expect(screen.getByText(/managed by ToolService/i)).toBeInTheDocument()
    })

    it('does not treat a missing MCP tool surface as zero effective tools', () => {
      // Given
      const agent = agentStatus({
        mcp_tool_surface: undefined,
      })

      // When
      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )
      fireEvent.click(screen.getByText('Available tools'))

      // Then
      expect(screen.getByText('unavailable')).toBeInTheDocument()
      expect(screen.getByText(/tool access is unavailable/i)).toBeInTheDocument()
      expect(screen.queryByText('No MCP tools visible for this agent.')).not.toBeInTheDocument()
    })

    it('hides ToolService debug details when they match the visible MCP tools', () => {
      const agent = agentStatus({
        mcp_tool_surface: {
          schema_version: 'cao-agent-mcp-surface.v1',
          tools: [
            {
              source: { kind: 'cao_builtin', name: 'cao' },
              name: 'send_message',
              description: 'Send a message.',
            },
            {
              source: { kind: 'provider', name: 'example' },
              name: 'cao_example.get_item',
              description: 'Read an example work item.',
            },
          ],
        },
        effective_tool_access: {
          agent_id: 'aria',
          team_id: null,
          role_id: null,
          registered_tools: ['send_message', 'cao_example.get_item', '@cao-mcp-server'],
          allowed_tools: ['send_message', 'cao_example.get_item'],
          blocked_tools: [],
          built_in_cao_tools: ['send_message'],
          provider_mediated_tools: { example: ['cao_example.get_item'] },
          materialized_mcp_servers: { 'cao-mcp-server': {} },
          runtime_capabilities: ['fs_read', '@cao-mcp-server'],
          source_markers: {},
          inactive_local_grants: {},
          diagnostics: [],
        },
      })

      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )

      expect(screen.queryByText('Tool access details')).not.toBeInTheDocument()
    })

    it('renders ToolService debug details when they add diagnostic signal', () => {
      const agent = agentStatus({
        mcp_tool_surface: {
          schema_version: 'cao-agent-mcp-surface.v1',
          tools: [
            {
              source: { kind: 'cao_builtin', name: 'cao' },
              name: 'send_message',
              description: 'Send a message.',
            },
          ],
        },
        effective_tool_access: {
          agent_id: 'aria',
          team_id: null,
          role_id: null,
          registered_tools: ['send_message', 'cao_example.get_item', '@cao-mcp-server'],
          allowed_tools: ['send_message', 'cao_example.get_item'],
          blocked_tools: [],
          built_in_cao_tools: ['send_message'],
          provider_mediated_tools: { example: ['cao_example.get_item'] },
          materialized_mcp_servers: { 'cao-mcp-server': {} },
          runtime_capabilities: ['fs_read', '@cao-mcp-server'],
          source_markers: {
            send_message: 'agent_config:cao_tools',
            'cao_example.get_item': 'example:tool_access.workflow',
          },
          inactive_local_grants: { local: ['legacy_tool'] },
          diagnostics: [{ code: 'debug', message: 'Tool access mismatch detected', source: 'test' }],
        },
      })

      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )
      fireEvent.click(screen.getByText('Tool access details'))

      expect(screen.getByText('allowed:')).toBeInTheDocument()
      expect(screen.getByText('send_message')).toBeInTheDocument()
      expect(screen.getByText('cao_example.get_item')).toBeInTheDocument()
      expect(screen.getByText('agent_config:cao_tools')).toBeInTheDocument()
      expect(screen.getByText('example:tool_access.workflow')).toBeInTheDocument()
      expect(screen.getByText(/Inactive agent-local grants: local/)).toBeInTheDocument()
      expect(screen.getByText('Tool access mismatch detected')).toBeInTheDocument()
    })

    it('renders stopped agent header with a Start button that fires the provided handler', () => {
      // Given
      const agent = agentStatus()
      const onStart = vi.fn()
      const onStop = vi.fn()

      // When
      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={onStart}
          onOpenTerminal={vi.fn()}
          onStopAgent={onStop}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )
      fireEvent.click(screen.getByRole('button', { name: /start aria/i }))

      // Then
      expect(screen.getByText('Stopped')).toBeInTheDocument()
      expect(onStart).toHaveBeenCalledWith('aria')
      expect(onStop).not.toHaveBeenCalled()
    })

    it('disables the Start button while the agent is starting', () => {
      // Given
      const agent = agentStatus()

      // When
      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          startingAgentId="aria"
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )

      // Then
      const button = screen.getByRole('button', { name: /start aria/i })
      expect(button).toBeDisabled()
      expect(button).toHaveTextContent(/starting/i)
    })

    it('falls back to a placeholder when no agent is selected', () => {
      // Given / When
      render(
        <AgentDetailPanel
          agent={null}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )

      // Then
      expect(screen.getByText(/select an agent/i)).toBeInTheDocument()
      expect(renderConfigTab).not.toHaveBeenCalled()
      expect(renderTimelineTab).not.toHaveBeenCalled()
    })
  })

  describe('tab control', () => {
    it('defaults to the Config tab on first render', () => {
      // Given
      const agent = agentStatus()

      // When
      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )

      // Then
      expect(screen.getByRole('tab', { name: 'Config' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByTestId('config-tab')).toBeInTheDocument()
      expect(screen.queryByTestId('timeline-tab')).not.toBeInTheDocument()
    })

    it('switches to the Timeline tab on click and stays on it while the same agent is selected', () => {
      // Given
      const agent = agentStatus()

      // When
      render(
        <AgentDetailPanel
          agent={agent}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )
      fireEvent.click(screen.getByRole('tab', { name: 'Timeline' }))

      // Then
      expect(screen.getByRole('tab', { name: 'Timeline' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByTestId('timeline-tab')).toBeInTheDocument()
      expect(screen.queryByTestId('config-tab')).not.toBeInTheDocument()
    })

    it('preserves the active tab when the selected agent changes', () => {
      // Given
      const aria = agentStatus({ agent_id: 'aria', display_name: 'Aria' })
      const cael = agentStatus({ agent_id: 'cael', display_name: 'Cael' })
      const { rerender } = render(
        <AgentDetailPanel
          agent={aria}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )
      fireEvent.click(screen.getByRole('tab', { name: 'Timeline' }))

      // When
      rerender(
        <AgentDetailPanel
          agent={cael}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )

      // Then
      expect(screen.getByRole('tab', { name: 'Timeline' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByTestId('timeline-tab')).toHaveTextContent('timeline for cael')
    })
  })
})

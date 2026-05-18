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
      workspace: { setup: null, diagnostics: [] },
      linear: null,
    },
    active: false,
    active_terminal_id: null,
    active_workspace_context_id: null,
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

    it('renders workspace setup diagnostics from the setup manager endpoint', () => {
      render(
        <AgentDetailPanel
          agent={agentStatus({ workspace_setup_id: 'cao_delivery' })}
          workspaceSetupDiagnostics={[
            {
              code: 'pruned_provider_identity',
              message: 'Workspace setup cao_delivery pruned linear tool access for discovery',
              setup_id: 'cao_delivery',
              agent_id: 'aria',
              provider_name: 'linear',
            },
            {
              code: 'unavailable_provider',
              message: 'Workspace setup cao_delivery requires unavailable provider linear',
              setup_id: 'cao_delivery',
              agent_id: null,
              provider_name: 'linear',
            },
          ]}
          onStartAgent={vi.fn()}
          onOpenTerminal={vi.fn()}
          onStopAgent={vi.fn()}
          renderConfigTab={renderConfigTab}
          renderTimelineTab={renderTimelineTab}
        />,
      )

      expect(screen.getByText(/pruned linear tool access/)).toBeInTheDocument()
      expect(screen.getByText(/requires unavailable provider linear/)).toBeInTheDocument()
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

import { useState } from 'react'
import { Monitor, Play, Square } from 'lucide-react'
import { AgentStatus, WorkspaceSetupDiagnostic } from '../../api'

export type AgentDetailTab = 'config' | 'timeline'

interface AgentDetailPanelProps {
  agent: AgentStatus | null
  onStartAgent: (agentId: string) => void | Promise<void>
  onOpenTerminal: (agentId: string) => void | Promise<void>
  onStopAgent: (agentId: string) => void | Promise<void>
  startingAgentId?: string | null
  stoppingAgentId?: string | null
  workspaceSetupDiagnostics?: WorkspaceSetupDiagnostic[]
  renderConfigTab: (agent: AgentStatus) => JSX.Element
  renderTimelineTab: (agent: AgentStatus) => JSX.Element
}

const TABS: { key: AgentDetailTab; label: string }[] = [
  { key: 'config', label: 'Config' },
  { key: 'timeline', label: 'Timeline' },
]

export function AgentDetailPanel({
  agent,
  onStartAgent,
  onOpenTerminal,
  onStopAgent,
  startingAgentId = null,
  stoppingAgentId = null,
  workspaceSetupDiagnostics = [],
  renderConfigTab,
  renderTimelineTab,
}: AgentDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<AgentDetailTab>('config')

  if (!agent) {
    return (
      <div className="rounded-xl border border-gray-700/50 bg-gray-800/60 p-4 min-w-0">
        <p className="text-gray-500 text-sm">Select an agent to view its details.</p>
      </div>
    )
  }

  const isStarting = startingAgentId === agent.agent_id
  const isStopping = stoppingAgentId === agent.agent_id
  const diagnostics = [
    ...(agent.workspace_setup_diagnostics ?? []),
    ...workspaceSetupDiagnostics
      .filter(diagnostic => !diagnostic.agent_id || diagnostic.agent_id === agent.agent_id)
      .map(diagnostic => diagnostic.message),
  ]

  return (
    <div className="rounded-lg border border-gray-700/50 bg-gray-800/60 min-w-0">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-gray-700/50 p-4">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs ${
                agent.active
                  ? 'bg-emerald-900/60 text-emerald-300'
                  : 'bg-gray-700 text-gray-400'
              }`}
            >
              {agent.active ? 'Running' : 'Stopped'}
            </span>
            <span className="rounded-full bg-gray-700/70 px-2 py-0.5 text-xs text-gray-300">{agent.cli_provider}</span>
          </div>
          <h3 className="truncate text-xl font-semibold text-white">{agent.display_name}</h3>
          <dl className="mt-2 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-2 gap-y-1 font-mono text-xs text-gray-500">
            <dt className="text-gray-600">id</dt>
            <dd className="truncate text-gray-400">{agent.agent_id}</dd>
            <dt className="text-gray-600">workdir</dt>
            <dd className="truncate text-gray-400">{agent.workdir}</dd>
            <dt className="text-gray-600">setup</dt>
            <dd className="truncate text-violet-300">{agent.workspace_setup_id ?? 'none'}</dd>
            {agent.active && agent.active_terminal_id && (
              <>
                <dt className="text-gray-600">terminal</dt>
                <dd className="truncate text-emerald-400">{agent.active_terminal_id}</dd>
              </>
            )}
            {agent.active_workspace_context_id && (
              <>
                <dt className="text-gray-600">context</dt>
                <dd className="truncate text-cyan-300">{agent.active_workspace_context_id}</dd>
              </>
            )}
          </dl>
          {!!diagnostics.length && (
            <div className="mt-2 space-y-1">
              {diagnostics.map(diagnostic => (
                <p key={diagnostic} className="max-w-xl text-xs text-amber-300">
                  {diagnostic}
                </p>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {agent.active ? (
            <>
              <button
                type="button"
                onClick={() => onOpenTerminal(agent.agent_id)}
                aria-label={`Open terminal for ${agent.agent_id}`}
                className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-medium rounded-lg transition-colors"
              >
                <Monitor size={13} />
                Open Terminal
              </button>
              <button
                type="button"
                onClick={() => onStopAgent(agent.agent_id)}
                disabled={isStopping}
                aria-label={`Stop ${agent.agent_id}`}
                className="flex items-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white text-xs font-medium rounded-lg transition-colors"
              >
                <Square size={13} />
                {isStopping ? 'Stopping...' : 'Stop'}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => onStartAgent(agent.agent_id)}
              disabled={isStarting}
              aria-label={`Start ${agent.agent_id}`}
              className="flex items-center gap-2 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-medium rounded-lg transition-colors"
            >
              <Play size={13} />
              {isStarting ? 'Starting...' : 'Start'}
            </button>
          )}
        </div>
      </header>

      <div role="tablist" aria-label="Agent detail tabs" className="flex gap-1 border-b border-gray-700/50 px-4">
        {TABS.map(tab => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-1.5 -mb-px text-xs font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-emerald-500 text-emerald-300'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" aria-label={`${activeTab} tab content`} className="min-w-0 p-4">
        {activeTab === 'config' ? renderConfigTab(agent) : renderTimelineTab(agent)}
      </div>
    </div>
  )
}

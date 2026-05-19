import { useState } from 'react'
import { Monitor, Play, Square, Wrench } from 'lucide-react'
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

const PRUNED_PROVIDER_IDENTITY_DIAGNOSTIC_CODE = 'pruned_provider_identity'

function isNoisyPruningDiagnostic(message: string) {
  return /pruned .* for out-of-team agent /.test(message)
}

function sourceLabel(source: { kind: string; name: string }) {
  return `${source.kind.replace(/_/g, ' ')} / ${source.name}`
}

function sameToolSet(left: string[], right: string[]) {
  if (left.length !== right.length) return false
  const rightSet = new Set(right)
  return left.every(tool => rightSet.has(tool))
}

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
  const [availableToolsOpen, setAvailableToolsOpen] = useState(false)
  const [toolDetailsOpen, setToolDetailsOpen] = useState(false)

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
    ...(agent.workspace_team_diagnostics ?? []),
    ...workspaceSetupDiagnostics
      .filter(diagnostic => diagnostic.code !== PRUNED_PROVIDER_IDENTITY_DIAGNOSTIC_CODE)
      .filter(diagnostic => !diagnostic.agent_id || diagnostic.agent_id === agent.agent_id)
      .map(diagnostic => diagnostic.message),
  ].filter(diagnostic => !isNoisyPruningDiagnostic(diagnostic))
  const mcpToolSurfaceAvailable = !!agent.mcp_tool_surface
  const mcpTools = agent.mcp_tool_surface?.tools ?? []
  const effectiveToolAccess = agent.effective_tool_access
  const allowedTools = effectiveToolAccess?.allowed_tools ?? []
  const inactiveGrantNames = Object.keys(effectiveToolAccess?.inactive_local_grants ?? {})
  const materializedServers = Object.keys(effectiveToolAccess?.materialized_mcp_servers ?? {})
  const visibleToolNames = mcpTools.map(tool => tool.name)
  const toolSurfaceMismatch = !!effectiveToolAccess
    && mcpToolSurfaceAvailable
    && !sameToolSet(visibleToolNames, allowedTools)
  const showToolAccessDetails = !!effectiveToolAccess && (
    toolSurfaceMismatch
    || inactiveGrantNames.length > 0
    || effectiveToolAccess.diagnostics.length > 0
  )

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
            <dt className="text-gray-600">team</dt>
            <dd className="truncate text-emerald-300">{agent.workspace_team_id ?? 'none'}</dd>
            <dt className="text-gray-600">setup</dt>
            <dd className="truncate text-violet-300">{agent.derived_workspace_setup_id ?? 'default'}</dd>
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
          <section className="mt-3 max-w-xl border-t border-gray-700/50 pt-3">
            <button
              type="button"
              onClick={() => setAvailableToolsOpen(open => !open)}
              aria-expanded={availableToolsOpen}
              className="flex items-center gap-2 text-xs font-medium text-gray-300 hover:text-gray-100"
            >
              <Wrench size={13} className="text-emerald-300" />
              <span>Available tools</span>
              <span className="rounded-full bg-gray-700/70 px-1.5 py-0.5 font-mono text-[10px] text-gray-400">
                {mcpToolSurfaceAvailable ? mcpTools.length : 'unavailable'}
              </span>
            </button>
            {availableToolsOpen && (
              <div className="mt-2 space-y-2">
                {!mcpToolSurfaceAvailable ? (
                  <p className="text-xs text-amber-300">
                    Tool access is unavailable from this dashboard response. Refresh after restarting the CAO server with the latest backend.
                  </p>
                ) : agent.active ? (
                  <p className="text-xs text-amber-300">
                    Current config for new MCP sessions; this running terminal may need a restart to pick up tool changes.
                  </p>
                ) : null}
                {mcpToolSurfaceAvailable && (
                  <p className="text-xs text-gray-500">Managed by ToolService.</p>
                )}
                {!mcpToolSurfaceAvailable ? null : mcpTools.length ? (
                  <ul className="space-y-2">
                    {mcpTools.map(tool => (
                      <li key={`${tool.source.kind}:${tool.source.name}:${tool.name}`} className="min-w-0">
                        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                          <span className="font-mono text-xs text-emerald-300">{tool.name}</span>
                          <span className="font-mono text-[10px] uppercase text-gray-500">
                            {sourceLabel(tool.source)}
                          </span>
                        </div>
                        {tool.description && (
                          <p className="mt-0.5 text-xs text-gray-500">{tool.description}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-gray-500">No MCP tools visible for this agent.</p>
                )}
              </div>
            )}
          </section>
          {showToolAccessDetails && (
            <section className="mt-3 max-w-xl border-t border-gray-700/50 pt-3">
              <button
                type="button"
                onClick={() => setToolDetailsOpen(open => !open)}
                aria-expanded={toolDetailsOpen}
                className="flex items-center gap-2 text-xs font-medium text-amber-200 hover:text-amber-100"
              >
                <Wrench size={13} className="text-amber-300" />
                <span>Tool access details</span>
                <span className="rounded-full bg-amber-950/50 px-1.5 py-0.5 font-mono text-[10px] text-amber-200">
                  debug
                </span>
              </button>
              {toolDetailsOpen && (
                <div className="mt-2 space-y-2 text-xs">
                  {toolSurfaceMismatch && (
                    <p className="text-amber-300">
                      Available tools differ from ToolService allowed tools.
                    </p>
                  )}
                  <div className="grid gap-1 font-mono text-gray-400">
                    <div className="flex flex-wrap gap-x-2 gap-y-1">
                      <span>allowed:</span>
                      {allowedTools.length ? (
                        allowedTools.map(tool => (
                          <span
                            key={tool}
                            className="inline-flex max-w-full flex-wrap gap-x-1 text-gray-300"
                          >
                            <span>{tool}</span>
                            {effectiveToolAccess.source_markers[tool] && (
                              <span className="text-gray-500">
                                {effectiveToolAccess.source_markers[tool]}
                              </span>
                            )}
                          </span>
                        ))
                      ) : (
                        <span>none</span>
                      )}
                    </div>
                    <div>runtime: {effectiveToolAccess.runtime_capabilities.join(', ') || 'none'}</div>
                    <div>mcp: {materializedServers.join(', ') || 'none'}</div>
                  </div>
                  {!!inactiveGrantNames.length && (
                    <div className="rounded-md border border-amber-500/30 bg-amber-950/20 p-2 text-amber-200">
                      Inactive agent-local grants: {inactiveGrantNames.join(', ')}
                    </div>
                  )}
                  {!!effectiveToolAccess.diagnostics.length && (
                    <ul className="space-y-1 text-amber-300">
                      {effectiveToolAccess.diagnostics.map(item => (
                        <li key={`${item.code}:${item.message}`}>{item.message}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>
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

import { useEffect, useRef, useState } from 'react'
import { Monitor, Play, Plus, Square, X } from 'lucide-react'
import { api, AgentStatus, WorkspaceSetupDiagnostic } from '../api'
import { useProviderSchema } from '../hooks/useProviderSchema'
import { useStore } from '../store'
import { AgentConfigTab } from './agents-tab/AgentConfigTab'
import { AgentDetailPanel } from './agents-tab/AgentDetailPanel'
import { AgentTimelineTab } from './agents-tab/AgentTimelineTab'
import { TerminalView } from './TerminalView'

interface AgentPanelProps {
  initialTerminalId?: string | null
  initialTerminalToken?: string | null
  initialAgentId?: string | null
  initialAgentToken?: string | null
  onInitialDeepLinkConsumed?: () => void
}

const emptyCreateDraft = {
  id: '',
  display_name: '',
  cli_provider: '',
  workdir: '',
}

export function AgentPanel({
  initialTerminalId = null,
  initialTerminalToken = null,
  initialAgentId = null,
  initialAgentToken = null,
  onInitialDeepLinkConsumed,
}: AgentPanelProps) {
  const { selectSession, showSnackbar } = useStore()
  const providerSchema = useProviderSchema()
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [workspaceSetupDiagnostics, setWorkspaceSetupDiagnostics] = useState<WorkspaceSetupDiagnostic[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [startingAgentId, setStartingAgentId] = useState<string | null>(null)
  const [stoppingAgentId, setStoppingAgentId] = useState<string | null>(null)
  const [editingByDefaultAgentId, setEditingByDefaultAgentId] = useState<string | null>(null)
  const [createDraft, setCreateDraft] = useState(emptyCreateDraft)
  const [creatingAgent, setCreatingAgent] = useState(false)
  const [liveTerminal, setLiveTerminal] = useState<{ id: string; provider?: string; agentId?: string | null; terminalToken?: string | null } | null>(null)
  const initialTerminalOpened = useRef(false)

  const refreshAgents = () => Promise.all([
    api.listAgents(),
    api.listWorkspaceSetupDiagnostics().catch(() => [] as WorkspaceSetupDiagnostic[]),
  ]).then(([nextAgents, nextDiagnostics]) => {
    setAgents(nextAgents)
    setWorkspaceSetupDiagnostics(nextDiagnostics)
    setSelectedAgentId(previous => (
      previous && nextAgents.some(agent => agent.agent_id === previous)
        ? previous
        : nextAgents[0]?.agent_id ?? null
    ))
  }).catch(() => {})

  const selectedAgent = agents.find(agent => agent.agent_id === selectedAgentId) ?? agents[0] ?? null

  useEffect(() => {
    refreshAgents()
  }, [])

  const openTerminal = (terminalId: string, provider?: string, agentId?: string | null, terminalToken?: string | null) => {
    setLiveTerminal({ id: terminalId, provider, agentId, terminalToken })
  }

  const openAgentTerminal = async (agent: AgentStatus) => {
    if (!agent.active) {
      showSnackbar({ type: 'error', message: `Agent ${agent.agent_id} is not running` })
      return
    }
    try {
      const result = await api.getAgentRuntimeTerminal(
        agent.agent_id,
        agent.agent_dashboard_token,
      )
      openTerminal(result.terminal.id, result.terminal.provider, result.terminal.agent_id, result.terminal_token)
    } catch (error) {
      showSnackbar({ type: 'error', message: error instanceof Error ? error.message : `Agent ${agent.agent_id} does not have a running terminal` })
    }
  }

  const handleStartAgent = async (agentId: string) => {
    setStartingAgentId(agentId)
    try {
      const result = await api.startAgent(agentId)
      openTerminal(result.terminal.id, result.terminal.provider, result.terminal.agent_id, result.terminal_token)
      await refreshAgents()
    } catch (error) {
      showSnackbar({ type: 'error', message: error instanceof Error ? error.message : `Failed to start ${agentId}` })
    } finally {
      setStartingAgentId(null)
    }
  }

  const handleStopAgent = async (agentId: string) => {
    setStoppingAgentId(agentId)
    try {
      await api.stopAgent(agentId)
      if (liveTerminal?.agentId === agentId) setLiveTerminal(null)
      await refreshAgents()
      showSnackbar({ type: 'success', message: `Agent ${agentId} stopped` })
    } catch (error) {
      showSnackbar({ type: 'error', message: error instanceof Error ? error.message : `Failed to stop ${agentId}` })
    } finally {
      setStoppingAgentId(null)
    }
  }

  const handleAgentUpdated = (updated: AgentStatus) => {
    setAgents(previous => previous.map(entry => entry.agent_id === updated.agent_id ? updated : entry))
    setSelectedAgentId(updated.agent_id)
    if (editingByDefaultAgentId === updated.agent_id) setEditingByDefaultAgentId(null)
    showSnackbar({ type: 'success', message: `Agent ${updated.agent_id} updated` })
  }

  const handleAgentSaveError = (message: string) => {
    showSnackbar({ type: 'error', message })
  }

  const handleCreateAgent = async () => {
    const agentId = createDraft.id.trim()
    if (!agentId) return
    const providerChoice = createDraft.cli_provider.trim()
    if (!providerChoice) {
      showSnackbar({ type: 'error', message: 'Pick a CLI provider' })
      return
    }
    setCreatingAgent(true)
    try {
      const created = await api.createAgent({
        id: agentId,
        display_name: createDraft.display_name.trim() || agentId,
        cli_provider: providerChoice,
        workdir: createDraft.workdir.trim() || '/',
      })
      setAgents(previous => [...previous.filter(agent => agent.agent_id !== created.agent_id), created])
      setSelectedAgentId(created.agent_id)
      setEditingByDefaultAgentId(created.agent_id)
      setCreateDraft(emptyCreateDraft)
      setShowCreateDialog(false)
      showSnackbar({ type: 'success', message: `Agent ${created.agent_id} created` })
    } catch (error) {
      showSnackbar({ type: 'error', message: error instanceof Error ? error.message : `Failed to create ${agentId}` })
    } finally {
      setCreatingAgent(false)
    }
  }

  const focusTimelineTerminal = async (terminalId: string) => {
    try {
      const terminal = await api.getTerminal(terminalId)
      await selectSession(terminal.session_name)
      openTerminal(terminal.id, terminal.provider, terminal.agent_id)
    } catch {
      showSnackbar({ type: 'error', message: `Terminal ${terminalId} was not found` })
    }
  }

  useEffect(() => {
    if ((!initialTerminalId && !initialAgentId) || initialTerminalOpened.current) return
    let cancelled = false
    initialTerminalOpened.current = true
    onInitialDeepLinkConsumed?.()
    const terminalPromise = initialTerminalId
      ? api.getTerminal(initialTerminalId).then(terminal => ({ terminal, terminalToken: initialTerminalToken }))
      : api.getAgentRuntimeTerminal(initialAgentId as string, initialAgentToken).then(result => ({ terminal: result.terminal, terminalToken: result.terminal_token }))

    terminalPromise.then(async ({ terminal, terminalToken }) => {
      if (cancelled) return
      await selectSession(terminal.session_name)
      if (!cancelled) openTerminal(terminal.id, terminal.provider, terminal.agent_id, terminalToken)
    }).catch(() => {
      if (!cancelled) showSnackbar({ type: 'error', message: initialAgentId ? `Agent ${initialAgentId} does not have a running terminal` : `Terminal ${initialTerminalId} was not found` })
    })
    return () => { cancelled = true }
  }, [initialTerminalId, initialTerminalToken, initialAgentId, initialAgentToken, onInitialDeepLinkConsumed])

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="bg-gray-800/60 border border-gray-700/50 rounded-lg p-4">
          <div className="flex items-center justify-between gap-3 mb-3">
            <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Agents ({agents.length})</h3>
            <button
              type="button"
              onClick={() => setShowCreateDialog(true)}
              className="inline-flex h-8 items-center gap-2 rounded-lg bg-emerald-600 px-3 text-xs font-semibold text-white transition-colors hover:bg-emerald-500"
            >
              <Plus size={14} /> New Agent
            </button>
          </div>
          {agents.length === 0 ? (
            <p className="text-gray-500 text-sm">No agents configured.</p>
          ) : (
            <div className="space-y-2">
              {agents.map(agent => (
                <div
                  key={agent.agent_id}
                  className={`grid min-h-[76px] grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-lg border p-3 transition-colors ${selectedAgent?.agent_id === agent.agent_id ? 'bg-emerald-900/30 border-emerald-700/50' : 'bg-gray-900/50 border-gray-700/30 hover:bg-gray-800/80'}`}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedAgentId(agent.agent_id)}
                    aria-label={`Select ${agent.display_name}`}
                    className="min-w-0 text-left"
                  >
                    <span className="block truncate text-sm font-semibold text-gray-200">{agent.display_name}</span>
                    <span className="block truncate text-xs text-gray-500 font-mono">{agent.agent_id} · {agent.cli_provider}</span>
                    <span className="mt-2 flex flex-wrap gap-1.5">
                      <span className={`inline-flex text-xs px-2 py-0.5 rounded-full ${agent.active ? 'bg-emerald-900/50 text-emerald-300' : 'bg-gray-700/70 text-gray-300'}`}>
                        {agent.active ? 'Running' : 'Stopped'}
                      </span>
                      {agent.active && agent.active_terminal_id && (
                        <span className="inline-flex max-w-full truncate rounded-full bg-gray-700/70 px-2 py-0.5 font-mono text-xs text-gray-300">
                          {agent.active_terminal_id}
                        </span>
                      )}
                    </span>
                  </button>
                  <div className="flex items-center gap-1.5" aria-label={`${agent.display_name} actions`}>
                    {agent.active ? (
                      <>
                        <button
                          type="button"
                          onClick={() => openAgentTerminal(agent)}
                          aria-label={`Open terminal for ${agent.agent_id}`}
                          title="Open terminal"
                          className="grid h-8 w-8 place-items-center rounded-lg bg-emerald-600 text-white transition-colors hover:bg-emerald-500"
                        >
                          <Monitor size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleStopAgent(agent.agent_id)}
                          disabled={stoppingAgentId === agent.agent_id}
                          aria-label={`Stop agent ${agent.agent_id}`}
                          title="Stop agent"
                          className="grid h-8 w-8 place-items-center rounded-lg bg-red-900/80 text-red-100 transition-colors hover:bg-red-700 disabled:opacity-40"
                        >
                          <Square size={13} />
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleStartAgent(agent.agent_id)}
                        disabled={startingAgentId === agent.agent_id}
                        aria-label={`Start agent ${agent.agent_id}`}
                        title="Start agent"
                        className="grid h-8 w-8 place-items-center rounded-lg bg-emerald-600 text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
                      >
                        <Play size={14} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <AgentDetailPanel
          agent={selectedAgent}
          onStartAgent={handleStartAgent}
          onOpenTerminal={agentId => {
            const agent = agents.find(entry => entry.agent_id === agentId)
            if (agent) openAgentTerminal(agent)
          }}
          onStopAgent={handleStopAgent}
          startingAgentId={startingAgentId}
          stoppingAgentId={stoppingAgentId}
          workspaceSetupDiagnostics={workspaceSetupDiagnostics}
          renderConfigTab={agent => (
            <AgentConfigTab
              key={agent.agent_id}
              agent={agent}
              onAgentUpdated={handleAgentUpdated}
              onSaveError={handleAgentSaveError}
              defaultEditing={editingByDefaultAgentId === agent.agent_id}
            />
          )}
          renderTimelineTab={agent => (
            <AgentTimelineTab
              agentId={agent.agent_id}
              onFocusTerminal={focusTimelineTerminal}
            />
          )}
        />
      </div>

      {liveTerminal && <TerminalView terminalId={liveTerminal.id} provider={liveTerminal.provider} agentId={liveTerminal.agentId} terminalToken={liveTerminal.terminalToken} onClose={() => setLiveTerminal(null)} />}

      {showCreateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowCreateDialog(false)} />
          <div className="relative bg-gray-800 border border-gray-700 rounded-2xl shadow-2xl shadow-black/50 w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b border-gray-700/50">
              <h3 className="text-base font-semibold text-gray-200">New Agent</h3>
              <button onClick={() => setShowCreateDialog(false)} className="p-1.5 text-gray-500 hover:text-gray-300 transition-colors rounded-lg hover:bg-gray-700/50"><X size={18} /></button>
            </div>
            <div className="p-5">
              <div className="space-y-3">
                <label className="block text-xs text-gray-400">
                  Agent ID
                  <input value={createDraft.id} onChange={event => setCreateDraft(previous => ({ ...previous, id: event.target.value }))} className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none" />
                </label>
                <label className="block text-xs text-gray-400">
                  Display name
                  <input value={createDraft.display_name} onChange={event => setCreateDraft(previous => ({ ...previous, display_name: event.target.value }))} className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none" />
                </label>
                <label className="block text-xs text-gray-400">
                  Provider
                  {providerSchema.status === 'ready' && providerSchema.schemas ? (
                    <select
                      value={createDraft.cli_provider}
                      onChange={event => setCreateDraft(previous => ({ ...previous, cli_provider: event.target.value }))}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
                    >
                      <option value="">Select a provider…</option>
                      {providerSchema.schemas.map(schema => (
                        <option key={schema.name} value={schema.name}>
                          {schema.name}
                          {schema.installed ? '' : '  (not installed)'}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={createDraft.cli_provider}
                      onChange={event => setCreateDraft(previous => ({ ...previous, cli_provider: event.target.value }))}
                      placeholder={providerSchema.status === 'loading' ? 'Loading providers…' : 'Provider name'}
                      disabled={providerSchema.status === 'loading'}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none disabled:opacity-50"
                    />
                  )}
                </label>
                <label className="block text-xs text-gray-400">
                  Workdir
                  <input value={createDraft.workdir} onChange={event => setCreateDraft(previous => ({ ...previous, workdir: event.target.value }))} className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none" />
                </label>
                <button onClick={handleCreateAgent} disabled={creatingAgent || !createDraft.id.trim() || !createDraft.cli_provider.trim()} className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium rounded-lg transition-colors">
                  <Plus size={14} /> {creatingAgent ? 'Creating...' : 'Create Agent'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

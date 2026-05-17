import { useEffect, useRef, useState } from 'react'
import { Bot, ChevronRight, Edit3, FileText, Mail, Monitor, Play, Plus, RotateCcw, Save, Send, Terminal as TermIcon, Trash2, X } from 'lucide-react'
import { api, AgentConfig, AgentStatus, AgentWriteRequest, TerminalMeta } from '../api'
import { useStore } from '../store'
import { AgentTimelinePanel } from './AgentTimelinePanel'
import { BatonIndicator } from './BatonIndicator'
import { ConfirmModal } from './ConfirmModal'
import { InboxPanel } from './InboxPanel'
import { MonitoringButton } from './MonitoringButton'
import { MonitoringIndicator } from './MonitoringIndicator'
import { OutputViewer } from './OutputViewer'
import { StatusBadge } from './StatusBadge'
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
  cli_provider: 'codex',
  workdir: '',
}

function quoteTomlString(value: string): string {
  return `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
}

function formatTomlKey(key: string): string {
  return /^[A-Za-z0-9_-]+$/.test(key) ? key : quoteTomlString(key)
}

function formatTomlValue(value: unknown): string {
  if (typeof value === 'string') return quoteTomlString(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return String(value)
  if (Array.isArray(value)) return `[${value.map(formatTomlValue).join(', ')}]`
  if (value && typeof value === 'object') {
    return `{ ${Object.entries(value as Record<string, unknown>).map(([key, entry]) => `${formatTomlKey(key)} = ${formatTomlValue(entry)}`).join(', ')} }`
  }
  return 'null'
}

function appendValue(lines: string[], key: string, value: unknown) {
  if (value === null || value === undefined) return
  if (Array.isArray(value) && value.length === 0) return
  if (value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value as Record<string, unknown>).length === 0) return
  lines.push(`${formatTomlKey(key)} = ${formatTomlValue(value)}`)
}

function formatAgentToml(config: AgentConfig): string {
  const lines: string[] = []
  appendValue(lines, 'id', config.id)
  appendValue(lines, 'display_name', config.display_name)
  appendValue(lines, 'cli_provider', config.cli_provider)
  appendValue(lines, 'workdir', config.workdir)
  appendValue(lines, 'session_name', config.session_name)
  appendValue(lines, 'model', config.model)
  appendValue(lines, 'description', config.description)
  appendValue(lines, 'reasoning_effort', config.reasoning_effort)
  appendValue(lines, 'tools', config.tools)
  appendValue(lines, 'cao_tools', config.cao_tools)
  appendValue(lines, 'skills', config.skills)
  appendValue(lines, 'tags', config.tags)
  appendValue(lines, 'resources', config.resources)
  appendValue(lines, 'runtime_capabilities', config.runtime_capabilities)
  appendValue(lines, 'use_legacy_mcp_json', config.use_legacy_mcp_json)

  if (config.workspace_context) {
    lines.push('', '[workspace_context]')
    appendValue(lines, 'enabled', config.workspace_context.enabled)
    appendValue(lines, 'resolver_id', config.workspace_context.resolver_id)
  }

  Object.entries(config.mcp_servers || {}).forEach(([name, server]) => {
    lines.push('', `[mcp_servers.${formatTomlKey(name)}]`)
    if (server && typeof server === 'object' && !Array.isArray(server)) {
      Object.entries(server as Record<string, unknown>).forEach(([key, value]) => appendValue(lines, key, value))
    } else {
      appendValue(lines, 'value', server)
    }
  })

  if (Object.keys(config.codex_config || {}).length) {
    lines.push('', '[codex_config]')
    Object.entries(config.codex_config).forEach(([key, value]) => appendValue(lines, key, value))
  }

  if (config.linear) {
    lines.push('', '[linear]')
    appendValue(lines, 'app_key', config.linear.app_key)
    appendValue(lines, 'client_id', config.linear.client_id)
    appendValue(lines, 'client_secret_configured', config.linear.client_secret_configured)
    appendValue(lines, 'webhook_secret_configured', config.linear.webhook_secret_configured)
    appendValue(lines, 'oauth_redirect_uri', config.linear.oauth_redirect_uri)
    appendValue(lines, 'access_token_configured', config.linear.access_token_configured)
    appendValue(lines, 'refresh_token_configured', config.linear.refresh_token_configured)
    appendValue(lines, 'token_expires_at', config.linear.token_expires_at)
    appendValue(lines, 'app_user_id', config.linear.app_user_id)
    appendValue(lines, 'app_user_name', config.linear.app_user_name)
    appendValue(lines, 'oauth_state_configured', config.linear.oauth_state_configured)
    config.linear.tool_access.forEach(access => {
      lines.push('', `[linear.tool_access.${formatTomlKey(access.access_id)}]`)
      appendValue(lines, 'tools', access.tools)
      appendValue(lines, 'issues', access.issues)
      appendValue(lines, 'create_team_ids', access.create_team_ids)
      appendValue(lines, 'create_project_ids', access.create_project_ids)
      appendValue(lines, 'create_parent_issues', access.create_parent_issues)
      appendValue(lines, 'allow_top_level_create', access.allow_top_level_create)
      appendValue(lines, 'update_fields', access.update_fields)
      appendValue(lines, 'reason', access.reason)
    })
  }

  return lines.join('\n') + '\n'
}

function parseTomlValue(value: string): unknown {
  const trimmed = value.trim()
  if (trimmed === 'true') return true
  if (trimmed === 'false') return false
  if (trimmed === 'null') return null
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, '\\')
  }
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    const inner = trimmed.slice(1, -1).trim()
    if (!inner) return []
    return inner.split(',').map(part => parseTomlValue(part.trim())).filter((entry): entry is string => typeof entry === 'string')
  }
  return trimmed
}

function parseAgentTomlDraft(text: string): AgentWriteRequest {
  const body: AgentWriteRequest = {}
  const stringFields = new Set(['id', 'display_name', 'cli_provider', 'workdir', 'session_name', 'prompt'])
  const nullableStringFields = new Set(['description', 'model', 'reasoning_effort'])
  const listFields = new Set(['tools', 'skills', 'runtime_capabilities', 'cao_tools'])
  let section = ''

  text.split(/\r?\n/).forEach(rawLine => {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) return
    if (line.startsWith('[') && line.endsWith(']')) {
      section = line.slice(1, -1)
      return
    }
    if (section) return
    const match = line.match(/^([A-Za-z0-9_-]+)\s*=\s*(.*)$/)
    if (!match) return
    const [, key, rawValue] = match
    const value = parseTomlValue(rawValue)
    if (stringFields.has(key) && typeof value === 'string') {
      ;(body as Record<string, unknown>)[key] = value
    } else if (nullableStringFields.has(key) && (typeof value === 'string' || value === null)) {
      ;(body as Record<string, unknown>)[key] = value
    } else if (listFields.has(key) && Array.isArray(value)) {
      ;(body as Record<string, unknown>)[key] = value
    }
  })

  return body
}

export function AgentPanel({
  initialTerminalId = null,
  initialTerminalToken = null,
  initialAgentId = null,
  initialAgentToken = null,
  onInitialDeepLinkConsumed,
}: AgentPanelProps) {
  const { sessions, fetchSessions, activeSession, activeSessionDetail, selectSession, deleteSession, terminalStatuses, setTerminalStatus, setActiveMonitoringSessions, setActiveBatons, showSnackbar } = useStore()
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [showSpawnModal, setShowSpawnModal] = useState(false)
  const [startingAgentId, setStartingAgentId] = useState<string | null>(null)
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null)
  const [agentTomlDraft, setAgentTomlDraft] = useState('')
  const [savingAgentId, setSavingAgentId] = useState<string | null>(null)
  const [createMode, setCreateMode] = useState(false)
  const [createDraft, setCreateDraft] = useState(emptyCreateDraft)
  const [creatingAgent, setCreatingAgent] = useState(false)
  const [liveTerminal, setLiveTerminal] = useState<{ id: string; provider?: string; agentId?: string | null; terminalToken?: string | null } | null>(null)
  const [pendingClose, setPendingClose] = useState<TerminalMeta | null>(null)
  const [closingTerminal, setClosingTerminal] = useState<string | null>(null)
  const [inboxTerminalId, setInboxTerminalId] = useState<string | null>(null)
  const [outputTerminalId, setOutputTerminalId] = useState<string | null>(null)
  const [sendInputOpen, setSendInputOpen] = useState<Record<string, boolean>>({})
  const [sendInputValues, setSendInputValues] = useState<Record<string, string>>({})
  const [sendingInput, setSendingInput] = useState<string | null>(null)
  const initialTerminalOpened = useRef(false)

  const refreshAgents = () => api.listAgents().then(nextAgents => {
    setAgents(nextAgents)
    setSelectedAgentId(previous => (
      previous && nextAgents.some(agent => agent.agent_id === previous)
        ? previous
        : nextAgents[0]?.agent_id ?? null
    ))
  }).catch(() => {})

  const selectedAgent = agents.find(agent => agent.agent_id === selectedAgentId) ?? agents[0] ?? null

  useEffect(() => {
    refreshAgents()
    fetchSessions()
  }, [])

  useEffect(() => {
    if (!activeSession) return
    selectSession(activeSession)
    const interval = setInterval(() => selectSession(activeSession), 5000)
    return () => clearInterval(interval)
  }, [activeSession])

  useEffect(() => {
    if (!activeSessionDetail?.terminals.length) return
    const terminalIds = activeSessionDetail.terminals.map(t => t.id)
    const fetchStatuses = () => {
      terminalIds.forEach(id => {
        api.getTerminalStatus(id).then(status => { if (status) setTerminalStatus(id, status) }).catch(() => {})
      })
      api.listActiveMonitoringSessions().then(setActiveMonitoringSessions).catch(() => {})
      api.listActiveBatons().then(setActiveBatons).catch(() => {})
    }
    fetchStatuses()
    const interval = setInterval(fetchStatuses, 3000)
    return () => clearInterval(interval)
  }, [activeSessionDetail?.terminals.map(t => t.id).join(',')])

  const openTerminal = (terminalId: string, provider?: string, agentId?: string | null, terminalToken?: string | null) => {
    setLiveTerminal({ id: terminalId, provider, agentId, terminalToken })
  }

  const handleStartAgent = async (agentId: string) => {
    setStartingAgentId(agentId)
    try {
      const result = await api.startAgent(agentId)
      openTerminal(result.terminal.id, result.terminal.provider, result.terminal.agent_id, result.terminal_token)
      await fetchSessions()
      await selectSession(result.terminal.session_name)
      refreshAgents()
      setShowSpawnModal(false)
    } catch (error) {
      showSnackbar({ type: 'error', message: error instanceof Error ? error.message : `Failed to start ${agentId}` })
    } finally {
      setStartingAgentId(null)
    }
  }

  const handleEditAgent = (agent: AgentStatus) => {
    setEditingAgentId(agent.agent_id)
    setAgentTomlDraft(formatAgentToml(agent.config))
  }

  const handleSaveAgent = async (agent: AgentStatus) => {
    setSavingAgentId(agent.agent_id)
    try {
      const updated = await api.updateAgent(agent.agent_id, parseAgentTomlDraft(agentTomlDraft))
      setAgents(previous => previous.map(entry => entry.agent_id === updated.agent_id ? updated : entry))
      setEditingAgentId(null)
      setSelectedAgentId(updated.agent_id)
      showSnackbar({ type: 'success', message: `Agent ${updated.agent_id} updated` })
    } catch (error) {
      showSnackbar({ type: 'error', message: error instanceof Error ? error.message : `Failed to update ${agent.agent_id}` })
    } finally {
      setSavingAgentId(null)
    }
  }

  const handleCreateAgent = async () => {
    const agentId = createDraft.id.trim()
    if (!agentId) return
    setCreatingAgent(true)
    try {
      const created = await api.createAgent({
        id: agentId,
        display_name: createDraft.display_name.trim() || agentId,
        cli_provider: createDraft.cli_provider.trim() || 'codex',
        workdir: createDraft.workdir.trim() || '/',
      })
      setAgents(previous => [...previous.filter(agent => agent.agent_id !== created.agent_id), created])
      setSelectedAgentId(created.agent_id)
      setCreateMode(false)
      setCreateDraft(emptyCreateDraft)
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

  const handleDeleteTerminal = async () => {
    if (!pendingClose) return
    setClosingTerminal(pendingClose.id)
    try {
      await api.deleteTerminal(pendingClose.id)
      if (liveTerminal?.id === pendingClose.id) setLiveTerminal(null)
      if (activeSession) await selectSession(activeSession)
      refreshAgents()
      showSnackbar({ type: 'success', message: `Terminal ${pendingClose.id} closed` })
    } catch {
      showSnackbar({ type: 'error', message: `Failed to close terminal ${pendingClose.id}` })
    } finally {
      setClosingTerminal(null)
      setPendingClose(null)
    }
  }

  const handleSendInput = async (terminalId: string) => {
    const message = (sendInputValues[terminalId] || '').trim()
    if (!message) return
    setSendingInput(terminalId)
    try {
      await api.sendInput(terminalId, message)
      setSendInputValues(prev => ({ ...prev, [terminalId]: '' }))
    } catch {
      showSnackbar({ type: 'error', message: `Failed to send message to terminal ${terminalId}` })
    } finally {
      setSendingInput(null)
    }
  }

  return (
    <div className="space-y-6">
      <AgentTimelinePanel onFocusTerminal={focusTimelineTerminal} />

      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Agents ({agents.length})</h3>
          </div>
          {agents.length === 0 ? (
            <p className="text-gray-500 text-sm">No agents configured.</p>
          ) : (
            <div className="space-y-2">
              {agents.map(agent => (
                <button
                  key={agent.agent_id}
                  type="button"
                  onClick={() => setSelectedAgentId(agent.agent_id)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${selectedAgent?.agent_id === agent.agent_id ? 'bg-emerald-900/30 border-emerald-700/50' : 'bg-gray-900/50 border-gray-700/30 hover:bg-gray-800/80'}`}
                >
                  <span className="block text-sm text-gray-200">{agent.display_name}</span>
                  <span className="block text-xs text-gray-500 font-mono">{agent.agent_id} · {agent.cli_provider}</span>
                  <span className={`mt-2 inline-flex text-xs px-2 py-0.5 rounded-full ${agent.active ? 'bg-emerald-900/50 text-emerald-300' : 'bg-gray-700/70 text-gray-300'}`}>
                    {agent.active ? `Running ${agent.active_terminal_id ?? ''}`.trim() : 'Stopped'}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-4 min-w-0">
          {selectedAgent ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">agent.toml</h3>
                  <p className="text-xs text-gray-500 mt-1">{selectedAgent.display_name} · {selectedAgent.active ? `Running in ${selectedAgent.active_terminal_id}` : 'Stopped'}</p>
                </div>
                {editingAgentId === selectedAgent.agent_id ? (
                  <div className="flex items-center gap-2">
                    <button onClick={() => handleSaveAgent(selectedAgent)} disabled={savingAgentId === selectedAgent.agent_id} className="flex items-center gap-2 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-medium rounded-lg transition-colors" aria-label={`Save ${selectedAgent.agent_id}`}>
                      <Save size={13} /> Save
                    </button>
                    <button onClick={() => setEditingAgentId(null)} className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-medium rounded-lg transition-colors" aria-label={`Cancel ${selectedAgent.agent_id}`}>
                      <RotateCcw size={13} /> Cancel
                    </button>
                  </div>
                ) : (
                  <button onClick={() => handleEditAgent(selectedAgent)} className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-medium rounded-lg transition-colors" aria-label={`Edit ${selectedAgent.agent_id}`}>
                    <Edit3 size={13} /> Edit
                  </button>
                )}
              </div>
              {editingAgentId === selectedAgent.agent_id ? (
                <textarea
                  aria-label={`${selectedAgent.agent_id} agent.toml`}
                  value={agentTomlDraft}
                  onChange={event => setAgentTomlDraft(event.target.value)}
                  className="w-full min-h-[360px] resize-y rounded-lg border border-gray-700 bg-gray-950 p-3 font-mono text-xs leading-5 text-gray-200 focus:border-emerald-500 focus:outline-none"
                />
              ) : (
                <pre className="max-h-[460px] overflow-auto rounded-lg border border-gray-700/50 bg-gray-950 p-3 font-mono text-xs leading-5 text-gray-200 whitespace-pre-wrap">{formatAgentToml(selectedAgent.config)}</pre>
              )}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Select an agent to view its config.</p>
          )}
        </div>
      </div>

      <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Sessions ({sessions.length})</h3>
          <button onClick={() => setShowSpawnModal(true)} className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
            <Plus size={14} /> Spawn Agent
          </button>
        </div>
        {sessions.length === 0 ? (
          <p className="text-gray-500 text-sm">No active sessions. Start an agent to create one.</p>
        ) : (
          <div className="space-y-2">
            {sessions.map(s => (
              <div key={s.id} className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${activeSession === s.id ? 'bg-emerald-900/30 border border-emerald-700/50' : 'bg-gray-900/50 border border-gray-700/30 hover:bg-gray-800/80'}`} onClick={() => selectSession(activeSession === s.id ? null : s.id)}>
                <div className="flex items-center gap-3">
                  <Bot size={16} className="text-emerald-400" />
                  <span className="text-sm text-gray-200 font-mono">{s.id}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-900/50 text-emerald-400">{s.status}</span>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={e => { e.stopPropagation(); deleteSession(s.id) }} className="p-1.5 text-gray-500 hover:text-red-400 transition-colors rounded" title="Delete session">
                    <Trash2 size={14} />
                  </button>
                  <ChevronRight size={14} className={`text-gray-500 transition-transform ${activeSession === s.id ? 'rotate-90' : ''}`} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {activeSessionDetail && (
        <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-4">Terminals in {activeSession}</h3>
          <div className="space-y-2">
            {activeSessionDetail.terminals.map(t => (
              <div key={t.id} className="bg-gray-900/50 border border-gray-700/30 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <TermIcon size={14} className="text-gray-400" />
                    <span className="text-sm font-mono text-gray-300">{t.id}</span>
                    <StatusBadge status={terminalStatuses[t.id] || null} />
                    <MonitoringIndicator terminalId={t.id} />
                    <BatonIndicator terminalId={t.id} />
                    <span className="text-xs text-gray-500">{t.provider}</span>
                    <span className="text-xs text-emerald-400">{t.agent_id}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <MonitoringButton terminalId={t.id} />
                    <button onClick={() => setInboxTerminalId(t.id)} aria-label={`Open inbox ${t.id}`} className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-medium rounded-lg transition-colors"><Mail size={14} />Inbox</button>
                    <button onClick={() => openTerminal(t.id, t.provider, t.agent_id, t.terminal_token)} aria-label={`Open terminal ${t.id}`} className="flex items-center gap-2 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-colors"><Monitor size={14} />Open</button>
                    <button onClick={() => setOutputTerminalId(t.id)} aria-label={`Open output ${t.id}`} className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-medium rounded-lg transition-colors"><FileText size={14} />Output</button>
                    <button onClick={() => setPendingClose(t as TerminalMeta)} disabled={closingTerminal === t.id} className="flex items-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white text-xs font-medium rounded-lg transition-colors"><Trash2 size={14} />Close</button>
                  </div>
                </div>
                {!sendInputOpen[t.id] ? (
                  <button onClick={() => setSendInputOpen(prev => ({ ...prev, [t.id]: true }))} className="text-xs text-gray-500 hover:text-gray-300 transition-colors">Message agent...</button>
                ) : (
                  <div className="flex items-center gap-2">
                    <input value={sendInputValues[t.id] || ''} onChange={e => setSendInputValues(prev => ({ ...prev, [t.id]: e.target.value }))} onKeyDown={e => { if (e.key === 'Enter') handleSendInput(t.id) }} placeholder="Type a message..." className="flex-1 bg-gray-900 border border-gray-700 text-gray-200 text-sm font-mono rounded-lg px-3 py-1.5 focus:border-emerald-500 focus:outline-none" autoFocus />
                    <button onClick={() => handleSendInput(t.id)} disabled={sendingInput === t.id || !(sendInputValues[t.id] || '').trim()} className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-medium rounded-lg transition-colors"><Send size={12} />Send</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {inboxTerminalId && <InboxPanel terminalId={inboxTerminalId} onClose={() => setInboxTerminalId(null)} />}
      {liveTerminal && <TerminalView terminalId={liveTerminal.id} provider={liveTerminal.provider} agentId={liveTerminal.agentId} terminalToken={liveTerminal.terminalToken} onClose={() => setLiveTerminal(null)} />}
      {outputTerminalId && <OutputViewer terminalId={outputTerminalId} onClose={() => setOutputTerminalId(null)} />}

      <ConfirmModal
        open={!!pendingClose}
        title="Close Terminal"
        message="This will kill the tmux window and terminate the agent process. This action cannot be undone."
        details={pendingClose ? [
          { label: 'Terminal ID', value: pendingClose.id },
          { label: 'Provider', value: pendingClose.provider },
          { label: 'Agent', value: pendingClose.agent_id },
          { label: 'Session', value: pendingClose.tmux_session },
        ] : []}
        confirmLabel="Close Terminal"
        variant="danger"
        loading={!!closingTerminal}
        onConfirm={handleDeleteTerminal}
        onCancel={() => setPendingClose(null)}
      />

      {showSpawnModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowSpawnModal(false)} />
          <div className="relative bg-gray-800 border border-gray-700 rounded-2xl shadow-2xl shadow-black/50 w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b border-gray-700/50">
              <h3 className="text-base font-semibold text-gray-200">Spawn Agent</h3>
              <button onClick={() => setShowSpawnModal(false)} className="p-1.5 text-gray-500 hover:text-gray-300 transition-colors rounded-lg hover:bg-gray-700/50"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-2">
              <button
                type="button"
                onClick={() => setCreateMode(previous => !previous)}
                className="w-full flex items-center justify-between p-3 rounded-lg bg-gray-900/50 border border-emerald-700/50 hover:bg-gray-800/80 transition-colors"
              >
                <span className="text-left">
                  <span className="block text-sm text-gray-200">Create new agent</span>
                  <span className="block text-xs text-gray-500">Add a durable agent before starting it.</span>
                </span>
                <Plus size={15} className="text-emerald-300" />
              </button>
              {createMode && (
                <div className="rounded-lg border border-gray-700/50 bg-gray-900/60 p-3 space-y-3">
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
                    <input value={createDraft.cli_provider} onChange={event => setCreateDraft(previous => ({ ...previous, cli_provider: event.target.value }))} className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none" />
                  </label>
                  <label className="block text-xs text-gray-400">
                    Workdir
                    <input value={createDraft.workdir} onChange={event => setCreateDraft(previous => ({ ...previous, workdir: event.target.value }))} className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none" />
                  </label>
                  <button onClick={handleCreateAgent} disabled={creatingAgent || !createDraft.id.trim()} className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium rounded-lg transition-colors">
                    <Plus size={14} /> {creatingAgent ? 'Creating...' : 'Create Agent'}
                  </button>
                </div>
              )}
              {agents.map(agent => (
                <button
                  key={agent.agent_id}
                  onClick={() => !agent.active && handleStartAgent(agent.agent_id)}
                  disabled={agent.active || startingAgentId === agent.agent_id}
                  title={agent.active ? `Already running: ${agent.active_terminal_id}` : `Start ${agent.agent_id}`}
                  className="w-full flex items-center justify-between p-3 rounded-lg bg-gray-900/50 border border-gray-700/30 hover:bg-gray-800/80 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <span className="text-left">
                    <span className="block text-sm text-gray-200">{agent.display_name}</span>
                    <span className="block text-xs text-gray-500 font-mono">{agent.agent_id} · {agent.cli_provider}</span>
                  </span>
                  <span className="flex items-center gap-2 text-xs text-gray-400">
                    {agent.active ? 'Running' : startingAgentId === agent.agent_id ? 'Starting...' : 'Start'}
                    <Play size={14} />
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

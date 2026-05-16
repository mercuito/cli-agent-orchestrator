const BASE = ''  // Vite proxy handles routing to backend

async function fetchJSON<T>(url: string, opts?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), opts?.timeoutMs ?? 10000)
  try {
    const res = await fetch(`${BASE}${url}`, { ...opts, signal: controller.signal })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  } finally {
    clearTimeout(timeout)
  }
}

export interface Session {
  id: string
  name: string
  status: string
}

export interface Terminal {
  id: string
  name: string
  provider: string
  session_name: string
  agent_profile: string | null
  agent_identity_id: string | null
  status: string | null
  last_active: string | null
}

export interface SessionDetail {
  session: Session
  terminals: TerminalMeta[]
}

export interface TerminalMeta {
  id: string
  tmux_session: string
  tmux_window: string
  provider: string
  agent_profile: string | null
  agent_identity_id: string | null
  terminal_token?: string | null
  last_active: string | null
}

export interface AgentRuntimeTerminalLink {
  terminal: Terminal
  terminal_token: string
}

export interface AgentConfig {
  id: string
  display_name: string
  cli_provider: string
  workdir: string
  session_name: string
  prompt: string
  description: string | null
  model: string | null
  reasoning_effort: string | null
  mcp_servers: Record<string, unknown>
  tools: string[]
  tool_aliases: Record<string, string>
  tools_settings: Record<string, unknown>
  cao_tools: string[] | null
  skills: string[]
  tags: string[]
  resources: string[]
  hooks: Record<string, unknown>
  use_legacy_mcp_json: boolean | null
  runtime_capabilities: string[] | null
  codex_config: Record<string, unknown>
  workspace_context: { enabled: boolean; resolver_id: string | null }
  linear: {
    app_key: string | null
    client_id: string | null
    client_secret_configured: boolean
    webhook_secret_configured: boolean
    oauth_redirect_uri: string | null
    access_token_configured: boolean
    refresh_token_configured: boolean
    token_expires_at: string | null
    app_user_id: string | null
    app_user_name: string | null
    oauth_state_configured: boolean
    tool_access: Array<{
      access_id: string
      tools: string[]
      issues: string[]
      create_team_ids: string[]
      create_project_ids: string[]
      create_parent_issues: string[]
      allow_top_level_create: boolean
      update_fields: string[]
      reason: string | null
    }>
  } | null
}

export interface AgentStatus {
  agent_id: string
  display_name: string
  cli_provider: string
  workdir: string
  session_name: string
  config: AgentConfig
  active: boolean
  active_terminal_id: string | null
  active_workspace_context_id: string | null
  last_active_at: string | null
}

export interface AgentTimelineEvent {
  event_id: string
  event_name: string
  event_type_key: string
  source_type: string
  source_id: string
  occurred_at: string
  correlation_id: string | null
  causation_id: string | null
  event_data: Record<string, unknown>
  participant_role: string | null
}

export interface AgentTimeline {
  agent: AgentStatus
  events: AgentTimelineEvent[]
}

export interface AgentCausationRelatedEvents {
  direct_cause: AgentTimelineEvent | null
  direct_effects: AgentTimelineEvent[]
}

export interface AgentRelatedEvents {
  event: AgentTimelineEvent
  correlation_events: AgentTimelineEvent[]
  causation_events: AgentCausationRelatedEvents
}

export interface AgentProfileInfo {
  name: string
  description: string
  source: 'built-in' | 'local' | 'kiro' | 'q_cli'
}

export interface AgentDirsSettings {
  agent_dirs: Record<string, string>
  extra_dirs: string[]
}

export interface InboxMessage {
  id: string
  sender_id: string
  receiver_id: string
  message: string
  source_kind: string | null
  source_id: string | null
  status: 'pending' | 'delivered' | 'failed'
  created_at: string | null
}

export interface Flow {
  name: string
  file_path: string
  schedule: string
  agent_profile: string
  provider: string
  script: string | null
  last_run: string | null
  next_run: string | null
  enabled: boolean
  prompt_template: string | null
}

export interface ProviderInfo {
  name: string
  binary: string
  installed: boolean
}

export interface MonitoringSession {
  id: string
  terminal_id: string
  label: string | null
  started_at: string
  ended_at: string | null
  status: 'active' | 'ended'
}

export interface Baton {
  id: string
  title: string
  status: 'active' | 'completed' | 'blocked' | 'canceled' | 'orphaned'
  originator_id: string
  current_holder_id: string | null
  return_stack: string[]
  expected_next_action: string | null
  created_at: string
  updated_at: string
  last_nudged_at: string | null
  completed_at: string | null
}

export interface BatonEvent {
  event_type: string
  actor_id: string
  from_holder_id: string | null
  to_holder_id: string | null
  message: string | null
  created_at: string
}

export const api = {
  // Agent Profiles & Providers
  listProfiles: () => fetchJSON<AgentProfileInfo[]>('/agents/profiles'),
  listProviders: () => fetchJSON<ProviderInfo[]>('/agents/providers'),

  // Settings
  getAgentDirs: () => fetchJSON<AgentDirsSettings>('/settings/agent-dirs'),
  setAgentDirs: (data: { agent_dirs?: Record<string, string>; extra_dirs?: string[] }) =>
    fetchJSON<AgentDirsSettings>('/settings/agent-dirs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  // Sessions
  listSessions: () => fetchJSON<Session[]>('/sessions'),
  getSession: (name: string) => fetchJSON<SessionDetail>(`/sessions/${name}`),
  createSession: (provider: string, agentProfile: string, sessionName?: string, workingDirectory?: string) =>
    fetchJSON<Terminal>(`/sessions?provider=${provider}&agent_profile=${agentProfile}${sessionName ? `&session_name=${sessionName}` : ''}${workingDirectory ? `&working_directory=${encodeURIComponent(workingDirectory)}` : ''}`, { method: 'POST', timeoutMs: 90000 }),
  deleteSession: (name: string) => fetchJSON<{ success: boolean; deleted: string[]; errors: any[] }>(`/sessions/${name}`, { method: 'DELETE' }),

  // Terminals
  getTerminal: (id: string) => fetchJSON<Terminal>(`/terminals/${id}`),
  getAgentRuntimeTerminal: (agentId: string, agentToken?: string | null) => {
    const query = agentToken ? `?agent_token=${encodeURIComponent(agentToken)}` : ''
    return fetchJSON<AgentRuntimeTerminalLink>(
      `/agents/runtime/${encodeURIComponent(agentId)}/terminal${query}`,
    )
  },
  listAgents: () => fetchJSON<AgentStatus[]>('/agents'),
  getAgentTimeline: (agentId: string) =>
    fetchJSON<AgentTimeline>(
      `/agents/${encodeURIComponent(agentId)}/timeline`,
    ),
  getAgentRelatedEvents: (agentId: string, eventId: string) =>
    fetchJSON<AgentRelatedEvents>(
      `/agents/${encodeURIComponent(agentId)}/events/${encodeURIComponent(eventId)}/related`,
    ),
  getTerminalStatus: (id: string) =>
    fetchJSON<Terminal>(`/terminals/${id}`).then(t => t.status),
  getTerminalOutput: (id: string, mode: 'full' | 'last' = 'full') =>
    fetchJSON<{ output: string; mode: string }>(`/terminals/${id}/output?mode=${mode}`),
  sendInput: (id: string, message: string) =>
    fetchJSON<{ success: boolean }>(`/terminals/${id}/input?message=${encodeURIComponent(message)}`, { method: 'POST' }),
  exitTerminal: (id: string) =>
    fetchJSON<{ success: boolean }>(`/terminals/${id}/exit`, { method: 'POST' }),
  deleteTerminal: (id: string) => fetchJSON<{ success: boolean }>(`/terminals/${id}`, { method: 'DELETE' }),
  getWorkingDirectory: (id: string) =>
    fetchJSON<{ working_directory: string | null }>(`/terminals/${id}/working-directory`),
  addTerminalToSession: (sessionName: string, provider: string, agentProfile: string, workingDirectory?: string) =>
    fetchJSON<Terminal>(`/sessions/${sessionName}/terminals?provider=${provider}&agent_profile=${agentProfile}${workingDirectory ? `&working_directory=${encodeURIComponent(workingDirectory)}` : ''}`, { method: 'POST', timeoutMs: 90000 }),

  // Inbox
  getInboxMessages: (terminalId: string, limit?: number, status?: string) =>
    fetchJSON<InboxMessage[]>(`/terminals/${terminalId}/inbox/messages?limit=${limit || 50}${status ? `&status=${status}` : ''}`),
  sendInboxMessage: (receiverId: string, senderId: string, message: string) =>
    fetchJSON<{ success: boolean }>(`/terminals/${receiverId}/inbox/messages?sender_id=${senderId}&message=${encodeURIComponent(message)}`, { method: 'POST' }),

  // Monitoring
  listActiveMonitoringSessions: () =>
    fetchJSON<MonitoringSession[]>('/monitoring/sessions?status=active'),
  startMonitoring: (terminalId: string, label?: string) =>
    fetchJSON<MonitoringSession>('/monitoring/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        terminal_id: terminalId,
        label: label ?? null,
      }),
    }),
  endMonitoring: (sessionId: string) =>
    fetchJSON<MonitoringSession>(`/monitoring/sessions/${sessionId}/end`, {
      method: 'POST',
    }),

  // Batons
  listActiveBatons: async () => {
    try {
      return await fetchJSON<Baton[]>('/batons')
    } catch (error) {
      if (error instanceof Error && error.message.startsWith('404 ')) return []
      throw error
    }
  },
  getBaton: (id: string) => fetchJSON<Baton>(`/batons/${id}`),
  listBatonEvents: (id: string) => fetchJSON<BatonEvent[]>(`/batons/${id}/events`),

  // Flows
  listFlows: () => fetchJSON<Flow[]>('/flows'),
  createFlow: (data: { name: string; schedule: string; agent_profile: string; provider?: string; prompt_template: string }) =>
    fetchJSON<Flow>('/flows', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      timeoutMs: 30000,
    }),
  deleteFlow: (name: string) => fetchJSON<{ success: boolean }>(`/flows/${name}`, { method: 'DELETE' }),
  enableFlow: (name: string) => fetchJSON<{ success: boolean }>(`/flows/${name}/enable`, { method: 'POST' }),
  disableFlow: (name: string) => fetchJSON<{ success: boolean }>(`/flows/${name}/disable`, { method: 'POST' }),
  runFlow: (name: string) => fetchJSON<{ executed: boolean }>(`/flows/${name}/run`, { method: 'POST', timeoutMs: 90000 }),
}

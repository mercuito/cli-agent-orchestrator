const BASE = ''  // Vite proxy handles routing to backend

async function fetchJSON<T>(url: string, opts?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), opts?.timeoutMs ?? 10000)
  try {
    const res = await fetch(`${BASE}${url}`, { ...opts, signal: controller.signal })
    if (!res.ok) {
      let detail = ''
      try {
        const body = await res.json()
        detail = typeof body?.detail === 'string' ? body.detail : ''
      } catch {
        detail = ''
      }
      throw new Error(`${res.status} ${res.statusText}${detail ? `: ${detail}` : ''}`)
    }
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
  agent_id: string
  workspace_context_id: string
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
  agent_id: string
  workspace_context_id: string
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
  workspace: { team: string | null; derived_workspace: string | null; diagnostics: string[] }
}

export interface McpToolSurface {
  schema_version: string
  tools: Array<{
    source: { kind: string; name: string }
    name: string
    description: string
  }>
}

export interface EffectiveToolAccess {
  agent_id: string
  team_id: string | null
  role_id: string | null
  registered_tools: string[]
  allowed_tools: string[]
  blocked_tools: string[]
  built_in_cao_tools: string[]
  provider_mediated_tools: Record<string, string[]>
  materialized_mcp_servers: Record<string, unknown>
  runtime_capabilities: string[]
  source_markers: Record<string, string>
  inactive_local_grants: Record<string, unknown>
  diagnostics: Array<{ code: string; message: string; source: string }>
}

export interface AgentStatus {
  agent_id: string
  display_name: string
  cli_provider: string
  workdir: string
  session_name: string
  config: AgentConfig
  active: boolean
  agent_dashboard_token?: string | null
  active_terminal_id: string | null
  active_workspace_context_id: string | null
  workspace_team_id?: string | null
  derived_workspace_id?: string | null
  workspace_team_diagnostics?: string[]
  mcp_tool_surface?: McpToolSurface
  effective_tool_access?: EffectiveToolAccess
  last_active_at: string | null
}

export interface WorkspaceDiagnostic {
  code: string
  message: string
  team_id: string | null
  workspace_id: string | null
  agent_id: string | null
  provider_name: string | null
}

export interface Workspace {
  id: string
  display_name: string
  providers: string[]
}

export interface WorkspaceTeam {
  id: string
  display_name: string
  workspace: string
  roles: Record<string, WorkspaceTeamRole>
  role_assignments: Record<string, string>
  members: string[]
  member_details: WorkspaceTeamMemberDetail[]
  diagnostics: string[]
}

export interface WorkspaceTeamMemberDetail {
  agent_id: string
  display_name: string
  role_id: string
  role_explicitly_assigned: boolean
}

export interface WorkspaceTeamRole {
  display_name: string
  cao_tools: string[]
  mcp_servers: Record<string, unknown>
  providers: Record<string, Record<string, Record<string, unknown>>>
  deletable?: boolean
}

export interface ToolDescriptor {
  name: string
  description: string
}

export interface AgentWriteRequest {
  id?: string
  display_name?: string
  cli_provider?: string
  workdir?: string
  session_name?: string
  prompt?: string
  description?: string | null
  model?: string | null
  reasoning_effort?: string | null
  mcp_servers?: Record<string, unknown>
  tools?: string[]
  tool_aliases?: Record<string, string>
  tools_settings?: Record<string, unknown>
  cao_tools?: string[] | null
  skills?: string[]
  tags?: string[]
  resources?: string[]
  hooks?: Record<string, unknown>
  use_legacy_mcp_json?: boolean | null
  runtime_capabilities?: string[] | null
  codex_config?: Record<string, unknown>
  workspace?: { team?: string | null }
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

export interface InboxMessage {
  notification_id: number
  sender_agent_id: string
  receiver_agent_id: string
  body: string
  status: 'pending' | 'delivered' | 'failed'
  created_at: string | null
}

export interface Flow {
  name: string
  file_path: string
  schedule: string
  agent_id: string
  provider: string
  script: string | null
  last_run: string | null
  next_run: string | null
  enabled: boolean
  prompt_template: string | null
}

export interface MonitoringSession {
  id: string
  agent_id: string
  label: string | null
  started_at: string
  ended_at: string | null
  status: 'active' | 'ended'
}

/**
 * Capability schema for one CAO-registered provider, as returned by
 * ``GET /providers``. Mirrors the backend's ``ProviderSchemaResponse``
 * model exactly — the dashboard must not re-derive these fields from
 * literal strings (per ``authoritative-sources-are-referenced-not-copied``).
 */
export interface ProviderSchema {
  name: string
  binary: string
  installed: boolean
  model_catalog_available: boolean
}

export interface ProviderModel {
  id: string
  display_name: string
  reasoning_efforts: string[]
  thinking_supported: boolean
  max_input_tokens: number | null
  max_output_tokens: number | null
}

export interface ProviderCatalog {
  provider_type: string
  models: ProviderModel[]
  discovered_at: string
  source: string
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
  // Providers (capability schema for dashboard forms)
  listProviders: () => fetchJSON<ProviderSchema[]>('/providers'),
  getProviderCatalog: (provider: string) => fetchJSON<ProviderCatalog>(`/providers/${encodeURIComponent(provider)}/catalog`),

  // Sessions
  listSessions: () => fetchJSON<Session[]>('/sessions'),
  getSession: (name: string) => fetchJSON<SessionDetail>(`/sessions/${name}`),
  deleteSession: (name: string) => fetchJSON<{ success: boolean; deleted: string[]; errors: any[] }>(`/sessions/${name}`, { method: 'DELETE' }),

  // Terminals
  getTerminal: (id: string) => fetchJSON<Terminal>(`/terminals/${id}`),
  startAgent: (agentId: string) =>
    fetchJSON<AgentRuntimeTerminalLink>(`/agents/${encodeURIComponent(agentId)}/start`, {
      method: 'POST',
      timeoutMs: 90000,
    }),
  stopAgent: (agentId: string) =>
    fetchJSON<{ success: boolean }>(`/agents/${encodeURIComponent(agentId)}/stop`, {
      method: 'POST',
      timeoutMs: 30000,
    }),
  getAgentRuntimeTerminal: (agentId: string, agentToken?: string | null) => {
    const query = agentToken ? `?agent_token=${encodeURIComponent(agentToken)}` : ''
    return fetchJSON<AgentRuntimeTerminalLink>(
      `/agents/runtime/${encodeURIComponent(agentId)}/terminal${query}`,
    )
  },
  listAgents: () => fetchJSON<AgentStatus[]>('/agents', { timeoutMs: 30000 }),
  listWorkspaceDiagnostics: () => fetchJSON<WorkspaceDiagnostic[]>('/workspaces/diagnostics'),
  listWorkspaces: () => fetchJSON<Workspace[]>('/workspaces'),
  listWorkspaceTeams: () => fetchJSON<WorkspaceTeam[]>('/workspace-teams'),
  listCaoToolDescriptors: () => fetchJSON<ToolDescriptor[]>('/cao-tools/descriptors'),
  createWorkspaceTeam: (team: { id: string; display_name: string; workspace: string }) =>
    fetchJSON<WorkspaceTeam>('/workspace-teams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(team),
    }),
  updateWorkspaceTeamMetadata: (teamId: string, metadata: { display_name: string; workspace: string }) =>
    fetchJSON<WorkspaceTeam>(`/workspace-teams/${encodeURIComponent(teamId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(metadata),
    }),
  deleteWorkspaceTeam: (teamId: string) =>
    fetchJSON<WorkspaceTeam>(`/workspace-teams/${encodeURIComponent(teamId)}`, {
      method: 'DELETE',
    }),
  putWorkspaceTeamRole: (teamId: string, roleId: string, role: WorkspaceTeamRole) =>
    fetchJSON<WorkspaceTeam>(
      `/workspace-teams/${encodeURIComponent(teamId)}/roles/${encodeURIComponent(roleId)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(role),
      },
    ),
  deleteWorkspaceTeamRole: (teamId: string, roleId: string) =>
    fetchJSON<WorkspaceTeam>(
      `/workspace-teams/${encodeURIComponent(teamId)}/roles/${encodeURIComponent(roleId)}`,
      {
        method: 'DELETE',
      },
    ),
  putWorkspaceTeamMember: (teamId: string, agentId: string, body: { role_id?: string | null } = {}) =>
    fetchJSON<WorkspaceTeam>(
      `/workspace-teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(agentId)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    ),
  deleteWorkspaceTeamMember: (teamId: string, agentId: string) =>
    fetchJSON<WorkspaceTeam>(
      `/workspace-teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(agentId)}`,
      {
        method: 'DELETE',
      },
    ),
  createAgent: (agent: AgentWriteRequest) =>
    fetchJSON<AgentStatus>('/agents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agent),
    }),
  updateAgent: (agentId: string, agent: AgentWriteRequest) =>
    fetchJSON<AgentStatus>(`/agents/${encodeURIComponent(agentId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agent),
    }),
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

  // Inbox
  getInboxMessages: (agentId: string, limit?: number, status?: string) =>
    fetchJSON<InboxMessage[]>(`/agents/${encodeURIComponent(agentId)}/inbox/messages?limit=${limit || 50}${status ? `&status=${status}` : ''}`),
  sendInboxMessage: (receiverAgentId: string, senderAgentId: string, message: string) =>
    fetchJSON<{ success: boolean }>(`/agents/${encodeURIComponent(receiverAgentId)}/inbox/messages?sender_agent_id=${encodeURIComponent(senderAgentId)}&body=${encodeURIComponent(message)}`, { method: 'POST' }),

  // Monitoring
  listActiveMonitoringSessions: () =>
    fetchJSON<MonitoringSession[]>('/monitoring/sessions?status=active'),
  startMonitoring: (agentId: string, label?: string) =>
    fetchJSON<MonitoringSession>('/monitoring/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_id: agentId,
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
  createFlow: (data: { name: string; schedule: string; agent_id: string; provider?: string; prompt_template: string }) =>
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

import type {
  AgentStatus,
  ProviderRoleAccessSchema,
  ToolDescriptor,
  WorkspaceSetup,
  WorkspaceTeam,
  WorkspaceTeamRole,
} from '../../api'

export interface ToolOption {
  key: string
  name: string
  description: string
  category: 'cao' | 'mcp' | 'provider'
  pill: string
  provider?: string
  mcpServerConfig?: Record<string, unknown>
}

export interface TeamsDataProps {
  teams: WorkspaceTeam[]
  selectedTeam: WorkspaceTeam | null
  setups: WorkspaceSetup[]
  agents: AgentStatus[]
  caoTools: ToolDescriptor[]
  providerSchemas: Record<string, ProviderRoleAccessSchema>
}

export type TeamMutator = (team: WorkspaceTeam) => void

export type RoleMutator = (role: WorkspaceTeamRole) => WorkspaceTeamRole

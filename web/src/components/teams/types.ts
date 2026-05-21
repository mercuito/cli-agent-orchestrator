import type {
  AgentStatus,
  ToolDescriptor,
  Workspace,
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
  workspaces: Workspace[]
  agents: AgentStatus[]
  caoTools: ToolDescriptor[]
}

export type TeamMutator = (team: WorkspaceTeam) => void

export type RoleMutator = (role: WorkspaceTeamRole) => WorkspaceTeamRole

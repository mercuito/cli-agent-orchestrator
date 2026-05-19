import type {
  AgentStatus,
  ProviderRoleAccessSchema,
  ToolDescriptor,
  WorkspaceSetup,
  WorkspaceTeam,
  WorkspaceTeamRole,
} from '../../api'
import type { ToolOption } from './types'

export const fallbackRoleId = 'member'

export function defaultMemberRole(): WorkspaceTeamRole {
  return {
    display_name: 'Member',
    cao_tools: [],
    mcp_servers: {},
    providers: {},
    deletable: false,
  }
}

export function displayAgentId(agent: AgentStatus) {
  return agent.agent_id || agent.config?.id || agent.display_name
}

export function roleDisplayName(roleId: string, role: WorkspaceTeamRole) {
  return role.display_name?.trim() || titleize(roleId)
}

export function titleize(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function roleMemberCount(team: WorkspaceTeam, roleId: string) {
  return team.member_details.filter(member => member.role_id === roleId).length
}

export function roleToolNames(role: WorkspaceTeamRole) {
  const providerTools = Object.values(role.providers || {}).flatMap(grants =>
    Object.values(grants).flatMap(grant => stringArray(grant.tools)),
  )
  return [...role.cao_tools, ...Object.keys(role.mcp_servers || {}), ...providerTools]
}

export function buildToolOptions(
  caoTools: ToolDescriptor[],
  agents: AgentStatus[],
  setup: WorkspaceSetup | undefined,
  providerSchemas: Record<string, ProviderRoleAccessSchema>,
): ToolOption[] {
  const options = new Map<string, ToolOption>()

  caoTools.forEach(tool => {
    options.set(`cao:${tool.name}`, {
      key: `cao:${tool.name}`,
      name: tool.name,
      description: tool.description,
      category: 'cao',
      pill: 'CAO',
    })
  })

  agents.forEach(agent => {
    Object.entries(mcpServersForAgent(agent)).forEach(([name, config]) => {
      if (!options.has(`mcp:${name}`)) {
        options.set(`mcp:${name}`, {
          key: `mcp:${name}`,
          name,
          description: 'Configured MCP server',
          category: 'mcp',
          pill: 'MCP',
          mcpServerConfig: config,
        })
      }
    })
  })

  setup?.providers.forEach(provider => {
    providerSchemas[provider]?.tools.forEach(tool => {
      options.set(`provider:${provider}:${tool.name}`, {
        key: `provider:${provider}:${tool.name}`,
        name: tool.name,
        description: tool.description || `${titleize(provider)} workspace provider`,
        category: 'provider',
        pill: titleize(provider),
        provider,
      })
    })
  })

  return Array.from(options.values()).sort((left, right) =>
    `${left.pill}:${left.name}`.localeCompare(`${right.pill}:${right.name}`),
  )
}

export function isToolEnabled(role: WorkspaceTeamRole, option: ToolOption) {
  if (option.category === 'cao') return role.cao_tools.includes(option.name)
  if (option.category === 'mcp') return Object.prototype.hasOwnProperty.call(role.mcp_servers, option.name)
  const grant = option.provider ? role.providers[option.provider]?.default : undefined
  return stringArray(grant?.tools).includes(option.name)
}

export function toggleTool(role: WorkspaceTeamRole, option: ToolOption, enabled: boolean): WorkspaceTeamRole {
  if (option.category === 'cao') {
    return {
      ...role,
      cao_tools: enabled
        ? uniqueStrings([...role.cao_tools, option.name])
        : role.cao_tools.filter(tool => tool !== option.name),
    }
  }

  if (option.category === 'mcp') {
    const nextServers = { ...(role.mcp_servers || {}) }
    if (enabled) nextServers[option.name] = option.mcpServerConfig ?? {}
    else delete nextServers[option.name]
    return { ...role, mcp_servers: nextServers }
  }

  if (!option.provider) return role
  const providerGrants = role.providers[option.provider] || {}
  const grant = providerGrants.default || { tools: [] }
  const nextTools = enabled
    ? uniqueStrings([...stringArray(grant.tools), option.name])
    : stringArray(grant.tools).filter(tool => tool !== option.name)
  const nextProviders: WorkspaceTeamRole['providers'] = {
    ...role.providers,
    [option.provider]: {
      ...providerGrants,
      default: { ...grant, tools: nextTools },
    },
  }
  if (nextTools.length === 0) {
    delete nextProviders[option.provider].default
    if (Object.keys(nextProviders[option.provider]).length === 0) delete nextProviders[option.provider]
  }
  return { ...role, providers: nextProviders }
}

function mcpServersForAgent(agent: AgentStatus) {
  const servers: Record<string, Record<string, unknown>> = {}
  Object.entries(mappingValue(agent.config?.mcp_servers)).forEach(([name, config]) => {
    servers[name] = config
  })
  Object.entries(mappingValue(agent.config?.codex_config?.mcp_servers)).forEach(([name, config]) => {
    servers[name] = config
  })
  return servers
}

function mappingValue(value: unknown): Record<string, Record<string, unknown>> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return Object.fromEntries(
    Object.entries(value).filter(([, entry]) => entry && typeof entry === 'object' && !Array.isArray(entry)),
  ) as Record<string, Record<string, unknown>>
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter(item => typeof item === 'string') : []
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values))
}

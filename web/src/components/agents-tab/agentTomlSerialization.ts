import type { AgentConfig, AgentWriteRequest } from '../../api'

function quoteTomlString(value: string): string {
  return `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t')}"`
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

/**
 * Render an ``agent.toml`` view, omitting the named top-level keys plus
 * the always-immutable ``id`` field. Used by the Config tab's raw-TOML
 * section to suppress fields owned by the structured form (and ``id``,
 * which is owned by the directory name and never editable).
 */
export function formatAgentTomlExcluding(
  config: AgentConfig,
  excludedKeys: ReadonlyArray<string>,
): string {
  return renderAgentToml(config, new Set(['id', ...excludedKeys]))
}

function renderAgentToml(config: AgentConfig, exclude: Set<string>): string {
  const lines: string[] = []
  if (!exclude.has('id')) appendValue(lines, 'id', config.id)
  if (!exclude.has('display_name')) appendValue(lines, 'display_name', config.display_name)
  if (!exclude.has('cli_provider')) appendValue(lines, 'cli_provider', config.cli_provider)
  appendValue(lines, 'workdir', config.workdir)
  appendValue(lines, 'session_name', config.session_name)
  if (!exclude.has('model')) appendValue(lines, 'model', config.model)
  if (!exclude.has('description')) appendValue(lines, 'description', config.description)
  if (!exclude.has('reasoning_effort'))
    appendValue(lines, 'reasoning_effort', config.reasoning_effort)
  appendValue(lines, 'tools', config.tools)
  appendValue(lines, 'tool_aliases', config.tool_aliases)
  appendValue(lines, 'tools_settings', config.tools_settings)
  appendValue(lines, 'cao_tools', config.cao_tools)
  appendValue(lines, 'skills', config.skills)
  appendValue(lines, 'tags', config.tags)
  appendValue(lines, 'resources', config.resources)
  appendValue(lines, 'hooks', config.hooks)
  appendValue(lines, 'runtime_capabilities', config.runtime_capabilities)
  appendValue(lines, 'use_legacy_mcp_json', config.use_legacy_mcp_json)

  if (config.workspace?.team) {
    lines.push('', '[workspace]')
    appendValue(lines, 'team', config.workspace.team)
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
    return trimmed.slice(1, -1).replace(/\\n/g, '\n').replace(/\\r/g, '\r').replace(/\\t/g, '\t').replace(/\\"/g, '"').replace(/\\\\/g, '\\')
  }
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    const inner = trimmed.slice(1, -1).trim()
    if (!inner) return []
    return splitTomlItems(inner).map(part => parseTomlValue(part.trim()))
  }
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    const inner = trimmed.slice(1, -1).trim()
    if (!inner) return {}
    return Object.fromEntries(splitTomlItems(inner).map(part => {
      const [key, rawValue] = splitTomlAssignment(part)
      return [unquoteTomlKey(key.trim()), parseTomlValue(rawValue.trim())]
    }))
  }
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed)
  return trimmed
}

function splitTomlItems(value: string): string[] {
  const items: string[] = []
  let current = ''
  let quote = false
  let bracketDepth = 0
  let braceDepth = 0
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index]
    const previous = value[index - 1]
    if (char === '"' && previous !== '\\') quote = !quote
    if (!quote) {
      if (char === '[') bracketDepth += 1
      if (char === ']') bracketDepth -= 1
      if (char === '{') braceDepth += 1
      if (char === '}') braceDepth -= 1
      if (char === ',' && bracketDepth === 0 && braceDepth === 0) {
        items.push(current.trim())
        current = ''
        continue
      }
    }
    current += char
  }
  if (current.trim()) items.push(current.trim())
  return items
}

function splitTomlAssignment(value: string): [string, string] {
  let quote = false
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index]
    const previous = value[index - 1]
    if (char === '"' && previous !== '\\') quote = !quote
    if (char === '=' && !quote) return [value.slice(0, index), value.slice(index + 1)]
  }
  return [value, '']
}

function unquoteTomlKey(value: string): string {
  const trimmed = value.trim()
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) return String(parseTomlValue(trimmed))
  return trimmed
}

export function parseAgentTomlDraft(text: string): AgentWriteRequest {
  const body: AgentWriteRequest = {}
  const stringFields = new Set(['id', 'display_name', 'cli_provider', 'workdir', 'session_name'])
  const nullableStringFields = new Set(['description', 'model', 'reasoning_effort'])
  const listFields = new Set(['tools', 'skills', 'tags', 'resources', 'runtime_capabilities', 'cao_tools'])
  const tableFields = new Set(['tool_aliases', 'tools_settings', 'hooks', 'codex_config'])
  const ignoredLinearPresenceFields = new Set(['client_secret_configured', 'webhook_secret_configured', 'access_token_configured', 'refresh_token_configured', 'oauth_state_configured'])
  let section = ''

  text.split(/\r?\n/).forEach(rawLine => {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) return
    if (line.startsWith('[') && line.endsWith(']')) {
      section = line.slice(1, -1)
      return
    }
    const match = line.match(/^([A-Za-z0-9_-]+)\s*=\s*(.*)$/)
    if (!match) return
    const [, key, rawValue] = match
    const value = parseTomlValue(rawValue)
    if (section === 'workspace') {
      if (key === 'setup') {
        throw new Error('[workspace].setup is not supported; use [workspace].team')
      }
      body.workspace = { ...(body.workspace || {}), [key]: value } as AgentWriteRequest['workspace']
      return
    }
    if (section === 'codex_config') {
      body.codex_config = { ...(body.codex_config || {}), [key]: value }
      return
    }
    if (section.startsWith('mcp_servers.')) {
      const serverName = unquoteTomlKey(section.slice('mcp_servers.'.length))
      body.mcp_servers = { ...(body.mcp_servers || {}) }
      body.mcp_servers[serverName] = {
        ...((body.mcp_servers[serverName] as Record<string, unknown>) || {}),
        [key]: value,
      }
      return
    }
    if (section === 'linear') {
      if (ignoredLinearPresenceFields.has(key)) return
      body.linear = { ...(body.linear || {}), [key]: value } as AgentWriteRequest['linear']
      return
    }
    if (section.startsWith('linear.tool_access.')) {
      const accessId = unquoteTomlKey(section.slice('linear.tool_access.'.length))
      const current = body.linear?.tool_access || []
      const existing = current.find(access => access.access_id === accessId)
      const nextAccess = { ...(existing || { access_id: accessId }), [key]: value }
      body.linear = {
        ...(body.linear || {}),
        tool_access: [...current.filter(access => access.access_id !== accessId), nextAccess],
      }
      return
    }
    if (section) return
    if (stringFields.has(key) && typeof value === 'string') {
      ;(body as Record<string, unknown>)[key] = value
    } else if (nullableStringFields.has(key) && (typeof value === 'string' || value === null)) {
      ;(body as Record<string, unknown>)[key] = value
    } else if (listFields.has(key) && Array.isArray(value)) {
      ;(body as Record<string, unknown>)[key] = value
    } else if (tableFields.has(key) && value && typeof value === 'object') {
      ;(body as Record<string, unknown>)[key] = value
    } else if (key === 'use_legacy_mcp_json' && typeof value === 'boolean') {
      body.use_legacy_mcp_json = value
    }
  })

  return body
}

export function linearFieldStatus(configured: boolean, revealed: boolean): string {
  if (!configured) return 'Not configured'
  return revealed ? 'Configured on server' : '••••••••'
}

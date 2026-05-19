import { useEffect, useState } from 'react'
import { Save, Users } from 'lucide-react'
import { api, ProviderRoleAccessSchema, ToolDescriptor, WorkspaceSetup, WorkspaceTeam } from '../api'
import { useStore } from '../store'

const emptyDraft: WorkspaceTeam = {
  id: '',
  display_name: '',
  workspace_setup: '',
  roles: {},
  role_assignments: {},
  members: [],
  diagnostics: [],
}

interface ProviderFieldDescriptor {
  type?: string
  allowed_values?: string[]
}

function isNoisyPruningDiagnostic(message: string) {
  return /pruned .* for out-of-team agent /.test(message)
}

function providerFieldDescriptor(value: unknown): ProviderFieldDescriptor {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as ProviderFieldDescriptor)
    : {}
}

function stringListValue(value: unknown): string[] {
  return Array.isArray(value) ? value.filter(item => typeof item === 'string') : []
}

function parseStringList(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map(item => item.trim())
    .filter(Boolean)
}

export function WorkspaceTeamsPanel() {
  const { showSnackbar } = useStore()
  const [teams, setTeams] = useState<WorkspaceTeam[]>([])
  const [setups, setSetups] = useState<WorkspaceSetup[]>([])
  const [caoTools, setCaoTools] = useState<ToolDescriptor[]>([])
  const [providerSchemas, setProviderSchemas] = useState<Record<string, ProviderRoleAccessSchema>>({})
  const [draft, setDraft] = useState<WorkspaceTeam>(emptyDraft)
  const [saving, setSaving] = useState(false)

  const refresh = () =>
    Promise.all([api.listWorkspaceTeams(), api.listWorkspaceSetups(), api.listCaoToolDescriptors()]).then(([nextTeams, nextSetups, nextTools]) => {
      setTeams(nextTeams)
      setSetups(nextSetups)
      setCaoTools(nextTools)
      nextSetups
        .flatMap(setup => setup.providers)
        .filter((provider, index, providers) => providers.indexOf(provider) === index)
        .forEach(provider => {
          api
            .getWorkspaceProviderRoleAccessSchema(provider)
            .then(schema => setProviderSchemas(previous => ({ ...previous, [provider]: schema })))
            .catch(() => {})
        })
      setDraft(previous => ({
        ...previous,
        workspace_setup: previous.workspace_setup || nextSetups[0]?.id || '',
      }))
    })

  useEffect(() => {
    refresh().catch(() => {})
  }, [])

  const editTeam = (team: WorkspaceTeam) => {
    setDraft({
      ...team,
      roles: team.roles || {},
      role_assignments: team.role_assignments || {},
    })
  }

  const selectedSetup = setups.find(setup => setup.id === draft.workspace_setup)
  const addRole = () => {
    const nextId = `role_${Object.keys(draft.roles || {}).length + 1}`
    setDraft(previous => ({
      ...previous,
      roles: {
        ...(previous.roles || {}),
        [nextId]: {
          display_name: nextId,
          cao_tools: [],
          mcp_servers: {},
          providers: {},
          deletable: true,
        },
      },
    }))
  }

  const updateRole = (roleId: string, updater: (role: WorkspaceTeam['roles'][string]) => WorkspaceTeam['roles'][string]) => {
    setDraft(previous => ({
      ...previous,
      roles: {
        ...(previous.roles || {}),
        [roleId]: updater(previous.roles[roleId]),
      },
    }))
  }

  const saveTeam = async () => {
    const teamId = draft.id.trim()
    const setupId = draft.workspace_setup.trim()
    if (!teamId || !setupId) return
    setSaving(true)
    try {
      const saved = await api.upsertWorkspaceTeam({
        ...draft,
        id: teamId,
        display_name: draft.display_name.trim() || teamId,
        workspace_setup: setupId,
      })
      await refresh()
      setDraft({ ...emptyDraft, workspace_setup: setupId })
      showSnackbar({ type: 'success', message: `Team ${saved.id} saved` })
    } catch (error) {
      showSnackbar({ type: 'error', message: error instanceof Error ? error.message : `Failed to save ${teamId}` })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="rounded-lg border border-gray-700/50 bg-gray-800/60 p-4">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-300">
          Workspace Teams
        </h3>
        <div className="space-y-3">
          {teams.map(team => (
            <article key={team.id} className="rounded-lg border border-gray-700/40 bg-gray-950 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h4 className="truncate text-sm font-semibold text-gray-100">{team.display_name}</h4>
                  <dl className="mt-2 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-2 gap-y-1 font-mono text-xs">
                    <dt className="text-gray-600">team</dt>
                    <dd className="truncate text-emerald-300">{team.id}</dd>
                    <dt className="text-gray-600">setup</dt>
                    <dd className="truncate text-cyan-300">{team.workspace_setup}</dd>
                    <dt className="text-gray-600">members</dt>
                    <dd className="truncate text-gray-300">{team.members.length ? team.members.join(', ') : 'none'}</dd>
                    <dt className="text-gray-600">roles</dt>
                    <dd className="truncate text-gray-300">{Object.keys(team.roles || {}).join(', ') || 'member'}</dd>
                  </dl>
                  {team.diagnostics
                    .filter(diagnostic => !isNoisyPruningDiagnostic(diagnostic))
                    .map(diagnostic => (
                      <p key={diagnostic} className="mt-2 text-xs text-amber-300">{diagnostic}</p>
                    ))}
                </div>
                <button
                  type="button"
                  onClick={() => editTeam(team)}
                  className="rounded-md bg-gray-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-600"
                >
                  Edit
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-gray-700/50 bg-gray-800/60 p-4">
        <div className="mb-3 flex items-center gap-2">
          <Users size={16} className="text-emerald-300" />
          <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-300">Team</h3>
        </div>
        <div className="space-y-3">
          <label className="block text-xs text-gray-400">
            Team ID
            <input
              aria-label="team id"
              value={draft.id}
              onChange={event => setDraft(previous => ({ ...previous, id: event.target.value }))}
              className="mt-1 w-full rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
            />
          </label>
          <label className="block text-xs text-gray-400">
            Display name
            <input
              aria-label="team display name"
              value={draft.display_name}
              onChange={event => setDraft(previous => ({ ...previous, display_name: event.target.value }))}
              className="mt-1 w-full rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
            />
          </label>
          <label className="block text-xs text-gray-400">
            Workspace setup
            <select
              aria-label="team workspace setup"
              value={draft.workspace_setup}
              onChange={event => setDraft(previous => ({ ...previous, workspace_setup: event.target.value }))}
              className="mt-1 w-full rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
            >
              {setups.map(setup => (
                <option key={setup.id} value={setup.id}>
                  {setup.display_name} ({setup.id})
                </option>
              ))}
            </select>
          </label>
          <div className="space-y-3 rounded-md border border-gray-700 bg-gray-950 p-3">
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Roles</h4>
              <button
                type="button"
                onClick={addRole}
                className="rounded-md bg-gray-700 px-2 py-1 text-xs text-white hover:bg-gray-600"
              >
                Add role
              </button>
            </div>
            {Object.entries(draft.roles || {}).map(([roleId, role]) => (
              <div key={roleId} className="space-y-2 border-t border-gray-800 pt-3 first:border-t-0 first:pt-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-emerald-300">{roleId}</span>
                  {!role.deletable && <span className="text-[10px] uppercase text-gray-500">default</span>}
                </div>
                <input
                  aria-label={`${roleId} role display name`}
                  value={role.display_name}
                  onChange={event => updateRole(roleId, current => ({ ...current, display_name: event.target.value }))}
                  className="w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
                />
                <fieldset className="space-y-1">
                  <legend className="text-xs text-gray-500">CAO tools</legend>
                  {caoTools.map(tool => (
                    <label key={tool.name} className="flex items-center gap-2 text-xs text-gray-300" title={tool.description}>
                      <input
                        type="checkbox"
                        checked={role.cao_tools.includes(tool.name)}
                        onChange={event =>
                          updateRole(roleId, current => ({
                            ...current,
                            cao_tools: event.target.checked
                              ? [...current.cao_tools, tool.name]
                              : current.cao_tools.filter(name => name !== tool.name),
                          }))
                        }
                      />
                      <span className="font-mono">{tool.name}</span>
                    </label>
                  ))}
                </fieldset>
                {selectedSetup?.providers.map(provider => {
                  const schema = providerSchemas[provider]
                  const tools = schema?.tools ?? []
                  const fields = Object.entries(schema?.fields ?? {}).filter(([field]) => field !== 'tools')
                  const providerGrants = role.providers[provider] || {}
                  const grantId = Object.keys(providerGrants)[0] || 'default'
                  const grant = providerGrants[grantId] || { tools: [] }
                  return (
                    <fieldset key={provider} className="space-y-1">
                      <legend className="text-xs text-gray-500">{provider} tools</legend>
                      {tools.map(tool => (
                        <label key={tool.name} className="flex items-center gap-2 text-xs text-gray-300" title={tool.description}>
                          <input
                            type="checkbox"
                            checked={Array.isArray(grant.tools) && grant.tools.includes(tool.name)}
                            onChange={event =>
                              updateRole(roleId, current => {
                                const currentTools = Array.isArray(grant.tools) ? grant.tools as string[] : []
                                const nextTools = event.target.checked
                                  ? [...currentTools, tool.name]
                                  : currentTools.filter(name => name !== tool.name)
                                return {
                                  ...current,
                                  providers: {
                                    ...current.providers,
                                    [provider]: {
                                      ...providerGrants,
                                      [grantId]: { ...grant, tools: nextTools },
                                    },
                                  },
                                }
                              })
                            }
                          />
                          <span className="font-mono">{tool.name}</span>
                        </label>
                      ))}
                      {fields.map(([fieldName, rawDescriptor]) => {
                        const descriptor = providerFieldDescriptor(rawDescriptor)
                        const ariaLabel = `${roleId} ${provider} ${fieldName}`
                        if (descriptor.type === 'boolean') {
                          return (
                            <label key={fieldName} className="flex items-center gap-2 text-xs text-gray-300">
                              <input
                                aria-label={ariaLabel}
                                type="checkbox"
                                checked={grant[fieldName] === true}
                                onChange={event =>
                                  updateRole(roleId, current => ({
                                    ...current,
                                    providers: {
                                      ...current.providers,
                                      [provider]: {
                                        ...providerGrants,
                                        [grantId]: { ...grant, [fieldName]: event.target.checked },
                                      },
                                    },
                                  }))
                                }
                              />
                              <span className="font-mono">{fieldName}</span>
                            </label>
                          )
                        }
                        if (descriptor.type === 'string_list') {
                          const allowedValues = descriptor.allowed_values ?? []
                          return (
                            <label key={fieldName} className="block text-xs text-gray-400">
                              <span className="font-mono">{fieldName}</span>
                              <textarea
                                aria-label={ariaLabel}
                                value={stringListValue(grant[fieldName]).join('\n')}
                                placeholder={allowedValues.length ? allowedValues.join(', ') : 'one value per line'}
                                onChange={event =>
                                  updateRole(roleId, current => ({
                                    ...current,
                                    providers: {
                                      ...current.providers,
                                      [provider]: {
                                        ...providerGrants,
                                        [grantId]: { ...grant, [fieldName]: parseStringList(event.target.value) },
                                      },
                                    },
                                  }))
                                }
                                className="mt-1 min-h-[58px] w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 font-mono text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
                              />
                            </label>
                          )
                        }
                        return (
                          <label key={fieldName} className="block text-xs text-gray-400">
                            <span className="font-mono">{fieldName}</span>
                            <input
                              aria-label={ariaLabel}
                              value={typeof grant[fieldName] === 'string' ? grant[fieldName] : ''}
                              onChange={event =>
                                updateRole(roleId, current => ({
                                  ...current,
                                  providers: {
                                    ...current.providers,
                                    [provider]: {
                                      ...providerGrants,
                                      [grantId]: { ...grant, [fieldName]: event.target.value },
                                    },
                                  },
                                }))
                              }
                              className="mt-1 w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 font-mono text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
                            />
                          </label>
                        )
                      })}
                    </fieldset>
                  )
                })}
              </div>
            ))}
          </div>
          <label className="block text-xs text-gray-400">
            Role assignments
            <textarea
              aria-label="team role assignments"
              value={JSON.stringify(draft.role_assignments, null, 2)}
              onChange={event => {
                try {
                  const parsed = JSON.parse(event.target.value || '{}')
                  setDraft(previous => ({ ...previous, role_assignments: parsed }))
                } catch {
                  setDraft(previous => previous)
                }
              }}
              className="mt-1 min-h-[90px] w-full rounded-md border border-gray-700 bg-gray-950 px-2 py-1 font-mono text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
            />
          </label>
          <button
            type="button"
            onClick={saveTeam}
            disabled={saving || !draft.id.trim() || !draft.workspace_setup.trim()}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
          >
            <Save size={14} /> {saving ? 'Saving...' : 'Save Team'}
          </button>
        </div>
      </section>
    </div>
  )
}

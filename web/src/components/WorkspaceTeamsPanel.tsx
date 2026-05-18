import { useEffect, useState } from 'react'
import { Save, Users } from 'lucide-react'
import { api, WorkspaceSetup, WorkspaceTeam } from '../api'
import { useStore } from '../store'

const emptyDraft: WorkspaceTeam = {
  id: '',
  display_name: '',
  workspace_setup: '',
  members: [],
  diagnostics: [],
}

export function WorkspaceTeamsPanel() {
  const { showSnackbar } = useStore()
  const [teams, setTeams] = useState<WorkspaceTeam[]>([])
  const [setups, setSetups] = useState<WorkspaceSetup[]>([])
  const [draft, setDraft] = useState<WorkspaceTeam>(emptyDraft)
  const [saving, setSaving] = useState(false)

  const refresh = () =>
    Promise.all([api.listWorkspaceTeams(), api.listWorkspaceSetups()]).then(([nextTeams, nextSetups]) => {
      setTeams(nextTeams)
      setSetups(nextSetups)
      setDraft(previous => ({
        ...previous,
        workspace_setup: previous.workspace_setup || nextSetups[0]?.id || '',
      }))
    })

  useEffect(() => {
    refresh().catch(() => {})
  }, [])

  const editTeam = (team: WorkspaceTeam) => {
    setDraft(team)
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
                  </dl>
                  {team.diagnostics.map(diagnostic => (
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

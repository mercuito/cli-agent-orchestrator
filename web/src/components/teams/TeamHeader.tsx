import { useEffect, useState } from 'react'
import type { WorkspaceSetup, WorkspaceTeam } from '../../api'

interface TeamHeaderProps {
  team: WorkspaceTeam
  setups: WorkspaceSetup[]
  onMetadataChange: (metadata: { display_name: string; workspace_setup: string }) => void
}

export function TeamHeader({ team, setups, onMetadataChange }: TeamHeaderProps) {
  const [displayName, setDisplayName] = useState(team.display_name)

  useEffect(() => {
    setDisplayName(team.display_name)
  }, [team.id, team.display_name])

  const commitDisplayName = () => {
    const nextDisplayName = displayName.trim() || team.id
    if (nextDisplayName !== team.display_name) {
      onMetadataChange({ display_name: nextDisplayName, workspace_setup: team.workspace_setup })
    }
  }

  return (
    <section className="rounded-lg border border-gray-700 bg-gray-800/80 p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <label className="grid gap-1.5 text-xs text-gray-400">
            Team display name
            <input
              aria-label="Team display name"
              value={displayName}
              onChange={event => setDisplayName(event.target.value)}
              onBlur={commitDisplayName}
              className="max-w-xl rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-xl font-semibold text-white focus:border-emerald-500 focus:outline-none"
            />
          </label>
          <dl className="mt-3 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
            <dt className="text-gray-500">Team ID</dt>
            <dd className="truncate font-mono text-emerald-300">{team.id}</dd>
          </dl>
        </div>

        <label className="grid min-w-[260px] gap-1.5 text-xs text-gray-400">
          Workspace setup
          <select
            aria-label="Workspace setup"
            value={team.workspace_setup}
            onChange={event => onMetadataChange({
              display_name: (displayName.trim() || team.id),
              workspace_setup: event.target.value,
            })}
            className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-100 focus:border-emerald-500 focus:outline-none"
          >
            {setups.map(setup => (
              <option key={setup.id} value={setup.id}>
                {setup.display_name} ({setup.id})
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  )
}

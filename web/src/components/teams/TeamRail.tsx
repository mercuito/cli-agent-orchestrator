import { Plus } from 'lucide-react'
import type { WorkspaceTeam } from '../../api'

interface TeamRailProps {
  teams: WorkspaceTeam[]
  selectedTeamId: string | null
  onSelectTeam: (teamId: string) => void
  onCreateTeam: () => void
}

export function TeamRail({ teams, selectedTeamId, onSelectTeam, onCreateTeam }: TeamRailProps) {
  const selectedTeam = teams.find(team => team.id === selectedTeamId)

  return (
    <aside className="flex min-h-[690px] flex-col gap-3 rounded-lg border border-gray-700 bg-gray-800/80 p-4" aria-label="Teams">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-bold text-gray-200">Teams</h2>
        <button
          type="button"
          onClick={onCreateTeam}
          className="inline-flex min-h-[34px] items-center gap-2 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-bold text-white hover:bg-emerald-500"
        >
          <Plus size={14} /> New team
        </button>
      </div>

      <div className="grid gap-2">
        {teams.map(team => {
          const agentCount = team.member_details.length
          const roleCount = Object.keys(team.roles || {}).length
          const active = team.id === selectedTeamId
          return (
            <button
              key={team.id}
              type="button"
              onClick={() => onSelectTeam(team.id)}
              aria-label={`${team.display_name} ${agentCount} agents ${roleCount} roles`}
              className={`relative rounded-lg border p-3 text-left transition-colors ${
                active
                  ? 'border-emerald-400 bg-emerald-500/15'
                  : 'border-gray-700 bg-gray-900/70 hover:border-gray-600'
              }`}
            >
              {active && <span className="absolute left-0 top-3 h-[calc(100%-24px)] w-1 rounded-r bg-emerald-400" />}
              <h3 className="truncate text-sm font-semibold text-white">{team.display_name}</h3>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="rounded-md bg-gray-700 px-2 py-1 text-[11px] text-gray-200">
                  {agentCount} agent{agentCount === 1 ? '' : 's'}
                </span>
                <span className="rounded-md bg-gray-700 px-2 py-1 text-[11px] text-gray-200">
                  {roleCount} role{roleCount === 1 ? '' : 's'}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      <div className="mt-auto rounded-lg border border-gray-700 bg-gray-900/60 p-3 text-xs text-gray-400">
        Workspace: {selectedTeam?.display_name ?? 'No team selected'}
      </div>
    </aside>
  )
}

import { Plus } from 'lucide-react'
import type { WorkspaceTeam } from '../../api'
import { roleDisplayName, roleMemberCount, roleToolNames } from './teamUtils'

interface RolesStripProps {
  team: WorkspaceTeam
  selectedRoleId: string | null
  onSelectRole: (roleId: string) => void
  onCreateRole: () => void
}

export function RolesStrip({ team, selectedRoleId, onSelectRole, onCreateRole }: RolesStripProps) {
  return (
    <section className="rounded-lg border border-gray-700 bg-gray-800/80 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-bold text-gray-200">Roles</h3>
        <button
          type="button"
          aria-label="+ New role"
          onClick={onCreateRole}
          className="inline-flex items-center gap-1.5 rounded-lg bg-gray-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-gray-600"
        >
          <Plus size={13} /> New role
        </button>
      </div>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {Object.entries(team.roles).map(([roleId, role]) => {
          const selected = selectedRoleId === roleId
          const memberCount = roleMemberCount(team, roleId)
          const toolNames = roleToolNames(role).slice(0, 3)
          return (
            <button
              key={roleId}
              type="button"
              onClick={() => onSelectRole(roleId)}
              className={`min-h-[124px] rounded-lg border p-3 text-left transition-colors ${
                selected
                  ? 'border-blue-400 bg-blue-500/15'
                  : 'border-gray-700 bg-gray-900/70 hover:border-gray-600'
              }`}
            >
              <div>
                <h4 className="truncate text-base font-semibold text-white">{roleDisplayName(roleId, role)}</h4>
                <p className="mt-1 text-xs text-gray-400">
                  {memberCount} member{memberCount === 1 ? '' : 's'} - {roleToolNames(role).length} tools
                </p>
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {toolNames.map(tool => (
                  <span key={tool} className="max-w-[120px] truncate rounded-md border border-gray-700 bg-gray-950 px-2 py-1 font-mono text-[11px] text-blue-100">
                    {tool}
                  </span>
                ))}
                {toolNames.length === 0 && (
                  <span className="rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-[11px] text-gray-500">
                    no tools
                  </span>
                )}
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}

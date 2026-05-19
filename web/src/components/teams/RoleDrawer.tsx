import { Shield, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { WorkspaceTeam, WorkspaceTeamRole } from '../../api'
import { ConfirmModal } from '../ConfirmModal'
import { fallbackRoleId, isToolEnabled, roleDisplayName, roleMemberCount, toggleTool } from './teamUtils'
import type { ToolOption } from './types'

interface RoleDrawerProps {
  team: WorkspaceTeam
  roleId: string | null
  tools: ToolOption[]
  onClose: () => void
  onSaveRole: (roleId: string, role: WorkspaceTeamRole) => void
  onDeleteRole: (roleId: string) => void
}

export function RoleDrawer({ team, roleId, tools, onClose, onSaveRole, onDeleteRole }: RoleDrawerProps) {
  const role = roleId ? team.roles[roleId] : null
  const [draft, setDraft] = useState<WorkspaceTeamRole | null>(role)
  const [toolQuery, setToolQuery] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    setDraft(role)
    setToolQuery('')
    setConfirmDelete(false)
  }, [role, roleId])

  const filteredTools = useMemo(() => {
    const normalizedQuery = toolQuery.trim().toLowerCase()
    if (!normalizedQuery) return tools
    return tools.filter(tool =>
      `${tool.name} ${tool.description} ${tool.pill}`.toLowerCase().includes(normalizedQuery),
    )
  }, [toolQuery, tools])

  if (!roleId || !draft || !role) {
    return (
      <aside className="min-h-[690px] rounded-lg border border-gray-700 bg-gray-800/80 p-4" aria-label="Role editor">
        <h2 className="text-base font-bold text-white">Edit role</h2>
        <p className="mt-3 text-sm text-gray-400">Select a role to edit its tools.</p>
      </aside>
    )
  }

  const displayName = roleDisplayName(roleId, draft)
  const canDelete = roleId !== fallbackRoleId && draft.deletable !== false

  return (
    <aside className="min-h-[690px] rounded-lg border border-gray-700 bg-gradient-to-b from-gray-800 to-gray-900 p-4" aria-label="Edit role" role="complementary">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-base font-bold text-white">Edit role</h2>
        <button
          type="button"
          aria-label="Close role editor"
          onClick={onClose}
          className="grid h-8 w-8 place-items-center rounded-lg border border-gray-600 bg-gray-700 text-gray-200 hover:bg-gray-600"
        >
          <X size={14} />
        </button>
      </div>

      <div className="mb-4 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg border border-blue-400/40 bg-blue-500/15 text-blue-100">
          <Shield size={18} />
        </div>
        <h3 className="min-w-0 truncate text-xl font-semibold text-white">{displayName}</h3>
      </div>

      <div className="grid gap-3">
        <label className="grid gap-1.5 text-xs text-gray-400">
          Display name
          <input
            aria-label="Role display name"
            value={draft.display_name}
            onChange={event => setDraft(current => current ? { ...current, display_name: event.target.value } : current)}
            className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-100 focus:border-emerald-500 focus:outline-none"
          />
        </label>

        <section className="overflow-hidden rounded-lg border border-gray-700 bg-gray-950/70">
          <div className="flex items-center justify-between gap-3 border-b border-gray-700 px-3 py-2">
            <h4 className="text-sm font-bold text-gray-200">Tools</h4>
            <span className="rounded-md bg-gray-700 px-2 py-1 text-[11px] text-gray-300">
              {tools.filter(tool => isToolEnabled(draft, tool)).length} enabled
            </span>
          </div>
          <div className="grid gap-2 p-3">
            <input
              aria-label="Search tools"
              value={toolQuery}
              onChange={event => setToolQuery(event.target.value)}
              placeholder="Search tools by name..."
              className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-100 focus:border-emerald-500 focus:outline-none"
            />
            <div className="grid max-h-[420px] gap-2 overflow-auto pr-1">
              {filteredTools.map(tool => (
                <label key={tool.key} className="grid grid-cols-[18px_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border border-gray-700 bg-gray-900 p-2.5">
                  <input
                    type="checkbox"
                    aria-label={`Toggle ${tool.name}`}
                    checked={isToolEnabled(draft, tool)}
                    onChange={event => setDraft(current => current ? toggleTool(current, tool, event.target.checked) : current)}
                    className="h-4 w-4 accent-emerald-500"
                  />
                  <span className="min-w-0">
                    <strong className="block truncate font-mono text-xs text-gray-100">{tool.name}</strong>
                    <span className="block truncate text-[11px] text-gray-400">{tool.description}</span>
                  </span>
                  <span className="rounded-md bg-gray-700 px-2 py-1 text-[11px] text-gray-200">{tool.pill}</span>
                </label>
              ))}
              {filteredTools.length === 0 && (
                <p className="rounded-lg border border-dashed border-gray-700 p-3 text-sm text-gray-500">No matching tools</p>
              )}
            </div>
          </div>
        </section>

        <p className="rounded-lg border border-blue-400/40 bg-blue-500/10 p-3 text-xs leading-5 text-blue-100">
          Changes to a role affect members assigned to that role. Running agents may need a terminal refresh before live tool access reflects the new configuration.
        </p>

        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            disabled={!canDelete}
            className="rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-2 text-xs font-bold text-red-100 hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Delete role
          </button>
          <button
            type="button"
            onClick={() => onSaveRole(roleId, draft)}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white hover:bg-emerald-500"
          >
            Save role
          </button>
        </div>
      </div>

      <ConfirmModal
        open={confirmDelete}
        title="Delete role"
        message={`${roleMemberCount(team, roleId)} members will fall back to member if this role is deleted.`}
        details={[{ label: 'Role', value: displayName }]}
        confirmLabel="Delete role"
        loading={false}
        onConfirm={() => {
          setConfirmDelete(false)
          onDeleteRole(roleId)
        }}
        onCancel={() => setConfirmDelete(false)}
      />
    </aside>
  )
}

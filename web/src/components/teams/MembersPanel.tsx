import { X } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { AgentStatus, WorkspaceTeam, WorkspaceTeamMemberDetail } from '../../api'
import { displayAgentId, roleDisplayName } from './teamUtils'

interface MembersPanelProps {
  team: WorkspaceTeam
  agents: AgentStatus[]
  onChangeRole: (agentId: string, roleId: string) => void
  onRemoveMember: (agentId: string) => void
}

export function MembersPanel({ team, agents, onChangeRole, onRemoveMember }: MembersPanelProps) {
  const [query, setQuery] = useState('')
  const agentById = new Map(agents.map(agent => [displayAgentId(agent), agent]))
  const visibleMembers = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return team.member_details.filter(member => {
      if (!normalizedQuery) return true
      const agent = agentById.get(member.agent_id)
      return `${member.display_name} ${member.agent_id} ${agent?.cli_provider ?? ''}`.toLowerCase().includes(normalizedQuery)
    })
  }, [agentById, query, team.member_details])

  return (
    <section className="rounded-lg border border-gray-700 bg-gray-900/60 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-bold text-gray-200">Members</h3>
        <span className="rounded-md bg-gray-700 px-2 py-1 text-[11px] text-gray-300">role assignment</span>
      </div>
      <input
        aria-label="Search members"
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder="Search members..."
        className="mb-3 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-100 focus:border-emerald-500 focus:outline-none"
      />
      <div className="grid gap-2">
        {visibleMembers.map(member => (
          <MemberRow
            key={member.agent_id}
            member={member}
            agent={agentById.get(member.agent_id)}
            team={team}
            onChangeRole={onChangeRole}
            onRemoveMember={onRemoveMember}
          />
        ))}
        {visibleMembers.length === 0 && (
          <p className="rounded-lg border border-dashed border-gray-700 p-3 text-sm text-gray-500">No members found</p>
        )}
      </div>
    </section>
  )
}

function MemberRow({
  member,
  agent,
  team,
  onChangeRole,
  onRemoveMember,
}: {
  member: WorkspaceTeamMemberDetail
  agent?: AgentStatus
  team: WorkspaceTeam
  onChangeRole: (agentId: string, roleId: string) => void
  onRemoveMember: (agentId: string) => void
}) {
  return (
    <article className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border border-gray-700 bg-gray-800/70 p-2.5">
      <div className="grid h-7 w-7 place-items-center rounded-lg border border-gray-600 bg-gray-700 text-xs font-bold text-blue-100">
        {member.display_name.charAt(0).toUpperCase()}
      </div>
      <div className="min-w-0">
        <strong className="block truncate text-sm text-gray-100">{member.display_name}</strong>
        <span className="block truncate text-[11px] text-gray-400">
          {agent?.cli_provider && (
            <span className="mr-1 rounded bg-gray-700 px-1.5 py-0.5 font-mono text-[10px] text-gray-300">
              {agent.cli_provider}
            </span>
          )}
          <span className="font-mono">{member.agent_id}</span>
        </span>
      </div>
      <div className="flex items-center gap-2">
        <select
          aria-label={`${member.display_name} role`}
          value={member.role_id}
          onChange={event => onChangeRole(member.agent_id, event.target.value)}
          className="w-[118px] rounded-lg border border-gray-700 bg-gray-950 px-2 py-1.5 text-xs text-gray-100 focus:border-emerald-500 focus:outline-none"
        >
          {Object.entries(team.roles).map(([roleId, role]) => (
            <option key={roleId} value={roleId}>
              {roleDisplayName(roleId, role)}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-label={`Remove ${member.display_name}`}
          onClick={() => onRemoveMember(member.agent_id)}
          className="grid h-8 w-8 place-items-center rounded-lg border border-gray-600 bg-gray-700 text-gray-200 hover:bg-gray-600"
        >
          <X size={14} />
        </button>
      </div>
    </article>
  )
}

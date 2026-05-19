import { Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { AgentStatus, WorkspaceTeam } from '../../api'
import { displayAgentId } from './teamUtils'

interface AvailableAgentsPanelProps {
  team: WorkspaceTeam
  agents: AgentStatus[]
  assignedAgentIds: Set<string>
  agentsLoading?: boolean
  onAddAgent: (agent: AgentStatus) => void
}

export function AvailableAgentsPanel({ team, agents, assignedAgentIds, agentsLoading = false, onAddAgent }: AvailableAgentsPanelProps) {
  const [query, setQuery] = useState('')
  const memberIds = new Set(team.member_details.map(member => member.agent_id))
  const visibleAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return agents
      .filter(agent => !memberIds.has(displayAgentId(agent)))
      .filter(agent => !assignedAgentIds.has(displayAgentId(agent)))
      .filter(agent => {
        if (!normalizedQuery) return true
        const agentId = displayAgentId(agent)
        return `${agent.display_name} ${agentId} ${agent.cli_provider}`.toLowerCase().includes(normalizedQuery)
      })
  }, [agents, assignedAgentIds, memberIds, query])

  return (
    <section className="rounded-lg border border-gray-700 bg-gray-900/60 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-bold text-gray-200">Available agents</h3>
        <span className="rounded-md bg-gray-700 px-2 py-1 text-[11px] text-gray-300">not in team</span>
      </div>
      <input
        aria-label="Search available agents"
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder="Search agents..."
        className="mb-3 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-100 focus:border-emerald-500 focus:outline-none"
      />
      <div className="grid gap-2">
        {visibleAgents.map(agent => {
          const agentId = displayAgentId(agent)
          return (
            <article key={agentId} className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border border-gray-700 bg-gray-800/70 p-2.5">
              <div className="grid h-7 w-7 place-items-center rounded-lg border border-gray-600 bg-gray-700 text-xs font-bold text-blue-100">
                {agent.display_name.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <strong className="block truncate text-sm text-gray-100">{agent.display_name}</strong>
                <span className="block truncate font-mono text-[11px] text-gray-400">{agentId}</span>
              </div>
              <button
                type="button"
                aria-label={`Add ${agent.display_name}`}
                onClick={() => onAddAgent(agent)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-gray-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-gray-600"
              >
                <Plus size={13} /> Add
              </button>
            </article>
          )
        })}
        {agentsLoading && visibleAgents.length === 0 && (
          <p className="rounded-lg border border-dashed border-gray-700 p-3 text-sm text-gray-500">Loading agents...</p>
        )}
        {!agentsLoading && visibleAgents.length === 0 && (
          <p className="rounded-lg border border-dashed border-gray-700 p-3 text-sm text-gray-500">No available agents</p>
        )}
      </div>
    </section>
  )
}

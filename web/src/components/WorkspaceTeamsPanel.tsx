import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type AgentStatus, type ProviderRoleAccessSchema, type ToolDescriptor, type WorkspaceSetup, type WorkspaceTeam, type WorkspaceTeamRole } from '../api'
import { useStore } from '../store'
import { AvailableAgentsPanel } from './teams/AvailableAgentsPanel'
import { MembersPanel } from './teams/MembersPanel'
import { RoleDrawer } from './teams/RoleDrawer'
import { RolesStrip } from './teams/RolesStrip'
import { TeamHeader } from './teams/TeamHeader'
import { TeamRail } from './teams/TeamRail'
import { buildToolOptions, defaultMemberRole } from './teams/teamUtils'
import { useTeamMutations } from './teams/useTeamMutations'

export function WorkspaceTeamsPanel() {
  const { showSnackbar } = useStore()
  const [teams, setTeams] = useState<WorkspaceTeam[]>([])
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [setups, setSetups] = useState<WorkspaceSetup[]>([])
  const [caoTools, setCaoTools] = useState<ToolDescriptor[]>([])
  const [providerSchemas, setProviderSchemas] = useState<Record<string, ProviderRoleAccessSchema>>({})
  const [agentsLoading, setAgentsLoading] = useState(true)
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null)
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const previousSelectedTeamId = useRef<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setAgentsLoading(true)
    try {
      const [nextTeams, nextSetups, nextTools] = await Promise.all([
        api.listWorkspaceTeams(),
        api.listWorkspaceSetups(),
        api.listCaoToolDescriptors(),
      ])
      setTeams(nextTeams)
      setSetups(nextSetups)
      setCaoTools(nextTools)
      setSelectedTeamId(current => current && nextTeams.some(team => team.id === current) ? current : nextTeams[0]?.id ?? null)
      setLoading(false)

      const providers = Array.from(new Set(nextSetups.flatMap(setup => setup.providers)))
      void Promise.all(providers.map(provider =>
        api.getWorkspaceToolProviderRoleAccessSchema(provider)
          .then(schema => [provider, schema] as const)
          .catch(() => null),
      )).then(schemas => {
        setProviderSchemas(Object.fromEntries(schemas.filter(Boolean) as Array<[string, ProviderRoleAccessSchema]>))
      })

      void api.listAgents()
        .then(setAgents)
        .catch(() => setAgents([]))
        .finally(() => setAgentsLoading(false))
    } catch (error) {
      showSnackbar({ type: 'error', message: error instanceof Error ? error.message : 'Failed to load workspace teams' })
      setLoading(false)
      setAgentsLoading(false)
    }
  }, [showSnackbar])

  useEffect(() => {
    refresh()
  }, [refresh])

  const selectedTeam = teams.find(team => team.id === selectedTeamId) ?? null
  const selectedSetup = selectedTeam ? setups.find(setup => setup.id === selectedTeam.workspace_setup) : undefined
  const assignedAgentIds = useMemo(
    () => new Set(teams.flatMap(team => team.member_details.map(member => member.agent_id))),
    [teams],
  )
  const toolOptions = useMemo(
    () => buildToolOptions(caoTools, agents, selectedSetup, providerSchemas),
    [agents, caoTools, providerSchemas, selectedSetup],
  )
  const mutations = useTeamMutations({ teams, setTeams, selectedTeamId, setSelectedTeamId, showSnackbar })

  useEffect(() => {
    if (previousSelectedTeamId.current === selectedTeamId) return
    previousSelectedTeamId.current = selectedTeamId
    setSelectedRoleId(selectedTeam ? Object.keys(selectedTeam.roles)[0] ?? null : null)
  }, [selectedTeam, selectedTeamId])

  useEffect(() => {
    if (selectedRoleId && selectedTeam && !selectedTeam.roles[selectedRoleId]) {
      setSelectedRoleId(Object.keys(selectedTeam.roles)[0] ?? null)
    }
  }, [selectedRoleId, selectedTeam])

  const createTeam = () => {
    const workspaceSetup = selectedTeam?.workspace_setup || setups[0]?.id
    if (!workspaceSetup) {
      showSnackbar({ type: 'error', message: 'Create a workspace setup before adding a team' })
      return
    }
    const id = uniqueTeamId(teams)
    mutations.createTeam(mutations.emptyTeam(id, 'New Team', workspaceSetup))
  }

  const createRole = () => {
    if (!selectedTeam) return
    const roleId = uniqueRoleId(selectedTeam)
    const role: WorkspaceTeamRole = {
      ...defaultMemberRole(),
      display_name: roleId.replace(/^role_/, 'Role '),
      deletable: true,
    }
    setSelectedRoleId(roleId)
    mutations.createRole(selectedTeam, roleId, role)
  }

  if (loading && teams.length === 0) {
    return (
      <div className="rounded-lg border border-gray-700 bg-gray-800/80 p-6 text-sm text-gray-400">
        Loading workspace teams...
      </div>
    )
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)_340px]">
      <TeamRail
        teams={teams}
        selectedTeamId={selectedTeamId}
        onSelectTeam={teamId => {
          setSelectedTeamId(teamId)
          const nextTeam = teams.find(team => team.id === teamId)
          setSelectedRoleId(nextTeam ? Object.keys(nextTeam.roles)[0] ?? null : null)
        }}
        onCreateTeam={createTeam}
      />

      {selectedTeam ? (
        <>
          <section className="grid min-w-0 gap-4">
            <TeamHeader
              team={selectedTeam}
              setups={setups}
              onMetadataChange={metadata => mutations.updateMetadata(selectedTeam, metadata)}
            />

            {visibleDiagnostics(selectedTeam).length > 0 && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
                {visibleDiagnostics(selectedTeam).map(diagnostic => (
                  <p key={diagnostic}>{diagnostic}</p>
                ))}
              </div>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              <AvailableAgentsPanel
                team={selectedTeam}
                agents={agents}
                assignedAgentIds={assignedAgentIds}
                agentsLoading={agentsLoading}
                onAddAgent={agent => mutations.addMember(selectedTeam, agent)}
              />
              <MembersPanel
                team={selectedTeam}
                agents={agents}
                onChangeRole={(agentId, roleId) => mutations.changeMemberRole(selectedTeam, agentId, roleId)}
                onRemoveMember={agentId => mutations.removeMember(selectedTeam, agentId)}
              />
            </div>

            <RolesStrip
              team={selectedTeam}
              selectedRoleId={selectedRoleId}
              onSelectRole={setSelectedRoleId}
              onCreateRole={createRole}
            />
          </section>

          <RoleDrawer
            team={selectedTeam}
            roleId={selectedRoleId}
            tools={toolOptions}
            onClose={() => setSelectedRoleId(null)}
            onSaveRole={(roleId, role) => mutations.saveRole(selectedTeam, roleId, role)}
            onDeleteRole={roleId => {
              mutations.deleteRole(selectedTeam, roleId)
              setSelectedRoleId(Object.keys(selectedTeam.roles).find(id => id !== roleId) ?? null)
            }}
          />
        </>
      ) : (
        <section className="xl:col-span-2 rounded-lg border border-gray-700 bg-gray-800/80 p-6 text-sm text-gray-400">
          No teams yet. Use New team to create one.
        </section>
      )}
    </div>
  )
}

function uniqueTeamId(teams: WorkspaceTeam[]) {
  const existing = new Set(teams.map(team => team.id))
  let index = teams.length + 1
  let id = `team_${index}`
  while (existing.has(id)) {
    index += 1
    id = `team_${index}`
  }
  return id
}

function uniqueRoleId(team: WorkspaceTeam) {
  const existing = new Set(Object.keys(team.roles))
  let index = Object.keys(team.roles).length + 1
  let id = `role_${index}`
  while (existing.has(id)) {
    index += 1
    id = `role_${index}`
  }
  return id
}

function visibleDiagnostics(team: WorkspaceTeam) {
  return team.diagnostics.filter(diagnostic => !/pruned .* for out-of-team agent /.test(diagnostic))
}

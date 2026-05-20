import type { Dispatch, SetStateAction } from 'react'
import { api, type AgentStatus, type WorkspaceTeam, type WorkspaceTeamRole } from '../../api'
import { defaultMemberRole, displayAgentId, fallbackRoleId } from './teamUtils'

interface Snackbar {
  type: 'success' | 'error' | 'info'
  message: string
}

interface UseTeamMutationsArgs {
  teams: WorkspaceTeam[]
  setTeams: Dispatch<SetStateAction<WorkspaceTeam[]>>
  selectedTeamId: string | null
  setSelectedTeamId: (teamId: string | null) => void
  showSnackbar: (snackbar: Snackbar) => void
}

export function useTeamMutations({ teams, setTeams, selectedTeamId, setSelectedTeamId, showSnackbar }: UseTeamMutationsArgs) {
  const commitTeam = (team: WorkspaceTeam) => {
    setTeams(current => current.map(currentTeam => currentTeam.id === team.id ? team : currentTeam))
  }

  const commitMemberMove = (team: WorkspaceTeam, agentId: string) => {
    setTeams(current => current.map(currentTeam => (
      currentTeam.id === team.id ? team : withoutMember(currentTeam, agentId)
    )))
  }

  const rollback = (snapshot: WorkspaceTeam[], error: unknown) => {
    setTeams(snapshot)
    showSnackbar({ type: 'error', message: error instanceof Error ? error.message : 'Team update failed' })
  }

  const runOptimisticTeamUpdate = async (
    team: WorkspaceTeam,
    optimisticTeam: WorkspaceTeam,
    request: () => Promise<WorkspaceTeam>,
  ) => {
    const snapshot = teams
    commitTeam(optimisticTeam)
    try {
      commitTeam(await request())
    } catch (error) {
      rollback(snapshot, error)
      throw error
    }
  }

  return {
    async createTeam(team: WorkspaceTeam) {
      const snapshot = teams
      setTeams(current => [...current, team])
      setSelectedTeamId(team.id)
      try {
        const created = await api.createWorkspaceTeam({
          id: team.id,
          display_name: team.display_name,
          workspace: team.workspace,
        })
        setTeams(current => current.map(currentTeam => currentTeam.id === team.id ? created : currentTeam))
        setSelectedTeamId(created.id)
        showSnackbar({ type: 'success', message: `Team ${created.display_name} created` })
      } catch (error) {
        rollback(snapshot, error)
        setSelectedTeamId(
          selectedTeamId && snapshot.some(currentTeam => currentTeam.id === selectedTeamId)
            ? selectedTeamId
            : snapshot[0]?.id ?? null,
        )
      }
    },

    async updateMetadata(team: WorkspaceTeam, metadata: { display_name: string; workspace: string }) {
      await runOptimisticTeamUpdate(
        team,
        { ...team, ...metadata },
        () => api.updateWorkspaceTeamMetadata(team.id, metadata),
      ).catch(() => {})
    },

    async addMember(team: WorkspaceTeam, agent: AgentStatus) {
      const agentId = displayAgentId(agent)
      if (team.member_details.some(member => member.agent_id === agentId)) return
      const optimisticTeam = {
        ...team,
        members: [...team.members, agentId],
        member_details: [
          ...team.member_details,
          {
            agent_id: agentId,
            display_name: agent.display_name || agentId,
            role_id: fallbackRoleId,
            role_explicitly_assigned: false,
          },
        ],
      }
      const snapshot = teams
      commitMemberMove(optimisticTeam, agentId)
      try {
        commitMemberMove(await api.putWorkspaceTeamMember(team.id, agentId, {}), agentId)
      } catch (error) {
        rollback(snapshot, error)
      }
    },

    async changeMemberRole(team: WorkspaceTeam, agentId: string, roleId: string) {
      const optimisticTeam = {
        ...team,
        role_assignments: { ...team.role_assignments, [agentId]: roleId },
        member_details: team.member_details.map(member =>
          member.agent_id === agentId
            ? { ...member, role_id: roleId, role_explicitly_assigned: true }
            : member,
        ),
      }
      await runOptimisticTeamUpdate(team, optimisticTeam, () =>
        api.putWorkspaceTeamMember(team.id, agentId, { role_id: roleId }),
      ).catch(() => {})
    },

    async removeMember(team: WorkspaceTeam, agentId: string) {
      const nextAssignments = { ...team.role_assignments }
      delete nextAssignments[agentId]
      const optimisticTeam = {
        ...team,
        members: team.members.filter(memberId => memberId !== agentId),
        member_details: team.member_details.filter(member => member.agent_id !== agentId),
        role_assignments: nextAssignments,
      }
      await runOptimisticTeamUpdate(team, optimisticTeam, () =>
        api.deleteWorkspaceTeamMember(team.id, agentId),
      ).catch(() => {})
    },

    async createRole(team: WorkspaceTeam, roleId: string, role: WorkspaceTeamRole) {
      const optimisticTeam = {
        ...team,
        roles: { ...team.roles, [roleId]: role },
      }
      await runOptimisticTeamUpdate(team, optimisticTeam, () =>
        api.putWorkspaceTeamRole(team.id, roleId, role),
      ).catch(() => {})
    },

    async saveRole(team: WorkspaceTeam, roleId: string, role: WorkspaceTeamRole) {
      const completeRole = {
        display_name: role.display_name,
        cao_tools: role.cao_tools || [],
        mcp_servers: role.mcp_servers || {},
        providers: role.providers || {},
        deletable: role.deletable ?? roleId !== fallbackRoleId,
      }
      const optimisticTeam = {
        ...team,
        roles: { ...team.roles, [roleId]: completeRole },
      }
      await runOptimisticTeamUpdate(team, optimisticTeam, () =>
        api.putWorkspaceTeamRole(team.id, roleId, completeRole),
      ).catch(() => {})
    },

    async deleteRole(team: WorkspaceTeam, roleId: string) {
      if (roleId === fallbackRoleId || team.roles[roleId]?.deletable === false) return
      const nextRoles = { ...team.roles }
      delete nextRoles[roleId]
      const nextAssignments = { ...team.role_assignments }
      Object.entries(nextAssignments).forEach(([agentId, assignedRole]) => {
        if (assignedRole === roleId) delete nextAssignments[agentId]
      })
      const optimisticTeam = {
        ...team,
        roles: nextRoles,
        role_assignments: nextAssignments,
        member_details: team.member_details.map(member =>
          member.role_id === roleId ? { ...member, role_id: fallbackRoleId, role_explicitly_assigned: false } : member,
        ),
      }
      await runOptimisticTeamUpdate(team, optimisticTeam, () =>
        api.deleteWorkspaceTeamRole(team.id, roleId),
      ).catch(() => {})
    },

    emptyTeam(id: string, displayName: string, workspace: string): WorkspaceTeam {
      return {
        id,
        display_name: displayName,
        workspace,
        roles: { [fallbackRoleId]: defaultMemberRole() },
        role_assignments: {},
        members: [],
        member_details: [],
        diagnostics: [],
      }
    },
  }
}

function withoutMember(team: WorkspaceTeam, agentId: string): WorkspaceTeam {
  if (!team.member_details.some(member => member.agent_id === agentId) && !team.role_assignments[agentId]) {
    return team
  }
  const nextAssignments = { ...team.role_assignments }
  delete nextAssignments[agentId]
  return {
    ...team,
    members: team.members.filter(memberId => memberId !== agentId),
    member_details: team.member_details.filter(member => member.agent_id !== agentId),
    role_assignments: nextAssignments,
  }
}

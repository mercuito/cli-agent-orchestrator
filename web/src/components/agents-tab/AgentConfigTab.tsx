import { useEffect, useRef, useState } from 'react'
import { Edit3, RotateCcw, Save } from 'lucide-react'
import { api, AgentStatus, WorkspaceTeam } from '../../api'
import { useProviderCatalog } from '../../hooks/useProviderCatalog'
import { useProviderSchema } from '../../hooks/useProviderSchema'
import { formatAgentTomlExcluding, parseAgentTomlDraft } from './agentTomlSerialization'
import {
  AgentStructuredForm,
  STRUCTURED_FIELD_KEYS,
  StructuredFields,
} from './AgentStructuredForm'

interface AgentConfigTabProps {
  agent: AgentStatus
  onAgentUpdated: (agent: AgentStatus) => void
  onSaveError?: (message: string) => void
  defaultEditing?: boolean
}

function readStructuredFields(agent: AgentStatus): StructuredFields {
  return {
    display_name: agent.config.display_name ?? '',
    description: agent.config.description ?? '',
    cli_provider: agent.config.cli_provider ?? '',
    model: agent.config.model ?? '',
    reasoning_effort: agent.config.reasoning_effort ?? '',
  }
}

export function AgentConfigTab({
  agent,
  onAgentUpdated,
  onSaveError,
  defaultEditing = false,
}: AgentConfigTabProps) {
  const providerSchema = useProviderSchema()
  const [editing, setEditing] = useState(defaultEditing)
  const [structuredDraft, setStructuredDraft] = useState<StructuredFields>(() =>
    readStructuredFields(agent),
  )
  const [tomlDraft, setTomlDraft] = useState(() =>
    defaultEditing ? formatAgentTomlExcluding(agent.config, STRUCTURED_FIELD_KEYS) : '',
  )
  const [promptDraft, setPromptDraft] = useState(() => (defaultEditing ? agent.config.prompt : ''))
  const [saveError, setSaveError] = useState<string | null>(null)
  const [teams, setTeams] = useState<WorkspaceTeam[]>([])
  const [workspaceTeamDraft, setWorkspaceTeamDraft] = useState<string>(() => agent.config.workspace.team ?? '')
  const [saving, setSaving] = useState(false)
  const isFirstRenderRef = useRef(true)
  const visibleStructuredFields = editing ? structuredDraft : readStructuredFields(agent)
  const selectedProviderSchema =
    providerSchema.schemas?.find(schema => schema.name === visibleStructuredFields.cli_provider) ??
    null
  const providerCatalog = useProviderCatalog(
    selectedProviderSchema?.name ?? null,
    providerSchema.status === 'ready' && selectedProviderSchema?.model_catalog_available === true,
  )

  useEffect(() => {
    if (isFirstRenderRef.current) {
      isFirstRenderRef.current = false
      return
    }
    setEditing(false)
    setSaveError(null)
    setStructuredDraft(readStructuredFields(agent))
    setWorkspaceTeamDraft(agent.config.workspace.team ?? '')
  }, [agent.agent_id])

  useEffect(() => {
    api.listWorkspaceTeams().then(setTeams).catch(() => setTeams([]))
  }, [])

  const handleEdit = () => {
    setEditing(true)
    setStructuredDraft(readStructuredFields(agent))
    setWorkspaceTeamDraft(agent.config.workspace.team ?? '')
    setTomlDraft(formatAgentTomlExcluding(agent.config, STRUCTURED_FIELD_KEYS))
    setPromptDraft(agent.config.prompt)
    setSaveError(null)
  }

  const handleCancel = () => {
    setEditing(false)
    setSaveError(null)
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const rawPayload = parseAgentTomlDraft(tomlDraft)
      const structuredPayload = {
        display_name: structuredDraft.display_name,
        description: structuredDraft.description === '' ? null : structuredDraft.description,
        cli_provider: structuredDraft.cli_provider,
        model: structuredDraft.model === '' ? null : structuredDraft.model,
        reasoning_effort:
          structuredDraft.reasoning_effort === '' ? null : structuredDraft.reasoning_effort,
      }
      const updated = await api.updateAgent(agent.agent_id, {
        ...rawPayload,
        ...structuredPayload,
        workspace: { team: workspaceTeamDraft.trim() || null },
        prompt: promptDraft,
      })
      onAgentUpdated(updated)
      setEditing(false)
    } catch (error) {
      const message = error instanceof Error ? error.message : `Failed to update ${agent.agent_id}`
      setSaveError(message)
      onSaveError?.(message)
    } finally {
      setSaving(false)
    }
  }

  if (providerSchema.status === 'loading') {
    return (
      <div className="rounded-lg border border-gray-700/50 bg-gray-950 p-3 text-xs text-gray-400">
        Loading provider schema…
      </div>
    )
  }

  if (providerSchema.status === 'error' || providerSchema.schemas === null) {
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-900/60 bg-red-950/50 p-3 text-xs text-red-200"
      >
        Failed to load provider schema: {providerSchema.error ?? 'unknown error'}
      </div>
    )
  }

  const schemas = providerSchema.schemas
  const inactiveLocalGrantNames = Object.keys(agent.effective_tool_access?.inactive_local_grants ?? {})
  const rawLocalAccessFallbackNotice =
    Boolean(editing ? workspaceTeamDraft : agent.config.workspace.team)
  const selectedWorkspaceTeam = teams.find(team => team.id === workspaceTeamDraft)
  const derivedWorkspace = editing
    ? workspaceTeamDraft
      ? selectedWorkspaceTeam?.workspace ?? agent.config.workspace.derived_workspace ?? 'unknown'
      : 'default'
    : agent.config.workspace.derived_workspace ?? 'default'

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">
            Configuration
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            {agent.display_name} ·{' '}
            {agent.active ? `Running in ${agent.active_terminal_id}` : 'Stopped'}
          </p>
        </div>
        {editing ? (
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-medium rounded-lg transition-colors"
              aria-label={`Save ${agent.agent_id}`}
            >
              <Save size={13} /> Save
            </button>
            <button
              onClick={handleCancel}
              className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-medium rounded-lg transition-colors"
              aria-label={`Cancel ${agent.agent_id}`}
            >
              <RotateCcw size={13} /> Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={handleEdit}
            className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-medium rounded-lg transition-colors"
            aria-label={`Edit ${agent.agent_id}`}
          >
            <Edit3 size={13} /> Edit
          </button>
        )}
      </div>

      <AgentStructuredForm
        agentId={agent.agent_id}
        values={visibleStructuredFields}
        schemas={schemas}
        catalog={providerCatalog.catalog}
        catalogStatus={providerCatalog.status}
        editing={editing}
        saveError={saveError}
        onChange={setStructuredDraft}
      />

      <section
        aria-label="Workspace team"
        className="rounded-lg border border-gray-700/50 bg-gray-950 p-3"
      >
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
          Workspace team
        </h4>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-xs text-gray-400">
            Team
            {editing ? (
              <select
                aria-label={`${agent.agent_id} workspace team`}
                value={workspaceTeamDraft}
                onChange={event => setWorkspaceTeamDraft(event.target.value)}
                className="mt-1 w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
              >
                <option value="">Standalone</option>
                {teams.map(team => (
                  <option key={team.id} value={team.id}>
                    {team.display_name} ({team.id})
                  </option>
                ))}
              </select>
            ) : (
              <span className="mt-1 block font-mono text-sm text-gray-300">
                {agent.config.workspace.team ?? 'standalone'}
              </span>
            )}
          </label>
          <label className="block text-xs text-gray-400">
            Workspace
            <input
              aria-label={`${agent.agent_id} derived workspace`}
              value={derivedWorkspace}
              readOnly
              disabled={!!(editing && workspaceTeamDraft)}
              className="mt-1 w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-400 disabled:cursor-not-allowed disabled:opacity-70"
            />
          </label>
        </div>
      </section>

      {editing ? (
        <div className="space-y-3">
          <details className="rounded-lg border border-gray-700/50 bg-gray-950">
            <summary className="cursor-pointer select-none px-3 py-2 text-xs font-semibold uppercase tracking-wide text-gray-400 hover:text-gray-200">
              Raw agent.toml (unstructured fields)
            </summary>
            {rawLocalAccessFallbackNotice && (
              <p className="border-t border-amber-500/20 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
                {inactiveLocalGrantNames.length
                  ? `ToolService marks these agent-local tool grants inactive for this teamed agent: ${inactiveLocalGrantNames.join(', ')}. `
                  : 'This teamed agent inherits tool access from its workspace team role. '}
                Edits affect only standalone fallback behavior after leaving the team.
              </p>
            )}
            <textarea
              aria-label={`${agent.agent_id} agent.toml`}
              value={tomlDraft}
              onChange={event => setTomlDraft(event.target.value)}
              className="w-full min-h-[200px] resize-y rounded-b-lg border-t border-gray-700/50 bg-gray-950 p-3 font-mono text-xs leading-5 text-gray-200 focus:border-emerald-500 focus:outline-none"
            />
          </details>
          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              prompt.md
            </h4>
            <textarea
              aria-label={`${agent.agent_id} prompt.md`}
              value={promptDraft}
              onChange={event => setPromptDraft(event.target.value)}
              className="w-full min-h-[180px] resize-y rounded-lg border border-gray-700 bg-gray-950 p-3 font-mono text-xs leading-5 text-gray-200 focus:border-emerald-500 focus:outline-none"
            />
          </div>
          {saveError && (
            <p
              role="alert"
              className="rounded-lg border border-red-900/60 bg-red-950/50 px-3 py-2 text-xs text-red-200"
            >
              {saveError}
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <details className="rounded-lg border border-gray-700/50 bg-gray-950">
            <summary className="cursor-pointer select-none px-3 py-2 text-xs font-semibold uppercase tracking-wide text-gray-400 hover:text-gray-200">
              Raw agent.toml (unstructured fields)
            </summary>
            {rawLocalAccessFallbackNotice && (
              <p className="border-t border-amber-500/20 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
                {inactiveLocalGrantNames.length
                  ? `ToolService marks these agent-local tool grants inactive for this teamed agent: ${inactiveLocalGrantNames.join(', ')}. `
                  : 'This teamed agent inherits tool access from its workspace team role. '}
                These values affect only standalone fallback behavior after leaving the team.
              </p>
            )}
            <pre className="max-h-[300px] overflow-auto rounded-b-lg border-t border-gray-700/50 bg-gray-950 p-3 font-mono text-xs leading-5 text-gray-200 whitespace-pre-wrap">
              {formatAgentTomlExcluding(agent.config, STRUCTURED_FIELD_KEYS)}
            </pre>
          </details>
          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              prompt.md
            </h4>
            <pre className="max-h-[260px] overflow-auto rounded-lg border border-gray-700/50 bg-gray-950 p-3 font-mono text-xs leading-5 text-gray-200 whitespace-pre-wrap">
              {agent.config.prompt}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}

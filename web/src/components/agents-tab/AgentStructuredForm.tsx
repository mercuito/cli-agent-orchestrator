import { useEffect } from 'react'
import { ProviderCatalog, ProviderSchema } from '../../api'

/**
 * Five tier-1 fields the structured form owns. These are the only fields
 * the form serializes into the merged save payload; everything else
 * round-trips through the raw TOML escape hatch.
 */
export interface StructuredFields {
  display_name: string
  description: string
  cli_provider: string
  model: string
  reasoning_effort: string
}

export const STRUCTURED_FIELD_KEYS: ReadonlyArray<keyof StructuredFields> = [
  'display_name',
  'description',
  'cli_provider',
  'model',
  'reasoning_effort',
]

/**
 * Map a structured-field name onto the substring the backend embeds in
 * its ``agents.<id>.<field>`` error messages. The form surfaces the
 * server's 400 detail inline against the offending input by checking
 * whether the detail string contains the field key.
 */
function fieldErrorMatches(field: keyof StructuredFields, errorDetail: string | null): boolean {
  if (!errorDetail) return false
  return errorDetail.includes(field)
}

interface AgentStructuredFormProps {
  agentId: string
  values: StructuredFields
  schemas: ProviderSchema[]
  catalog: ProviderCatalog | null
  catalogStatus: 'idle' | 'loading' | 'ready' | 'error'
  editing: boolean
  saveError: string | null
  onChange: (next: StructuredFields) => void
}

export function AgentStructuredForm({
  agentId,
  values,
  schemas,
  catalog,
  catalogStatus,
  editing,
  saveError,
  onChange,
}: AgentStructuredFormProps) {
  const selectedSchema = schemas.find(schema => schema.name === values.cli_provider) ?? null
  const catalogModels = catalog?.models ?? []
  const selectedModel = catalogModels.find(model => model.id === values.model) ?? null
  const modelOptions =
    values.model && !catalogModels.some(model => model.id === values.model)
      ? [
          {
            id: values.model,
            display_name: values.model,
            reasoning_efforts: [],
            thinking_supported: false,
            max_input_tokens: null,
            max_output_tokens: null,
          },
          ...catalogModels,
        ]
      : catalogModels
  const discoveredEfforts = selectedModel
    ? selectedModel.reasoning_efforts
    : Array.from(new Set(catalogModels.flatMap(model => model.reasoning_efforts)))
  const effortOptions = discoveredEfforts
  const unsupportedReasoningEffort =
    editing &&
    catalogStatus === 'ready' &&
    selectedSchema?.model_catalog_available === true &&
    values.reasoning_effort !== '' &&
    !discoveredEfforts.includes(values.reasoning_effort)
  const modelDisabled =
    selectedSchema?.model_catalog_available !== true ||
    catalogStatus !== 'ready' ||
    catalogModels.length === 0
  const reasoningEffortDisabled =
    selectedSchema?.model_catalog_available !== true ||
    catalogStatus !== 'ready' ||
    effortOptions.length === 0

  const updateField = <K extends keyof StructuredFields>(
    field: K,
    value: StructuredFields[K],
  ): void => {
    onChange({ ...values, [field]: value })
  }

  const updateModel = (modelId: string): void => {
    const nextModel = catalogModels.find(model => model.id === modelId) ?? null
    const nextEfforts = nextModel?.reasoning_efforts ?? []
    onChange({
      ...values,
      model: modelId,
      reasoning_effort: nextEfforts.includes(values.reasoning_effort)
        ? values.reasoning_effort
        : '',
    })
  }

  useEffect(() => {
    if (!unsupportedReasoningEffort) return
    onChange({ ...values, reasoning_effort: '' })
  }, [onChange, unsupportedReasoningEffort, values])

  return (
    <section
      aria-label="Structured fields"
      className="rounded-lg border border-gray-700/50 bg-gray-950 p-3"
    >
      <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Structured fields
      </h4>
      <div className="space-y-3">
        <StructuredRow
          label="Display name"
          field="display_name"
          agentId={agentId}
          saveError={saveError}
        >
          {editing ? (
            <input
              aria-label={`${agentId} display_name`}
              value={values.display_name}
              onChange={event => updateField('display_name', event.target.value)}
              className="w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
            />
          ) : (
            <span className="font-mono text-sm text-gray-300">{values.display_name}</span>
          )}
        </StructuredRow>

        <StructuredRow
          label="Description"
          field="description"
          agentId={agentId}
          saveError={saveError}
        >
          {editing ? (
            <textarea
              aria-label={`${agentId} description`}
              value={values.description}
              onChange={event => updateField('description', event.target.value)}
              rows={3}
              className="w-full resize-y rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
            />
          ) : (
            <span className="font-mono text-sm text-gray-300 whitespace-pre-wrap">
              {values.description || <em className="text-gray-600">(none)</em>}
            </span>
          )}
        </StructuredRow>

        <StructuredRow
          label="CLI provider"
          field="cli_provider"
          agentId={agentId}
          saveError={saveError}
        >
          {editing ? (
            <select
              aria-label={`${agentId} cli_provider`}
              value={values.cli_provider}
              onChange={event =>
                onChange({
                  ...values,
                  cli_provider: event.target.value,
                  model: '',
                  reasoning_effort: '',
                })
              }
              className="w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
            >
              {schemas.map(schema => (
                <option key={schema.name} value={schema.name}>
                  {schema.name}
                  {schema.installed ? '' : '  (not installed)'}
                </option>
              ))}
            </select>
          ) : (
            <span className="font-mono text-sm text-gray-300">{values.cli_provider}</span>
          )}
        </StructuredRow>

        <StructuredRow
          label="Model"
          field="model"
          agentId={agentId}
          saveError={saveError}
        >
          {editing ? (
            <select
              aria-label={`${agentId} model`}
              value={values.model}
              onChange={event => updateModel(event.target.value)}
              disabled={modelDisabled}
              title={
                modelDisabled
                  ? `${values.cli_provider} has no loaded model catalog with model options`
                  : undefined
              }
              className="w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">(unset)</option>
              {modelOptions.map(model => (
                <option key={model.id} value={model.id}>
                  {model.display_name === model.id
                    ? model.id
                    : `${model.display_name} (${model.id})`}
                </option>
              ))}
            </select>
          ) : (
            <span className="font-mono text-sm text-gray-300">
              {values.model || <em className="text-gray-600">(none)</em>}
            </span>
          )}
        </StructuredRow>

        <StructuredRow
          label="Reasoning effort"
          field="reasoning_effort"
          agentId={agentId}
          saveError={saveError}
        >
          {editing ? (
            <select
              aria-label={`${agentId} reasoning_effort`}
              value={values.reasoning_effort}
              onChange={event => updateField('reasoning_effort', event.target.value)}
              disabled={reasoningEffortDisabled}
              title={
                reasoningEffortDisabled
                  ? `${values.cli_provider} has no loaded model catalog with reasoning_effort options`
                  : undefined
              }
              className="w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">(unset)</option>
              {effortOptions.map(effort => (
                <option key={effort} value={effort}>
                  {effort}
                </option>
              ))}
            </select>
          ) : (
            <span className="font-mono text-sm text-gray-300">
              {values.reasoning_effort || <em className="text-gray-600">(unset)</em>}
            </span>
          )}
        </StructuredRow>
      </div>
    </section>
  )
}

interface StructuredRowProps {
  label: string
  field: keyof StructuredFields
  agentId: string
  saveError: string | null
  children: React.ReactNode
}

function StructuredRow({ label, field, agentId, saveError, children }: StructuredRowProps) {
  const hasError = fieldErrorMatches(field, saveError)
  return (
    <div className="grid gap-1 sm:grid-cols-[140px_minmax(0,1fr)] sm:items-start">
      <label
        htmlFor={`${agentId}-${field}`}
        className="text-xs font-medium text-gray-400 sm:pt-1.5"
      >
        {label}
      </label>
      <div>
        {children}
        {hasError && saveError && (
          <p role="alert" className="mt-1 text-xs text-red-300">
            {saveError}
          </p>
        )}
      </div>
    </div>
  )
}

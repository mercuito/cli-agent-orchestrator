import { ProviderSchema } from '../../api'

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
  editing: boolean
  saveError: string | null
  onChange: (next: StructuredFields) => void
}

export function AgentStructuredForm({
  agentId,
  values,
  schemas,
  editing,
  saveError,
  onChange,
}: AgentStructuredFormProps) {
  const selectedSchema = schemas.find(schema => schema.name === values.cli_provider) ?? null
  const supportedEfforts = selectedSchema?.supported_reasoning_efforts ?? null
  const suggestedModels = selectedSchema?.suggested_models ?? null
  const reasoningEffortDisabled = supportedEfforts === null

  const updateField = <K extends keyof StructuredFields>(
    field: K,
    value: StructuredFields[K],
  ): void => {
    onChange({ ...values, [field]: value })
  }

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
              onChange={event => updateField('cli_provider', event.target.value)}
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
            <>
              <input
                aria-label={`${agentId} model`}
                value={values.model}
                onChange={event => updateField('model', event.target.value)}
                list={suggestedModels ? `${agentId}-model-suggestions` : undefined}
                className="w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none"
              />
              {suggestedModels && (
                <datalist id={`${agentId}-model-suggestions`}>
                  {suggestedModels.map(model => (
                    <option key={model} value={model} />
                  ))}
                </datalist>
              )}
            </>
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
                  ? `${values.cli_provider} does not support reasoning_effort`
                  : undefined
              }
              className="w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 focus:border-emerald-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">(unset)</option>
              {(supportedEfforts ?? []).map(effort => (
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

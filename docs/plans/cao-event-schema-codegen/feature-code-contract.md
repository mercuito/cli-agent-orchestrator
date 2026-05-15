# Feature Code Contract — CAO Event Schema Codegen

Cross-task implementation-steering obligations for the CAO Event Schema
Codegen refactor. This is the entry artifact: the work is a pure refactor
with no externally observable behavior change. The end-state pivots the
CAO event type system to a stable internal/storage discriminator and a
schema-driven TypeScript codegen pipeline while preserving the existing
public timeline API response envelope.

## Scope Preamble

### Structure being changed

- CAO event declaration: every event class declares a stable instance-level
  `kind` discriminator field and is constructed via Pydantic dataclasses
  instead of stdlib dataclasses.
- Internal/storage discriminator: persisted events identify their type by
  a stable `kind` string (`"<provider>.<event_name>"`) rather than by the
  Python module-qualified class name
  (`event_type_key = f"{module}.{qualname}"`).
- Event serializer class lookup: `CaoEventSerializerRegistry` indexes
  registered event classes by `kind` and resolves them via explicit
  registration at startup, retiring dynamic module import for unknown
  type keys.
- API timeline response compatibility: timeline routes keep their
  existing externally observable response envelope, including the
  `event_type_key` field and object-shaped `event_data` payloads.
- Frontend event type generation pipeline: TypeScript event payload types
  are generated from a repo-local schema document via `openapi-typescript`
  without changing the public timeline API response schema. The hand-rolled
  `scripts/generate_cao_event_type_keys.py` and
  `web/src/generated/caoEventTypeKeys.ts` are retired.
- Database `cao_events` table: a `kind` column is added as the canonical
  discriminator column.

### Code surfaces affected

- `src/cli_agent_orchestrator/runtime/events.py`
- `src/cli_agent_orchestrator/linear/workspace_events.py`
- `src/cli_agent_orchestrator/events/__init__.py`
- `src/cli_agent_orchestrator/events/serialization.py`
- `src/cli_agent_orchestrator/clients/cao_event_store.py`
- `src/cli_agent_orchestrator/services/agent_identity_timeline.py`
- `src/cli_agent_orchestrator/api/main.py` (timeline-related response
  models and routes only)
- `web/src/components/timelineEventViews.tsx` and
  `web/src/components/timelineEventViews/`
- `web/src/generated/` (replace existing generated TS event constants
  with `openapi-typescript` output)
- `web/package.json` and `web/package-lock.json` (codegen script and
  dependency wiring)
- `scripts/generate_cao_event_type_keys.py` (retired)
- Affected tests: `test/events/test_cao_event_persistence.py`,
  `test/api/test_agent_identity_routes.py`,
  `test/runtime/test_agent_runtime.py`, frontend timeline tests under
  `web/src/test/`.

### Code surfaces outside scope

- `CaoEventDispatcher` publish/subscribe semantics and handler registration
  in `src/cli_agent_orchestrator/events/__init__.py`. The dispatcher's
  external contract (publish, subscribe, handler invocation) is preserved.
- Event production callsites — the runtime, Linear webhook ingestion,
  Linear tool-result publishers, and other event publishers — do not
  change beyond accepting the new field defaults transparently.
- Non-event API routes and non-event Pydantic response models in
  `src/cli_agent_orchestrator/api/main.py`.
- Non-event frontend components and non-event API call sites.
- The runtime monitor, inbox, terminal management, workspace context
  resolution, and other subsystems that consume events.

### Feature-wide obligations that must not be violated

The binding preservation obligations are the ID'd clauses below:

- Public timeline API response compatibility is governed by F-CC-4.
- Persisted event migration and reconstruction are governed by F-CC-6.
- Event equality and protocol attribute preservation are governed by
  F-CC-9.
- Task-boundary proof preservation is governed by the task-specific
  preservation baseline clauses in
  `feature-test-contract.md`.

## Applicable Feature-Level Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [implementation-clause-verifiability](../../planning/methodology/criteria/feature-code-contract/implementation-clause-verifiability.md) | Always applies; every clause below names the surface it governs and what counts as compliance. |
| [stable-code-clause-ids](../../planning/methodology/criteria/feature-code-contract/stable-code-clause-ids.md) | Always applies; every clause carries a stable `F-CC-<n>` ID for slicing in `feature-tasks.md`, handoffs, and Code Contract Defences. |
| [backward-compatibility-policy](../../planning/methodology/criteria/feature-code-contract/backward-compatibility-policy.md) | The contract reshapes every event class, the serializer, the storage schema, API response construction internals, and the frontend codegen pipeline while preserving public timeline API compatibility through F-CC-4. |
| [replaced-surface-lifecycle-policy](../../planning/methodology/criteria/feature-code-contract/replaced-surface-lifecycle-policy.md) | The contract replaces `event_type_key` as the serializer/storage discriminator, the dynamic-import serializer fallback, the hand-rolled codegen script, and the legacy storage column; F-CC-7 and F-CC-10 state the end-state for each while preserving API response compatibility under F-CC-4. |
| [caller-migration-policy](../../planning/methodology/criteria/feature-code-contract/caller-migration-policy.md) | Reshaped surfaces have callers in event factories, the persistence layer, the timeline service, the API routes, and the frontend timeline panel; F-CC-8, F-CC-11, and F-CC-12 enumerate the migration policy and discovery method per surface. |
| [persistent-state-migration-policy](../../planning/methodology/criteria/feature-code-contract/persistent-state-migration-policy.md) | The `cao_events` table schema is reshaped and pre-existing rows must be backfilled; F-CC-6 states the migration shape, owning-task scope, and failure-handling policy. |

## Architectural Commitments

- **F-CC-1 — Events declare a stable `kind` discriminator field.** Every
  CAO event class (every member of `LINEAR_CAO_EVENTS` and
  `RUNTIME_CAO_EVENTS`) declares an instance field
  `kind: Literal["<discriminator>"]` with the same literal as its default
  value. Discriminator strings follow the format
  `"<provider_or_source>.<event_name>"` (for example
  `"linear.agent_mentioned"`, `"cao_runtime.agent_runtime_lifecycle"`,
  `"cao_runtime.runtime_workspace"`). Existing `ClassVar event_name` and
  `ClassVar provider_name` declarations remain unchanged; `kind` is the
  internal/storage discriminator going forward.

  **Illustration.** Compliant declaration on a Linear event class:

  ```python
  @pydantic.dataclasses.dataclass(frozen=True, kw_only=True)
  class LinearAgentMentionedEvent(LinearIssueContextEvent):
      event_name: ClassVar[str] = "agent_mentioned"
      kind: Literal["linear.agent_mentioned"] = "linear.agent_mentioned"
  ```

  Not compliant: `kind: str = "linear.agent_mentioned"` — the wide `str`
  type can't drive Pydantic's `Discriminator("kind")` because the union
  branches can't be narrowed to a single class.
  `kind: ClassVar[Literal["linear.agent_mentioned"]] = "..."` — the
  class-level value never appears on instances, so the JSON Schema for
  the event omits the discriminator field and the generated event schema
  cannot be assembled.

- **F-CC-2 — Event classes are Pydantic dataclasses.** Every CAO event
  class is declared with
  `@pydantic.dataclasses.dataclass(frozen=True, kw_only=True)` instead of
  the stdlib `@dataclass`. All other class members — `ClassVar`
  annotations, `NewType`-typed fields, `field(default_factory=...)`
  defaults, frozen/kw_only semantics, inheritance from
  `_AgentRuntimeEventMetadata` and `LinearIssueContextEvent`, computed
  `@property` accessors — are preserved unchanged except for the single
  `kind` instance field required by F-CC-1. `is_dataclass` remains true;
  `dataclasses.fields` exposes every pre-existing field with its existing
  type/default/init behavior plus the new `kind` field exactly once; and
  `typing.get_type_hints` preserves all pre-existing hints while adding
  the `kind` literal hint.

  **Illustration.** Compliant decorator swap, leaving the class body
  unchanged:

  ```python
  # Before
  from dataclasses import dataclass

  @dataclass(frozen=True, kw_only=True)
  class LinearAgentMentionedEvent(LinearIssueContextEvent):
      event_name: ClassVar[str] = "agent_mentioned"
      # ... fields unchanged

  # After
  from pydantic.dataclasses import dataclass

  @dataclass(frozen=True, kw_only=True)
  class LinearAgentMentionedEvent(LinearIssueContextEvent):
      event_name: ClassVar[str] = "agent_mentioned"
      # ... fields unchanged
  ```

  Recognition of compliance: `is_dataclass(LinearAgentMentionedEvent)`
  returns `True` after the swap; every pre-existing
  `dataclasses.fields(...)` entry remains present with the same metadata,
  and the only added field entry is `kind`;
  `get_type_hints(LinearAgentMentionedEvent)["event_id"]` is still
  `CaoEventId`, while `get_type_hints(LinearAgentMentionedEvent)["kind"]`
  is the class-specific `Literal[...]`. Not compliant: replacing the decorator with
  `pydantic.BaseModel` inheritance — the serializer's `is_dataclass`
  guards and `_decode_value`'s `target_type is CaoEventId` branches stop
  matching, and inheritance from `_AgentRuntimeEventMetadata` /
  `LinearIssueContextEvent` would need to be refactored.

- **F-CC-3 — Serializer registry indexes event classes by `kind`.**
  `CaoEventSerializerRegistry` in
  `src/cli_agent_orchestrator/events/serialization.py` registers and
  resolves event classes via their `kind` literal value rather than via
  `f"{module}.{qualname}"`. `serialize_cao_event` emits `kind` as the
  internal/storage type key; `deserialize_cao_event` looks up the class by `kind` against
  the populated registry. The dynamic-import fallback (`_import_event_type`)
  is removed; an unrecognized `kind` raises `UnknownCaoEventError`. Event
  classes are registered explicitly at startup through the existing
  `register_cao_event_serializers` / `register_runtime_cao_events` /
  `register_linear_cao_events` entry points.

  **Illustration.** Compliant registry shape (paraphrased; task-level
  Coding Code Contracts decide private attribute names, decoding helper
  signatures, and other research-dependent details):

  ```python
  # Before
  class CaoEventSerializerRegistry:
      def __init__(self):
          self._event_types_by_key: dict[str, type[CaoEvent]] = {}

      def serialize(self, event):
          return event_type_key(type(event)), _dumps(...)   # "<module>.<qualname>"

      def deserialize(self, type_key, payload_json):
          event_type = self._event_types_by_key.get(type_key)
          if event_type is None:
              event_type = _import_event_type(type_key)     # dynamic import fallback
          ...

  # After
  class CaoEventSerializerRegistry:
      def __init__(self):
          self._event_types_by_kind: dict[str, type[CaoEvent]] = {}

      def serialize(self, event):
          return event.kind, _dumps(...)                    # stable storage string

      def deserialize(self, kind, payload_json):
          event_type = self._event_types_by_kind.get(kind)
          if event_type is None:
              raise UnknownCaoEventError(f"no registered event class for kind: {kind}")
          ...
  ```

  Not compliant: keeping `_import_event_type` as a silent fallback for
  unknown `kind` values — the contract's purpose is to decouple the
  storage discriminator from Python module paths, so dynamic resolution by `kind`
  through `importlib` would re-introduce the coupling under a new name.

- **F-CC-4 — Public timeline API response shape is preserved.** Timeline
  event response models and route outputs in
  `src/cli_agent_orchestrator/api/main.py` preserve the externally
  observable response envelope currently consumed by the frontend:
  `event_type_key` remains present with the same Python module-qualified
  class-name value shape, and `event_data` remains an object payload whose
  existing keys and values are not renamed, removed, or wrapped by the
  refactor. Any typed event instances or generated schema artifacts used
  during response construction are internal implementation details; they
  do not require clients to consume `kind` from the public timeline
  response.

  Not compliant: removing `event_type_key` from
  `AgentIdentityTimelineEventResponse`, changing it to a `kind` value, or
  requiring frontend/runtime API consumers to read `event_data.kind` to
  preserve existing timeline behavior. Not compliant: changing the
  `/openapi.json` timeline response schema in a way that removes the
  existing `event_type_key` property or changes `event_data` away from the
  object-shaped payload contract the current API exposes.

- **F-CC-5 — Frontend event payload types are schema-generated.**
  TypeScript type declarations for CAO event payloads are produced by
  running `openapi-typescript` against a repo-local schema document
  generated from the backend CAO event declarations. The generated output
  lives at a single version-controlled path under `web/src/generated/`
  and is the only source of CAO event payload field declarations consumed
  by the frontend event-view registry in
  `web/src/components/timelineEventViews.tsx` and the known event view
  modules under `web/src/components/timelineEventViews/`. This codegen
  path does not change the public timeline API response shape governed by
  F-CC-4. `scripts/generate_cao_event_type_keys.py` and
  `web/src/generated/caoEventTypeKeys.ts` are removed or replaced by the
  new generated artifact, with any still-needed public `event_type_key`
  constants produced by the new pipeline.

- **F-CC-6 — `cao_events` storage uses `kind` as the sole
  discriminator.** The `cao_events` table stores each event's `kind`
  discriminator in a `kind` column. As part of this feature pre-existing
  rows are migrated in place: the `kind` value is backfilled (the
  migration may derive it from the legacy `event_type_key`) and the
  `event_type_key` column is dropped. The migration runs in a single
  task of this feature (named in `feature-tasks.md` once tasks are
  sliced); the same task drops the `event_type_key` column. Rows whose
  legacy `event_type_key` does not resolve to a registered event class
  block the migration — the contract provides no skip, quarantine, or
  default-value path for unresolved rows; an unresolved row triggers a
  contract escalation rather than absorption at the task altitude.
  After the migration lands, all read paths (`get_cao_event`,
  `list_cao_events_*`, and `agent_identity_timeline` reconstruction)
  resolve the event class via `kind` exclusively; no read path
  references `event_type_key`.

- **F-CC-7 — Backend/storage replacement surfaces are removed with their
  replacements.** The backend/storage refactor's end state contains
  exactly one implementation of each event-declaration, serializer, and
  storage concern it reshapes. Backward-compatibility shims, parallel
  code paths, "deprecated but kept" surfaces, dual-write storage
  layouts, and transitional re-exports of removed symbols are out of
  scope for these backend/storage surfaces. The following surfaces are
  removed in the same task that lands their replacements:

  - The `event_type_key` column on the `cao_events` table.
  - The `event_type_key()` and `_import_event_type()` helpers in
    `src/cli_agent_orchestrator/events/serialization.py`.
  - The stdlib `dataclasses.dataclass` decorator applied to any member of
    `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`.

  **Illustration.** Not compliant: keeping `_import_event_type` with a `# deprecated`
  comment and an unchanged body — the function is removed, not
  annotated.

  Not compliant: writing new rows with both `kind` and `event_type_key`
  populated "so older readers can still parse them" — there are no
  older readers within scope; readers are migrated as part of this
  feature.

- **F-CC-8 — Backend/storage caller migration is exhaustive and
  verifiable.** For each reshaped backend/storage surface, every caller
  within the affected code surfaces migrates to the new shape in the task
  that reshapes that surface. The implementing task runs the named
  discovery methods, and its Coding Code Contract Defence records the
  resulting caller set and migration outcome per caller. A caller
  discovered after the task lands and missed by the discovery method is
  treated as a contract escalation, not a task-local fix.

  - **Event constructors** (every class in `LINEAR_CAO_EVENTS +
    RUNTIME_CAO_EVENTS`): discovery by `rg` over `src/` and `test/`
    matching each class name (or equivalent AST scan). Migration
    expectation: no caller source change is required, because the new
    `kind` field carries a default value matching the class's
    discriminator string (per F-CC-1). A caller that fails to construct
    after F-CC-1 / F-CC-2 land blocks the task.

  - **Serializer entry points** (`serialize_cao_event`,
    `deserialize_cao_event`): discovery by
    `rg 'serialize_cao_event|deserialize_cao_event' src/ test/`.
    Callers pass `kind` strings; the legacy `event_type_key` argument
    is gone.

  - **Internal/storage references to `event_type_key`**: discovery by
    `rg 'event_type_key' src/ test/`. Every match is classified as
    public API compatibility (deferred to F-CC-12) or internal/storage
    usage (migrated to `kind` or removed alongside its surrounding code,
    consistent with F-CC-7's removal of the helper and column).

  **Illustration.** Not compliant: a task migrates the callers it
  noticed by reading adjacent files and reports the slice complete; a
  caller in a less-obvious module was missed because the named
  discovery command was never run. The Coding Code Contract Defence
  claims "all callers migrated" without command output backing the
  claim.

  Good: the task runs each named discovery command, records the
  resulting caller set in its Coding Code Contract Defence, and
  migrates or removes every match. The Defence cites the commands and
  their matched paths.

- **F-CC-9 — Event reconstruction equality and protocol attributes are
  preserved.** Round-tripping a published event through the persistence
  layer yields an instance equal to the original under dataclass equality
  before and after the discriminator pivot. The `CaoEvent` protocol's
  required attributes (`event_id`, `source`, `occurred_at`,
  `correlation_id`, `causation_id`) remain present on every member of
  `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS` with their existing types.

- **F-CC-10 — Frontend codegen replacement surfaces are removed with
  their replacements.** The frontend codegen refactor's end state
  contains one generated source for event payload typing and public
  compatibility constants. `scripts/generate_cao_event_type_keys.py` and
  `web/src/generated/caoEventTypeKeys.ts` are removed or replaced in the
  same task that lands the new schema-generated artifact. Frontend
  hand-typed Python-style event type key strings are removed from
  `web/src/`; public API compatibility constants, if still needed, come
  from the new generated artifact.

  Not compliant: keeping `scripts/generate_cao_event_type_keys.py` as a
  thin re-export wrapper over the new `openapi-typescript` output to
  avoid touching callers.

- **F-CC-11 — Frontend codegen caller migration is exhaustive and
  verifiable.** Frontend callers of the retired generated event constants
  and hand-typed event key strings, plus codegen script wiring that
  invokes the retired generator, migrate to the new generated artifact
  and `openapi-typescript` pipeline in the task that lands it. Discovery is exhaustive over
  `web/src/components/timelineEventViews.tsx`, every file under
  `web/src/components/timelineEventViews/`, and
  `rg 'caoEventTypeKeys|event_type_key|cli_agent_orchestrator\\.' web/src/`,
  plus `rg 'generate_cao_event_type_keys|generate:event-types|openapi-typescript' web/package.json web/package-lock.json`.
  The task's Coding Code Contract Defence records every matched caller
  and whether it migrated to generated payload typing, generated public
  API compatibility constants, or the new codegen command.

- **F-CC-12 — Public timeline compatibility callers are classified and
  defended.** Timeline response construction internals in
  `src/cli_agent_orchestrator/services/agent_identity_timeline.py` and
  timeline route handlers in `src/cli_agent_orchestrator/api/main.py`
  preserve the public envelope required by F-CC-4 after the persistence
  and frontend codegen replacements have landed. Discovery is by the
  type-checker sweep, existing API route tests, frontend timeline tests,
  and `rg 'event_type_key' src/ test/ web/src/`. Every remaining match is
  classified as public API compatibility, generated compatibility
  constant usage, or a contract violation that must be removed before the
  feature completes.

## Feature-Specific Code Obligations

None beyond the architectural commitments above. Lower-level code-shape
obligations whose `when:` requires research to evaluate — Pydantic
`config`/`ConfigDict` choices, factory function adjustments,
`NewType` annotation handling at the field boundary, migration mechanics
for the new column, retirement choreography for the legacy generator
script, frontend registry self-registration shape after the generated
schema import — belong in each task's Coding Code Contract.

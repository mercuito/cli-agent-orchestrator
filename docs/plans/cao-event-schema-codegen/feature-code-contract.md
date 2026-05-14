# Feature Code Contract — CAO Event Schema Codegen

Cross-task implementation-steering obligations for the CAO Event Schema
Codegen refactor. This is the entry artifact: the work is a pure refactor
with no externally observable behavior change. The end-state pivots the
CAO event type system to a stable wire-format discriminator and an
OpenAPI-driven TypeScript codegen pipeline so that frontend event views
can narrow on typed event payloads.

## Scope Preamble

### Structure being changed

- CAO event declaration: every event class declares a stable instance-level
  `kind` discriminator field and is constructed via Pydantic dataclasses
  instead of stdlib dataclasses.
- Wire-format discriminator: persisted and transmitted events identify
  their type by a stable `kind` string (`"<provider>.<event_name>"`)
  rather than by the Python module-qualified class name
  (`event_type_key = f"{module}.{qualname}"`).
- Event serializer class lookup: `CaoEventSerializerRegistry` indexes
  registered event classes by `kind` and resolves them via explicit
  registration at startup, retiring dynamic module import for unknown
  type keys.
- API timeline response shape: timeline event-data fields on the API
  surface are typed as a Pydantic discriminated union over the full set
  of CAO event classes, producing `oneOf` + `discriminator` in OpenAPI.
- Frontend event type generation pipeline: TypeScript event types are
  generated from the FastAPI-emitted OpenAPI document via
  `openapi-typescript`. The hand-rolled
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
- `web/package.json` (codegen script wiring)
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

- No persisted event is lost during the storage migration: every row in
  `cao_events` at feature start is present and reconstructable (under
  the new `kind`-keyed shape) at feature end.
- Event reconstruction equality is preserved: round-tripping a published
  event through the persistence layer yields an instance equal to the
  original under dataclass equality, before and after the discriminator
  pivot.
- The `CaoEvent` protocol's required attributes (`event_id`, `source`,
  `occurred_at`, `correlation_id`, `causation_id`) remain present on
  every event class with their existing types.
- Existing event-driven tests across backend and frontend (per the
  affected tests list above) remain green at every task boundary.

## Applicable Feature-Level Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [implementation-clause-verifiability](../../planning/methodology/criteria/feature-code-contract/implementation-clause-verifiability.md) | Always applies; every clause below names the surface it governs and what counts as compliance. |
| [stable-code-clause-ids](../../planning/methodology/criteria/feature-code-contract/stable-code-clause-ids.md) | Always applies; every clause carries a stable `F-CC-<n>` ID for slicing in `feature-tasks.md`, handoffs, and Code Contract Defences. |
| [backward-compatibility-policy](../../planning/methodology/criteria/feature-code-contract/backward-compatibility-policy.md) | The contract reshapes every event class, the serializer, API response models, the storage schema, and the frontend codegen pipeline; F-CC-7 carries the policy across all reshaped surfaces. |
| [replaced-surface-lifecycle-policy](../../planning/methodology/criteria/feature-code-contract/replaced-surface-lifecycle-policy.md) | The contract replaces `event_type_key` as the wire-format identifier, the dynamic-import serializer fallback, the hand-rolled codegen script, and the legacy storage column; F-CC-7's removal list states the end-state for each. |
| [caller-migration-policy](../../planning/methodology/criteria/feature-code-contract/caller-migration-policy.md) | Reshaped surfaces have callers in event factories, the persistence layer, the timeline service, the API routes, and the frontend timeline panel; F-CC-8 enumerates the migration policy and discovery method per surface. |
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
  wire-format discriminator going forward.

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
  the event omits the discriminator field and the OpenAPI `oneOf` cannot
  be assembled.

- **F-CC-2 — Event classes are Pydantic dataclasses.** Every CAO event
  class is declared with
  `@pydantic.dataclasses.dataclass(frozen=True, kw_only=True)` instead of
  the stdlib `@dataclass`. All other class members — `ClassVar`
  annotations, `NewType`-typed fields, `field(default_factory=...)`
  defaults, frozen/kw_only semantics, inheritance from
  `_AgentRuntimeEventMetadata` and `LinearIssueContextEvent`, computed
  `@property` accessors — are preserved unchanged. `is_dataclass`,
  `dataclasses.fields`, and `typing.get_type_hints` continue to return
  the same shape on every event class.

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
  returns `True` after the swap; `dataclasses.fields(...)` returns the
  same field tuple as before;
  `get_type_hints(LinearAgentMentionedEvent)["event_id"]` is still
  `CaoEventId`. Not compliant: replacing the decorator with
  `pydantic.BaseModel` inheritance — the serializer's `is_dataclass`
  guards and `_decode_value`'s `target_type is CaoEventId` branches stop
  matching, and inheritance from `_AgentRuntimeEventMetadata` /
  `LinearIssueContextEvent` would need to be refactored.

- **F-CC-3 — Serializer registry indexes event classes by `kind`.**
  `CaoEventSerializerRegistry` in
  `src/cli_agent_orchestrator/events/serialization.py` registers and
  resolves event classes via their `kind` literal value rather than via
  `f"{module}.{qualname}"`. `serialize_cao_event` emits `kind` as the
  type key; `deserialize_cao_event` looks up the class by `kind` against
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
          return event.kind, _dumps(...)                    # stable wire-format string

      def deserialize(self, kind, payload_json):
          event_type = self._event_types_by_kind.get(kind)
          if event_type is None:
              raise UnknownCaoEventError(f"no registered event class for kind: {kind}")
          ...
  ```

  Not compliant: keeping `_import_event_type` as a silent fallback for
  unknown `kind` values — the contract's purpose is to decouple the wire
  format from Python module paths, so dynamic resolution by `kind`
  through `importlib` would re-introduce the coupling under a new name.

- **F-CC-4 — Timeline API responses expose a discriminated event union.**
  The `event_data` field on timeline event response models in
  `src/cli_agent_orchestrator/api/main.py` (currently
  `AgentIdentityTimelineEventResponse`,
  `AgentIdentityCausationRelatedEventsResponse`, and
  `AgentIdentityRelatedEventsResponse`) is typed
  `Annotated[Union[<every CAO event class>], pydantic.Discriminator("kind")]`.
  The FastAPI-emitted OpenAPI document served at `/openapi.json`
  contains, for each affected response, a JSON Schema `oneOf` with a
  `discriminator` keyed on `kind`, carrying exactly one branch per
  member of `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`.

  **Illustration.** Compliant response-model shape:

  ```python
  from typing import Annotated, Union
  from pydantic import BaseModel, Discriminator

  CaoEventUnion = Annotated[
      Union[
          LinearAgentMentionedEvent,
          LinearIssueDelegatedToAgentEvent,
          # ... every member of LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS
          AgentRuntimeLifecycleEvent,
      ],
      Discriminator("kind"),
  ]

  class AgentIdentityTimelineEventResponse(BaseModel):
      event_id: str
      occurred_at: datetime
      # ... other envelope fields
      event_data: CaoEventUnion
  ```

  Resulting OpenAPI shape under
  `components.schemas.AgentIdentityTimelineEventResponse.properties.event_data`:

  ```json
  {
    "oneOf": [
      { "$ref": "#/components/schemas/LinearAgentMentionedEvent" },
      { "$ref": "#/components/schemas/LinearIssueDelegatedToAgentEvent" }
    ],
    "discriminator": {
      "propertyName": "kind",
      "mapping": {
        "linear.agent_mentioned": "#/components/schemas/LinearAgentMentionedEvent",
        "linear.issue_delegated_to_agent": "#/components/schemas/LinearIssueDelegatedToAgentEvent"
      }
    }
  }
  ```

  Not compliant: leaving `event_data: Dict[str, Any]` and emitting the
  discriminator only as a sibling string field on the response envelope.
  The OpenAPI schema would lack `oneOf` / `discriminator` and
  `openapi-typescript` would generate a single opaque `Record<string,
  unknown>` instead of a narrowing TS union.

- **F-CC-5 — Frontend event types are OpenAPI-generated.** TypeScript
  type declarations for CAO events are produced by running
  `openapi-typescript` against the FastAPI-emitted OpenAPI document. The
  generated output lives at a single version-controlled path under
  `web/src/generated/` and is the only source of CAO event type
  declarations consumed by the frontend. The frontend event-view
  registry in `web/src/components/timelineEventViews.tsx` and the known
  event view modules under `web/src/components/timelineEventViews/`
  consume the generated discriminated union and narrow on `kind`.
  `scripts/generate_cao_event_type_keys.py` and
  `web/src/generated/caoEventTypeKeys.ts` are removed.

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

- **F-CC-7 — Replaced surfaces are removed, not retained.** The
  refactor's end state contains exactly one implementation of each
  concern this contract reshapes. Backward-compatibility shims, parallel
  code paths, "deprecated but kept" surfaces, dual-write storage
  layouts, and transitional re-exports of removed symbols are out of
  scope for this feature. The following surfaces no longer exist
  anywhere in the repository at feature end:

  - The `event_type_key` field on any event response model or wire-format
    payload.
  - The `event_type_key` column on the `cao_events` table.
  - The `event_type_key()` and `_import_event_type()` helpers in
    `src/cli_agent_orchestrator/events/serialization.py`.
  - The stdlib `dataclasses.dataclass` decorator applied to any member of
    `LINEAR_CAO_EVENTS + RUNTIME_CAO_EVENTS`.
  - `scripts/generate_cao_event_type_keys.py` and
    `web/src/generated/caoEventTypeKeys.ts`.
  - Frontend hand-typed Python-style event type key strings
    (e.g. `"cli_agent_orchestrator.linear.workspace_events.LinearAgentMentionedEvent"`)
    in any `web/src/` source file.

  Tasks that introduce a replacement surface remove the surface it
  replaces in the same change set unless the removal would break an
  unmigrated dependency owned by another task in this feature; in that
  case the deferring task names the follow-up task in this feature that
  performs the removal. No removal is deferred past the last task of
  this feature, and no removal is deferred to a follow-up feature.

  **Illustration.** Not compliant: leaving `event_type_key: str` on
  `AgentIdentityTimelineEventResponse` alongside the new typed
  `event_data: CaoEventUnion` "in case the frontend still wants it" —
  the frontend's consumption is in scope (F-CC-5) and both ends migrate
  together.

  Not compliant: keeping `_import_event_type` with a `# deprecated`
  comment and an unchanged body — the function is removed, not
  annotated.

  Not compliant: writing new rows with both `kind` and `event_type_key`
  populated "so older readers can still parse them" — there are no
  older readers within scope; readers are migrated as part of this
  feature.

  Not compliant: keeping `scripts/generate_cao_event_type_keys.py` as a
  thin re-export wrapper over the new `openapi-typescript` output to
  avoid touching callers — there are no remaining callers within scope.

- **F-CC-8 — Caller migration is exhaustive and verifiable.** For each
  reshaped surface, every caller within the affected code surfaces (per
  the scope preamble) migrates to the new shape during this feature; no
  caller is retained on the old shape (reinforces F-CC-7). Each
  reshaped surface names a discovery method that the implementing task
  runs to enumerate its callers; the task's Coding Code Contract
  Defence records the resulting caller set and the migration outcome
  per caller. A caller discovered after the task lands and missed by
  the discovery method is treated as a contract escalation, not a
  task-local fix.

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

  - **Timeline event-data response-model field**: discovery by the
    type-checker sweep after the `event_data` annotation changes to
    the discriminated union (F-CC-4). Callers —
    `src/cli_agent_orchestrator/services/agent_identity_timeline.py`
    and the timeline route handlers in
    `src/cli_agent_orchestrator/api/main.py` — construct response
    payloads with typed event instances rather than `Dict[str, Any]`
    payloads.

  - **Frontend event-view registry and known event view modules**:
    discovery is exhaustive over
    `web/src/components/timelineEventViews.tsx` and every file under
    `web/src/components/timelineEventViews/`. Callers consume the
    OpenAPI-generated discriminated union (F-CC-5) and narrow on
    `kind`; no caller imports `web/src/generated/caoEventTypeKeys.ts`
    after F-CC-5 lands.

  - **References to `event_type_key`**: discovery by
    `rg 'event_type_key' src/ test/ web/src/`. Every match is migrated
    to read `kind` or removed alongside its surrounding code
    (consistent with F-CC-7's removal of the wire field, helper, and
    column).

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

## Feature-Specific Code Obligations

None beyond the architectural commitments above. Lower-level code-shape
obligations whose `when:` requires research to evaluate — Pydantic
`config`/`ConfigDict` choices, factory function adjustments,
`NewType` annotation handling at the field boundary, migration mechanics
for the new column, retirement choreography for the legacy generator
script, frontend registry self-registration shape after the OpenAPI
import — belong in each task's Coding Code Contract.

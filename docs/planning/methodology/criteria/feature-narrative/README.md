# Feature Narrative Criteria Catalog

Reusable criteria for authoring a narrative — the user-facing event timeline
of behavior-changing work. Narratives are not authored for pure refactor
work; pure refactors enter at the Code Contract
instead.

This catalog is a library. A criterion has no authority until a narrative
artifact selects it. Catalog authoring follows the rules in
[../README.md](../README.md).

## How to use

The narrative is a feature-level artifact at
`docs/plans/<feature>/feature-narrative.md`. To assemble:

1. Browse this catalog — read each criterion's `when` field
2. Select criteria that apply
3. Add an **Applicable Criteria** table near the top of the narrative with
   one-line rationale per selection
4. Author the narrative against the selected criteria

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [domain-language-only](domain-language-only.md) | Always |
| [event-timeline-granularity](event-timeline-granularity.md) | Always |
| [events-have-observable-outcomes](events-have-observable-outcomes.md) | Always |
| [scenario-grounding](scenario-grounding.md) | Always |
| [vocabulary-grounded-in-event-timeline](vocabulary-grounded-in-event-timeline.md) | Always |

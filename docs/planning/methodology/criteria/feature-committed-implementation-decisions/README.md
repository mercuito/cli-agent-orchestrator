# Committed Implementation Decisions Criteria Catalog

Reusable criteria for the committed-implementation-decisions artifact —
the running ledger of settled facts from landed tasks that future tasks
must remain compatible with.

This catalog is a library. A criterion has no authority until the
committed-implementation-decisions artifact selects it. Catalog authoring
follows the rules in [../README.md](../README.md).

## How to use

The committed-implementation-decisions artifact is a feature-level ledger
at `docs/plans/<feature>/committed-implementation-decisions.md`. To
assemble:

1. Browse this catalog — read each criterion's `when` field
2. Select criteria that apply
3. Add an **Applicable Criteria** table near the top of the artifact with
   one-line rationale per selection
4. Author entries against the selected criteria as tasks promote them

See [creating-a-feature-committed-implementation-decisions](../../creating-a-feature-committed-implementation-decisions.md)
for full assembly guidance.

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [self-sufficient-entries](self-sufficient-entries.md) | Always |
| [defence-promoted-additions-only](defence-promoted-additions-only.md) | Always |

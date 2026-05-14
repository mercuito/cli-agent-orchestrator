---
name: persistent-state-migration-policy
when: When the contract changes the shape of persistent storage — database tables, on-disk formats, durable queues, cache key shapes — that holds pre-existing data.
---

# Persistent-State Migration Policy Is Stated

For each reshaped persistent-state surface that holds pre-existing
data, the contract states the data's fate: migrated in place,
backfilled into a new column or table, decoded on read through a
transitional decoder, retained in legacy form indefinitely, or
discarded. When migration is in-place or backfilled, the policy names
when the migration runs (a task in this feature, a one-shot deploy
script, on first read, etc.) and what happens to rows that fail
migration. The policy is stated as a clause carrying an `F-CC-<n>` ID.
The contract does not omit the policy on a reshaped persistent-state
surface that holds pre-existing data.

## Illustrations

**Bad — data fate implied.** The contract changes the storage schema
but says nothing about pre-existing rows. An implementer adds the new
column nullable, writes a transitional decoder that falls back to the
old column shape, and leaves both columns in place indefinitely.
**Good:** A clause states "pre-existing rows are backfilled by a
migration that runs in task t-2; the legacy column is dropped in the
same task; rows that fail the backfill block the migration."

**Bad — migration deferred without owner.** "Pre-existing data will be
migrated later." An implementer ships the new shape with no migration
and adds a transitional decoder, deferring the work to no one.
**Good:** "Pre-existing data is migrated by task t-2 of this feature;
no transitional decoder is added; rows that fail migration block the
feature."

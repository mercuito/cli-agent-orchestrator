---
name: sqlite-rebuild-migration-proof
when: A SQLite migration rebuilds, renames, drops, or replaces a table.
---

# SQLite Rebuild Migrations Prove Dependent Schema

When a SQLite migration rebuilds a table, tests must model enough of the
pre-migration schema graph to catch dependent schema breakage. A test that
creates only the changed table, or creates current ORM metadata before running
the migration, is not enough when existing dependent tables can affect runtime
writes.

The proof should run the production migration path or closest scoped migration
sequence, then assert both the migrated data and the resulting schema
relationships that matter for runtime behavior. When foreign keys are involved,
assert the final foreign key targets and perform one representative write
through the dependent table.

If no dependent schema exists, the test or completion note may state that the
rebuild has no dependent tables and does not need this extra proof.

## Illustrations

**Bad - isolated rebuilt table.** A migration test creates only
`inbox_notifications`, runs the migration, and asserts that new columns exist.
It never creates the tables that reference `inbox_notifications`.
**Good:** The test starts from the old `inbox_notifications` shape plus a
dependent marker table, runs the migration path, asserts the marker table's
foreign key points at the final `inbox_notifications`, and inserts through the
marker table.

**Bad - current metadata fixture.** A test uses current ORM metadata to create
all tables, then runs a migration meant for an older schema.
**Good:** The test builds the relevant old schema shape explicitly or through a
checked-in legacy schema fixture, then runs the migration.


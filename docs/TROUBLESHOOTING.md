# Troubleshooting

## "Cannot connect to <db>: database does not exist"

The target DB doesn't exist yet. Either:
- Drop `--skip-init` (so the script creates it for you), OR
- Pre-create the DB with `odoo -d <db> -i base,...` then re-run with `--skip-init`

## "Module installation failed" during Phase 0

The `odoo -d <db> -i <modules>` step failed inside the container. Check:

1. The modules listed in `--modules` actually exist in the container's `addons_path`. Common causes:
   - `helpdesk_mgmt` missing → install OCA `helpdesk` repo into your image
   - `mass_mailing` missing → it's now in `marketing`
2. Container has enough disk for the install (`df -h` inside the container)
3. Module dependencies don't conflict with each other

Run the same command manually to see the full error:
```bash
docker exec <odoo-container> odoo -d test-init -i base,account --stop-after-init --no-http
```

## "ERROR: relation X does not exist" on import

The Enterprise dump references a table that doesn't exist in the Community schema. This is normal for Enterprise-only tables (they show up in the planner as "Enterprise-only"). If the table is unexpected:

- Check if it was created by a custom module not in `--modules`
- Add it to `--skip-tables-extra`

## "null value in column X violates not-null constraint"

The Community schema has a `NOT NULL` column that the Enterprise dump's row doesn't populate. Add the column to `--not-null-fixups`:

```json
{
  "the_table": {
    "the_column": ["'sensible_default'", null]
  }
}
```

For complex defaults that need referencing other columns:
```json
{
  "product_template": {
    "uom_po_id": ["1", "SET uom_po_id = uom_id WHERE uom_po_id IS NULL"]
  }
}
```

## Status line says "fixups n/a: some_column"

The built-in `NOT_NULL_FIXUPS` names a column your target does not have. That
is expected, not an error: the fixup map is static, while the target schema is
whatever your `--modules` list produced. `product_template.ticket_active`, for
one, only exists once the event modules are installed. The fixup is skipped,
the rest still run, and the `NOT NULL` constraints dropped for the import are
put back.

If you see "fixups failed: some_column: ..." instead, that one did run and
errored. The rows are still in — the import commits before the fixups — but the
column may be left holding NULLs where Community wants a value. Fix the default
and re-run, or patch the column by hand.

## "duplicate key value violates unique constraint"

A sequence got out of sync. Phase 5 should have handled this, but if you used `--skip-init` on a DB that already had data, the sequences may have been reset incorrectly. Re-run with full init or manually fix:

```sql
SELECT setval('seq_name', (SELECT MAX(id) FROM linked_table));
```

## "permission denied for table X" during import

The DB user (`--db-user`) lacks privileges. The init phase creates the DB owned by this user, so this should not happen. If you're using `--skip-init` against a DB created by a different user, grant ownership:

```sql
ALTER DATABASE "<target-db>" OWNER TO "<db-user>";
REASSIGN OWNED BY <other_user> TO "<db-user>";
```

## Filestore copy: "no such file or directory"

The `--filestore` path isn't right. The Enterprise SaaS dump nests filestore under `filestore/<db_name>/`, so for a dump originally named `my-saas-db`:

```bash
--filestore /tmp/enterprise-dump/filestore/my-saas-db
```

Not `/tmp/enterprise-dump/filestore/`.

## "could not access file '$libdir/...': No such file or directory" during init

The PostgreSQL extension required by Odoo (e.g., `unaccent`, `pg_trgm`) isn't installed in the container's Postgres image. Install the corresponding `postgresql-contrib` package, or rebuild the DB image with:

```dockerfile
FROM postgres:15
RUN apt-get update && apt-get install -y postgresql-contrib
```

## After migration: "No database selected" in browser

The new DB isn't visible because of `dbfilter`. Edit `odoo.conf`:

```ini
dbfilter = ^(staging|<your-new-db>)$
```

Then `docker restart <odoo-container>`. Revert the dbfilter when done testing.

## After migration: emails not sending

That's intentional — neutralization disables `ir_mail_server`. To re-enable for production:

```sql
UPDATE ir_mail_server SET active = true;
UPDATE ir_config_parameter SET value = 'https://your.real.domain' WHERE key = 'web.base.url';
UPDATE ir_config_parameter SET value = 'your.real.domain' WHERE key = 'mail.catchall.domain';
```

## After migration: "no such language 'fr_CA'"

Activate any non-default languages explicitly:

```sql
UPDATE res_lang SET active = true WHERE code = 'fr_CA';
```

Or via the UI: Settings → Translations → Languages → Activate.

## "Errors: 5 tables failed" in summary

Read the per-table error message printed in Phase 4. Most failures are:

- **CHECK constraint violation**: usually a column with a Community-only enum value missing. Check the constraint definition (`SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = '...'`) and add the relevant fixup.
- **FK orphan**: the referenced row was in a skipped table. Either un-skip the parent table (rare — usually it's correctly skipped) or accept the data loss.

The migration is "partial success" — most data made it. Check row counts in the verify phase to gauge severity.

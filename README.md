# odoo18-ee2ce — Odoo 18 Enterprise → Community migration

Import an **Odoo 18 Enterprise SaaS** database dump into a self-hosted **Community** instance, the way you wished `pg_restore` could.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Odoo: 18.0](https://img.shields.io/badge/odoo-18.0-714B67.svg)](https://www.odoo.com)

## Why this exists

Odoo Enterprise SaaS exports are full `pg_dump` SQL files, but they **can't be loaded directly into a Community instance**. Enterprise and Community have deeply incompatible metadata: different module registries, different view definitions, different action paths, hundreds of Enterprise-only columns, and entire tables that don't exist on the Community side. Attempting to import the full dump leads to an endless chain of conflicts.

This tool sidesteps the problem with a **fresh-init + business-data injection** strategy:

1. Drop and re-create the target database with a freshly initialized Community Odoo instance (correct module set, correct metadata)
2. Parse the Enterprise `dump.sql` for `COPY` data blocks
3. Import **only business data** (journal entries, partners, tasks, mail messages, etc.) with **automatic column filtering** so Enterprise-only columns are silently dropped
4. Skip every framework / metadata table — Community already has the right ones

The result is a Community database with all your business data, ready to use, no `-u base` patching required.

## How it works — the eight phases

| Phase | What it does |
|-------|--------------|
| **0** | Drops the target DB, runs `odoo -d <db> -i <modules>` to create a fresh Community DB with correct metadata |
| **1** | Single-pass parses the Enterprise `dump.sql` for `COPY ... FROM stdin` blocks |
| **2** | Connects to the freshly-init'd target DB, catalogs all tables |
| **3** | Plans the import: which tables to import, which to skip (framework / Enterprise-only) |
| **4** | Streams each `COPY` block through psycopg2 with column intersection filtering. `session_replication_role = 'replica'` disables FK triggers during import; `NOT_NULL_FIXUPS` relaxes Community-only mandatory columns |
| **5** | Resets every sequence to `max(linked_column)` to avoid PK collisions on the next insert |
| **6** | Copies the extracted Enterprise filestore into the Odoo container |
| **7** | Neutralizes the new DB: disables outbound mail, regenerates `database.uuid`, sets a safe `web.base.url`, ensures `mail_alias_domain` has at least one row |
| **8** | Prints row counts for verification |

## What gets imported vs skipped

**Imported** (~140 tables): `account_move`, `account_move_line`, `account_account`, `account_journal`, `res_partner`, `crm_lead`, `project_project`, `project_task`, `sale_order`, `account_analytic_line`, `mail_message`, `blog_post`, `ir_attachment`, and all related junction/child tables.

**Skipped** (~800 tables):
- **Framework metadata**: `ir_model_data`, `ir_ui_view`, `ir_act_window`, `ir_module_module`, etc. — managed by Community module installation.
- **Reference data**: `res_country`, `res_currency`, `uom_uom` — already seeded by base module CSVs.
- **Enterprise-only**: `documents_*`, `sign_*`, `planning_*`, `knowledge_*`, `sale_subscription_*`, `studio_*`, etc. — no Community equivalent.
- **Security groups**: `res_groups`, `res_groups_users_rel` — managed by module install.

See `odoo18_ee2ce/config/skip_tables.py` for the full list.

## Requirements

- Python 3.9+ (`psycopg2-binary` is the only runtime dep)
- Docker CLI (containers must be running)
- An Odoo 18 Community Docker container (DB + Odoo)
- An extracted Odoo 18 Enterprise SaaS dump (`manifest.json` + `dump.sql` + `filestore/`)

## Install

```bash
# Via uv (recommended)
uv tool install git+https://github.com/bluefoxconsultant/odoo18-ee2ce

# Or pipx
pipx install git+https://github.com/bluefoxconsultant/odoo18-ee2ce

# Or local checkout
git clone https://github.com/bluefoxconsultant/odoo18-ee2ce
cd odoo18-ee2ce
pip install -e .
```

## Quick start

```bash
# 1. Extract the Enterprise SaaS dump
mkdir -p /tmp/enterprise-dump
cd /tmp/enterprise-dump
unzip /path/to/enterprise-backup.zip
# → manifest.json, dump.sql, filestore/<dbname>/

# 2. Run the migration
DB_PASSWORD=mypassword odoo18-ee2ce \
    --dump /tmp/enterprise-dump/dump.sql \
    --filestore /tmp/enterprise-dump/filestore/<dbname> \
    --target-db my-community-db \
    --db-container my-postgres-container \
    --odoo-container my-odoo-container \
    --db-user odoo

# 3. After completion, widen dbfilter and access the new DB:
#    Edit odoo.conf:    dbfilter = ^my-community-db$
#    Restart container: docker restart my-odoo-container
#    Visit:             http://localhost:8069/web
```

## CLI reference

```
odoo18-ee2ce \
    --dump PATH                      Path to Enterprise dump.sql (REQUIRED)
    --target-db NAME                 Target DB name (will be DROPPED if --skip-init not set) (REQUIRED)
    --db-container NAME              PostgreSQL Docker container name (REQUIRED)
    --odoo-container NAME            Odoo Docker container name (REQUIRED)
    --db-user NAME                   DB user / role (REQUIRED)

    --filestore PATH                 Filestore dir (default: <dump-dir>/filestore)
    --modules LIST                   Modules to install during init (default: see config/default_modules.py)
    --db-host HOST                   DB host (auto-detected from Docker if omitted)
    --db-port PORT                   DB port (default: 5432)
    --db-password PASS               DB password (prefer env vars or .env file)

    --skip-init                      Don't drop & re-init target DB (assume already done)
    --skip-filestore                 Don't copy filestore
    --dry-run                        Parse and plan only, no DB changes

    --skip-tables-extra PATH         Text file with additional tables to skip (one per line)
    --not-null-fixups PATH           JSON file with extra NOT NULL relaxation rules (merged with defaults)
    --verify-counts PATH             JSON file mapping table → expected_min_count for verification
    --neutralize-base-url URL        web.base.url to set during neutralization (default: localhost:8069)
```

### Password resolution order

1. `--db-password` CLI argument
2. `PGPASSWORD` environment variable
3. `DB_PASSWORD` environment variable
4. `DB_PASSWORD=` or `POSTGRES_PASSWORD=` in `.env` file (cwd or parent)

## Adapting for your instance

**Custom modules.** Override `--modules` with a comma-separated list. The default covers `base, account, contacts, crm, project, sale, sale_management, hr, hr_timesheet, website, website_blog, mass_mailing, calendar, helpdesk_mgmt, survey, product`. If your install needs `stock`, `mrp`, `purchase`, etc., add them.

**Extra skip rules.** Pass `--skip-tables-extra skip.txt` with one table name per line:
```
my_custom_table
my_custom_module_helper
```

**Extra NOT NULL relaxations.** If you hit a `NOT NULL violation` on import, add an entry via `--not-null-fixups fixups.json`:
```json
{
  "my_table": {
    "my_required_col": ["'default_value'", null]
  }
}
```
Format is `[default_value_sql, optional_custom_update_sql]`. If the second element is null, the importer runs `UPDATE my_table SET my_required_col = 'default_value' WHERE my_required_col IS NULL`.

**Verify counts.** To compare row counts against expected minimums:
```json
{
  "res_partner": 100,
  "account_move": 500
}
```

## Limitations

- **Odoo 18 only.** The skip lists and NOT NULL fixups are version-specific. Older versions need different rules.
- **No Studio support.** `x_studio_*` fields are dropped on import. If your Enterprise instance uses Studio extensively, port custom fields to a Community module (e.g., [bf_studio_light](https://github.com/bluefoxconsultant/odoo-modules/tree/main/bf_studio_light)) before migration.
- **One-shot import.** Creates a new database; doesn't merge into an existing one.
- **Filestore assumes Docker volumes.** The `docker cp` approach requires the Odoo container to be running.
- **Enterprise-only data is lost.** Modules without Community/OCA equivalents (Knowledge articles, Sign requests, Planning shifts, Marketing automation flows, Subscriptions) have their data skipped. Small datasets can be manually recreated; larger ones require custom migration.
- **OCA helpdesk swap.** Enterprise `helpdesk` data is not auto-mapped to OCA `helpdesk_mgmt`; the v1 attempt at this proved too brittle.

## Lessons learned

These hard-won insights drove the design — see `docs/ARCHITECTURE.md` for the full story.

- **Never import framework metadata** (`ir_model_data`, `ir_ui_view`, `ir_act_window`, etc.) from Enterprise into Community. The schemas differ massively.
- **Never import reference data** (`res_country`, `res_currency`, `uom_uom`). The fresh DB already has them; overwriting breaks `ir_model_data` xml_id references.
- **Never use `TRUNCATE ... CASCADE`** on an Odoo database. It cascades through all FK chains and can wipe the entire DB.
- **`session_replication_role = 'replica'`** disables FK triggers but NOT `NOT NULL` or `CHECK` constraints — that's why `NOT_NULL_FIXUPS` exists.
- **Reset with `'origin'`** (not `'DEFAULT'` — that's invalid in PostgreSQL).
- **Fresh DB init creates correct metadata.** All Community module views, actions, menus, security rules are created by `odoo -i`. No need to merge Enterprise metadata.

## Contributing

Bug reports and PRs welcome. The most useful contributions are:

- New entries in `config/not_null_fixups.py` for tables you hit
- New entries in `config/skip_tables.py` for Enterprise modules added in newer Odoo 18 builds
- Test fixtures in `tests/fixtures/` covering edge cases

## License

MIT — see [LICENSE](LICENSE).

Built and used in production by [Blue Fox Inc.](https://bluefoxconsultant.com) to migrate the company's own SaaS instance to self-hosted Community in February 2026.

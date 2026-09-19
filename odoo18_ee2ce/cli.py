"""Command-line entry point for the Enterprise → Community migration."""

import argparse
import json
import os
import subprocess
import sys
import time

import psycopg2
import psycopg2.extensions

from odoo18_ee2ce.config import (
    DEFAULT_MODULES,
    NOT_NULL_FIXUPS,
    should_skip,
)
from odoo18_ee2ce.db import connect, load_db_creds
from odoo18_ee2ce.docker_helpers import docker_exec, get_db_host
from odoo18_ee2ce.filestore import copy_filestore
from odoo18_ee2ce.leftovers import collect, export_leftovers
from odoo18_ee2ce.importer import import_table, import_table_relaxed
from odoo18_ee2ce.neutralize import neutralize
from odoo18_ee2ce.parser import parse_dump
from odoo18_ee2ce.schema import get_all_tables, get_table_columns
from odoo18_ee2ce.sequences import fix_sequences
from odoo18_ee2ce.verify import verify


def parse_args():
    parser = argparse.ArgumentParser(
        prog="odoo18-ee2ce",
        description="Migrate an Odoo 18 Enterprise pg_dump into a fresh Community DB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # Full migration (init + import + filestore + neutralize):
  odoo18-ee2ce \\
      --dump /tmp/enterprise/dump.sql \\
      --filestore /tmp/enterprise/filestore \\
      --target-db my-db \\
      --db-container my-pg \\
      --odoo-container my-odoo \\
      --db-user odoo

  # Dry run (parse and plan only):
  odoo18-ee2ce --dump /tmp/enterprise/dump.sql \\
               --target-db my-db --db-container my-pg \\
               --odoo-container my-odoo --db-user odoo --dry-run

  # Skip DB init (target already initialized):
  odoo18-ee2ce ... --skip-init

Password resolution order:
  1. --db-password
  2. PGPASSWORD env var
  3. DB_PASSWORD env var
  4. DB_PASSWORD= or POSTGRES_PASSWORD= in .env file (cwd or parent)
        """,
    )
    parser.add_argument("--dump", required=True,
                        help="Path to Enterprise dump.sql")
    parser.add_argument("--filestore", default=None,
                        help="Path to extracted Enterprise filestore directory "
                             "(default: <dump-dir>/filestore)")
    parser.add_argument("--target-db", required=True,
                        help="Target database name (will be DROPPED if --skip-init not set)")
    parser.add_argument("--modules", default=DEFAULT_MODULES,
                        help="Comma-separated modules to install during init "
                             "(default covers common functional areas)")
    parser.add_argument("--db-container", required=True,
                        help="PostgreSQL Docker container name")
    parser.add_argument("--odoo-container", required=True,
                        help="Odoo Docker container name")
    parser.add_argument("--db-host", default=None,
                        help="DB host (auto-detected from Docker if omitted)")
    parser.add_argument("--db-port", default="5432", help="DB port (default: 5432)")
    parser.add_argument("--db-user", required=True, help="DB user / role name")
    parser.add_argument("--db-password", default=None,
                        help="DB password (prefer env vars or .env file)")
    parser.add_argument("--skip-init", action="store_true",
                        help="Skip Phase 0 (target DB already exists, freshly initialized)")
    parser.add_argument("--skip-filestore", action="store_true",
                        help="Skip filestore copy")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse dump and show plan, no DB changes")
    parser.add_argument("--skip-tables-extra", default=None,
                        help="Path to a text file with additional table names to skip (one per line)")
    parser.add_argument("--not-null-fixups", default=None,
                        help="Path to a JSON file with extra NOT_NULL_FIXUPS entries "
                             "(merged with built-in defaults)")
    parser.add_argument("--verify-counts", default=None,
                        help="Path to a JSON file mapping table_name → expected_min_count "
                             "for the verification phase")
    parser.add_argument("--neutralize-base-url", default="http://localhost:8069",
                        help="web.base.url to set during neutralization")
    parser.add_argument("--leftovers", default=None,
                        help="Where to write the Enterprise-only data that has no "
                             "Community home (default: <dump-dir>/enterprise-leftovers.json). "
                             "Feed this file to the bf_oe2oc module inside the migrated "
                             "instance to re-home the rows.")
    parser.add_argument("--no-leftovers", action="store_true",
                        help="Do not export Enterprise-only data")
    parser.add_argument("--max-leftover-rows", type=int, default=100000,
                        help="Per-table cap on exported rows (default: 100000)")
    return parser.parse_args()


def _load_extra_skip(path):
    if not path:
        return None
    if not os.path.exists(path):
        sys.exit(f"ERROR: --skip-tables-extra file not found: {path}")
    with open(path) as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def _load_not_null_fixups(path):
    fixups = {k: dict(v) for k, v in NOT_NULL_FIXUPS.items()}
    if not path:
        return fixups
    if not os.path.exists(path):
        sys.exit(f"ERROR: --not-null-fixups file not found: {path}")
    with open(path) as f:
        extra = json.load(f)
    for table, cols in extra.items():
        fixups.setdefault(table, {})
        for col, spec in cols.items():
            # spec must be [default_value, custom_sql_or_null]
            fixups[table][col] = (spec[0], spec[1])
    return fixups


def _load_verify_counts(path):
    if not path:
        return None
    if not os.path.exists(path):
        sys.exit(f"ERROR: --verify-counts file not found: {path}")
    with open(path) as f:
        return json.load(f)


def _load_manifest(dump_path):
    """Read the SaaS export's manifest.json, if it sits next to the dump."""
    path = os.path.join(os.path.dirname(os.path.abspath(dump_path)), "manifest.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _resolve_filestore_default(dump_path):
    """Find the filestore directory next to the dump.

    Enterprise SaaS dumps nest the filestore as
    `filestore/<source_db_name>/<hash-prefix>/<hash>`. Odoo expects
    `<filestore_root>/<target_db_name>/<hash-prefix>/<hash>` — so if we
    don't descend into the source-db subdirectory before copying, we
    end up with one extra level of nesting and Odoo can't find any
    attachments.

    Strategy:
      1. Read manifest.json (always present in SaaS exports) to learn
         the source DB name, then return `filestore/<src_db_name>`.
      2. Fall back to plain `filestore/` if there's no manifest, with
         a warning so the user can override.
    """
    dump_dir = os.path.dirname(os.path.abspath(dump_path))
    base = os.path.join(dump_dir, "filestore")

    manifest_path = os.path.join(dump_dir, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            src_db = manifest.get("db_name")
            if src_db:
                nested = os.path.join(base, src_db)
                if os.path.isdir(nested):
                    return nested
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: if `filestore/` contains exactly one subdirectory, descend into it
    if os.path.isdir(base):
        subdirs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
        if len(subdirs) == 1:
            print(f"  Note: defaulting filestore to {subdirs[0]}/ (single subdirectory)")
            return os.path.join(base, subdirs[0])

    return base


def main():
    args = parse_args()

    # Default filestore: descend into the source DB's subdirectory if possible
    if not args.filestore:
        args.filestore = _resolve_filestore_default(args.dump)

    extra_skip = _load_extra_skip(args.skip_tables_extra)
    not_null_fixups = _load_not_null_fixups(args.not_null_fixups)
    expected_counts = _load_verify_counts(args.verify_counts)

    # Auto-detect DB host from Docker if not provided
    if not args.db_host:
        print("  Auto-detecting DB host from Docker...")
        args.db_host = get_db_host(args.db_container)
        print(f"  DB host: {args.db_host}")

    creds = load_db_creds(args)
    if not creds["password"]:
        sys.exit(
            "ERROR: No DB password found.  "
            "Set DB_PASSWORD/PGPASSWORD env var or use --db-password."
        )

    print("=" * 70)
    print("  Odoo 18 Enterprise → Community: Business Data Migration")
    print("=" * 70)
    print(f"  Dump:       {args.dump}")
    print(f"  Filestore:  {args.filestore}")
    print(f"  Target DB:  {args.target_db}")
    print(f"  DB host:    {creds['host']}:{creds['port']}")
    print()

    # ── Phase 0: Initialize fresh Community DB ──
    if not args.skip_init and not args.dry_run:
        print("Phase 0: Initializing fresh Community DB...")
        try:
            pg_conn = connect(creds, "postgres")
            pg_conn.autocommit = True
            with pg_conn.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{args.target_db}"')
            pg_conn.close()
            print(f"  Dropped existing '{args.target_db}'")
        except Exception as e:
            sys.exit(f"ERROR: Cannot drop target DB: {e}")

        print(f"  Installing modules (this takes 2-3 minutes)...")
        t0 = time.time()
        try:
            output = docker_exec(
                args.odoo_container,
                f"odoo -d {args.target_db} -i {args.modules} "
                f"--stop-after-init --no-http --without-demo=all 2>&1; echo EXIT_CODE=$?",
                check=False,
                timeout=900,
            )
            elapsed = time.time() - t0
            if "EXIT_CODE=0" in output:
                print(f"  DB initialized in {elapsed:.0f}s")
            else:
                lines = output.strip().split("\n")
                for line in lines[-15:]:
                    if "ERROR" in line or "CRITICAL" in line:
                        print(f"  {line}")
                sys.exit("ERROR: Module installation failed")
        except subprocess.TimeoutExpired:
            sys.exit("ERROR: Module installation timed out (>15 min)")

    # ── Phase 1: Parse dump ──
    print("\nPhase 1: Parsing Enterprise dump...")
    if not os.path.exists(args.dump):
        sys.exit(f"ERROR: Dump not found: {args.dump}")
    blocks = parse_dump(args.dump)

    # ── Phase 2: Connect to target DB ──
    print("\nPhase 2: Connecting to target DB...")
    conn = None
    target_tables = None
    try:
        conn = connect(creds, args.target_db)
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        target_tables = get_all_tables(conn)
        print(f"  Target DB has {len(target_tables)} tables")
    except Exception as e:
        if args.dry_run:
            print(f"  Target DB not reachable ({e.__class__.__name__}); dry-run will assume "
                  f"all non-skipped tables exist in target.")
        else:
            sys.exit(f"ERROR: Cannot connect to '{args.target_db}': {e}")

    # ── Phase 3: Plan import ──
    print("\nPhase 3: Planning import...")
    import_plan = []
    skipped = []
    no_match = []

    for table_name, block in sorted(blocks.items()):
        if should_skip(table_name, extra_skip=extra_skip):
            skipped.append(table_name)
            continue
        if target_tables is not None and table_name not in target_tables:
            no_match.append(table_name)
            continue
        row_count = block.data_end - block.data_start if block.data_end else 0
        if row_count == 0:
            continue
        import_plan.append((table_name, block, row_count))

    print(f"  Tables to import:    {len(import_plan)}")
    print(f"  Skipped (framework): {len(skipped)}")
    if target_tables is not None:
        print(f"  Enterprise-only:     {len(no_match)}")

    if args.dry_run:
        print("\n  DRY RUN — tables that would be imported:")
        for table, block, rows in import_plan:
            print(f"    {table:50s} {rows:>8,d} rows  {len(block.columns)} cols")
        if not args.no_leftovers:
            planned = {t for t, _b, _r in import_plan}
            leftover = collect(blocks, target_tables, planned, args.max_leftover_rows)
            print(f"\n  DRY RUN — Enterprise-only data that would be exported "
                  f"({len(leftover)} tables):")
            for table, _block, rows in leftover:
                print(f"    {table:50s} {rows:>8,d} rows")
        return

    # ── Phase 4: Import data ──
    print(f"\nPhase 4: Importing {len(import_plan)} tables...")

    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
    conn.autocommit = False

    with conn.cursor() as cur:
        cur.execute("SET session_replication_role = 'replica'")
    conn.commit()

    total_rows = 0
    errors = []
    imported_tables = []

    for i, (table_name, block, est_rows) in enumerate(import_plan):
        comm_cols = get_table_columns(conn, table_name)
        if not comm_cols:
            continue

        try:
            if table_name in not_null_fixups:
                count, status = import_table_relaxed(
                    conn, args.dump, block, comm_cols, not_null_fixups[table_name]
                )
            else:
                count, status = import_table(conn, args.dump, block, comm_cols)
            conn.commit()
            total_rows += count
            imported_tables.append(table_name)
            if count > 100:
                print(f"    [{i+1}/{len(import_plan)}] {table_name:45s} {count:>8,d}  {status}")
        except Exception as e:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SET session_replication_role = 'replica'")
            conn.commit()
            err_msg = str(e).split("\n")[0][:120]
            errors.append((table_name, err_msg))
            print(f"    [{i+1}/{len(import_plan)}] {table_name:45s} ERROR: {err_msg}")

    with conn.cursor() as cur:
        cur.execute("SET session_replication_role = 'origin'")
    conn.commit()

    print(f"\n  Imported {total_rows:,d} rows across {len(imported_tables)} tables")
    if errors:
        print(f"  Errors: {len(errors)} tables failed")

    # ── Phase 5: Fix sequences ──
    print("\nPhase 5: Fixing sequences...")
    conn.autocommit = False
    fix_sequences(conn)

    # ── Phase 6: Copy filestore ──
    if not args.skip_filestore:
        print("\nPhase 6: Copying filestore...")
        copy_filestore(args.filestore, args.target_db, args.odoo_container)
    else:
        print("\nPhase 6: Skipped (--skip-filestore)")

    # ── Phase 7: Neutralize ──
    print("\nPhase 7: Neutralizing...")
    extra_neutralize = [
        f"UPDATE ir_config_parameter SET value = '{args.neutralize_base_url}' "
        f"WHERE key = 'web.base.url'"
    ] if args.neutralize_base_url != "http://localhost:8069" else None
    neutralize(conn, extra_statements=extra_neutralize)

    # ── Phase 8: Verify ──
    print("\nPhase 8: Verification...")
    all_ok = verify(conn, expected_counts=expected_counts, imported_tables=imported_tables)

    # ── Phase 9: Export the Enterprise-only data ──
    leftover_tables = leftover_rows = 0
    leftover_path = None
    if args.no_leftovers:
        print("\nPhase 9: Skipped (--no-leftovers)")
    else:
        print("\nPhase 9: Exporting Enterprise-only data...")
        out_path = args.leftovers or os.path.join(
            os.path.dirname(os.path.abspath(args.dump)), "enterprise-leftovers.json")
        try:
            leftover_tables, leftover_rows, leftover_path = export_leftovers(
                args.dump, blocks, target_tables, imported_tables, out_path,
                manifest=_load_manifest(args.dump), target_db=args.target_db,
                max_rows=args.max_leftover_rows)
        except Exception as e:
            # The migration itself is done and committed by now; failing to
            # write a side file must not read as a failed migration.
            print(f"  WARNING: could not write {out_path}: {e}")

    # ── Summary ──
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Tables imported: {len(imported_tables)}")
    print(f"  Total rows:      {total_rows:,d}")
    print(f"  Errors:          {len(errors)}")
    if leftover_path:
        print(f"  Left behind:     {leftover_rows:,d} rows in {leftover_tables} "
              f"Enterprise-only tables")
    if expected_counts:
        print(f"  Data integrity:  {'ALL OK' if all_ok else 'ISSUES — check above'}")

    if errors:
        print("\n  Failed tables:")
        for t, e in errors:
            print(f"    {t}: {e}")

    print(f"\n  Next steps:")
    print(f"    1. Widen dbfilter in odoo.conf to include '{args.target_db}'")
    print(f"    2. Restart the Odoo container ({args.odoo_container})")
    print(f"    3. Login with the Enterprise admin credentials (password preserved)")
    print(f"    4. Activate any non-default languages: "
          f"UPDATE res_lang SET active = true WHERE code = '<lang>'")
    print(f"    5. Revert dbfilter when done testing")
    if leftover_path:
        print(f"    6. Install bf_oe2oc and feed it {os.path.basename(leftover_path)} "
              f"to re-home the Enterprise data")


if __name__ == "__main__":
    main()

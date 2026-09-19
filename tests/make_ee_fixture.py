#!/usr/bin/env python3
"""Generate an Enterprise-shaped `dump.sql` to exercise the import pipeline.

Why this exists
---------------
The column-intersection step -- the one that drops Enterprise-only columns so
Enterprise rows fit a Community table -- can only be exercised by a dump whose
COPY column lists are a *superset* of the Community schema. A Community dump
never triggers it: there is nothing to drop, and the pipeline reports success
without the interesting code path ever running.

What is grounded, and what is modelled
--------------------------------------
GROUNDED. The table names below -- shared, Enterprise-only and skippable alike
-- are transcribed from a measured inventory of a real Odoo 18 Enterprise SaaS
dump (saas~18.3.1.3, 939 tables, 293 installed modules of which 135
Enterprise-only), as is the pg_dump 16 preamble. The row counts are that same
inventory rounded to orders of magnitude, so the fixture keeps realistic
proportions without publishing anyone's activity profile.

MODELLED. The *column* names marked `x_ee_*` are synthetic. The others are
Enterprise field names, but this generator does not trust them: every proposed
extra column is checked against the live Community schema first, and any name
that already exists there is dropped from the list. What survives is, by
construction, a column the Community side does not have -- which is the only
property the intersection step actually depends on.

The row *values* are synthetic. They are type-correct against the live
Community schema (jsonb translations, timestamps, numerics, booleans, bytea),
and written in PostgreSQL text-COPY format with real escaping, so the parser
and the COPY path see what pg_dump would hand them.

Usage::

    python tests/make_ee_fixture.py --host <db-container-ip> --db ee2ce_target \\
        --user odoo --password odoo --out /tmp/ee-fixture
"""

import argparse
import json
import os
import random

import psycopg2


# ── Volumes: orders of magnitude, rounded ────────────────────────────────────
# The table names come from the measured inventory of a real Enterprise dump.
# The counts are that inventory rounded to the nearest round number: enough to
# keep the fixture's proportions realistic -- a table with thousands of rows
# behaves differently from one with a handful -- without publishing a company's
# activity profile. Nothing in the pipeline depends on their precision.
#
# Tables that exist on BOTH sides. These drive the column-intersection path.
SHARED = {
    "res_partner": 150, "hr_employee": 5, "crm_lead": 50,
    "project_project": 50, "project_task": 500,
    "account_move": 600, "account_move_line": 1500,
    "sale_order": 40, "sale_order_line": 100,
    "account_analytic_line": 600,
    "mail_message": 9000, "mail_followers": 1800,
    "discuss_channel": 10,
    "blog_post": 60, "blog_blog": 5, "blog_tag": 25,
    "website_visitor": 200,
    "mailing_contact": 150, "mailing_list": 5,
    "account_bank_statement": 35, "account_bank_statement_line": 400,
    "account_account": 400, "account_group": 175,
    "account_tax": 35, "account_journal": 15,
    "ir_attachment": 2000,
    # NOT NULL fixup path (Community has mandatory columns Enterprise omits)
    "product_template": 30, "account_reconcile_model": 10,
}

# Framework / module-seeded tables the dump carries and the importer must skip.
SKIPPABLE = {
    "ir_module_module": 700, "ir_model": 1100, "ir_model_data": 40000,
    "ir_ui_view": 4000, "ir_config_parameter": 50, "ir_cron": 60,
    "res_groups": 120, "res_country": 250, "res_currency": 175,
    "mail_template": 70, "website_page": 10, "website_menu": 15,
    "spreadsheet_dashboard": 20, "uom_uom": 25,
    "saas_trial_category": 5, "saas_trial_template": 10,
}

# Grounded: Enterprise-only tables, absent from Community entirely.
ENTERPRISE_ONLY = {
    "helpdesk_ticket": 25, "helpdesk_stage": 5, "helpdesk_team": 5,
    "documents_document": 60, "documents_tag": 30,
    "sign_template": 10, "sign_request": 10, "sign_request_item": 15,
    "knowledge_article": 40,
    "social_account": 5, "social_stream_post": 50,
    "sale_subscription_plan": 5, "sale_order_log": 5,
    "spreadsheet_revision": 10,
    "account_return": 40, "account_report_line": 200,
    "account_report_column": 100, "account_report_expression": 300,
}

# Proposed Enterprise-only columns, by the module that adds them. Any name that
# turns out to exist in Community is discarded at generation time.
EE_COLUMNS = {
    "project_task": [
        ("planned_date_begin", "timestamp"), ("planned_date_end", "timestamp"),
        ("is_timer_running", "boolean"), ("timer_start", "timestamp"),
        ("timer_pause", "timestamp"), ("x_ee_gantt_progress", "numeric"),
    ],
    "account_analytic_line": [
        ("helpdesk_ticket_id", "integer"), ("timer_start", "timestamp"),
        ("timer_pause", "timestamp"), ("is_timer_running", "boolean"),
        ("x_ee_grid_validated", "boolean"),
    ],
    "account_move": [
        ("extract_state", "character varying"), ("extract_document_uuid", "character varying"),
        ("extract_attachment_id", "integer"), ("extract_state_processed", "boolean"),
        ("asset_id", "integer"), ("asset_depreciated_value", "numeric"),
        ("x_ee_avatax_unique_code", "character varying"),
    ],
    "account_move_line": [
        ("asset_id", "integer"), ("x_ee_disallowed_expenses_rate", "numeric"),
    ],
    "account_bank_statement_line": [
        ("extract_state", "character varying"), ("extract_document_uuid", "character varying"),
        ("x_ee_online_transaction_identifier", "character varying"),
    ],
    "sale_order": [
        ("subscription_state", "character varying"), ("plan_id", "integer"),
        ("next_invoice_date", "date"), ("end_date", "date"),
        ("x_ee_subscription_child_ids", "integer"),
    ],
    "sale_order_line": [
        ("x_ee_subscription_start_date", "date"), ("x_ee_qty_invoiced_posted", "numeric"),
    ],
    "res_partner": [
        ("x_ee_documents_share_id", "integer"), ("x_ee_sign_request_count", "integer"),
    ],
    "hr_employee": [
        ("hourly_cost", "numeric"), ("x_ee_appraisal_count", "integer"),
    ],
    "crm_lead": [
        ("x_ee_lead_enrich_done", "boolean"), ("x_ee_helpdesk_ticket_count", "integer"),
    ],
    "project_project": [
        ("x_ee_allow_billable_grid", "boolean"), ("x_ee_documents_folder_id", "integer"),
    ],
    "mail_message": [
        ("x_ee_snailmail_error", "boolean"),
    ],
    "account_account": [
        ("x_ee_asset_model_id", "integer"),
    ],
    "product_template": [
        ("x_ee_subscription_plan_id", "integer"),
    ],
}

# Values chosen so the generated rows satisfy the Community CHECK constraints.
# Without these the run drowns in fixture noise and the real findings get lost.
# Each entry names the constraint it exists to satisfy.
COLUMN_OVERRIDES = {
    # account_group_check_length_prefix: both prefixes must be the same length
    "account_group": {"code_prefix_start": "1000", "code_prefix_end": "9999"},
    # account_move_line_check_credit_debit: credit * debit = 0.
    # display_type is NOT NULL here, so it needs a value outside the
    # line_section / line_note pair that the constraint exempts.
    # account_move_line_check_amount_currency_balance_sign: balance and
    # amount_currency must not disagree on sign
    "account_move_line": {"credit": "0.00", "display_type": "product",
                          "account_id": "1", "debit": "125.00",
                          "balance": "125.00", "amount_currency": "125.00"},
    # crm_lead_check_probability: 0 <= probability <= 100
    "crm_lead": {"probability": "42.0", "automated_probability": "42.0"},
    # discuss_channel_group_public_id_check: group_public_id only on 'channel'
    # discuss_channel_sub_channel_no_group_public_id: not both with a parent
    "discuss_channel": {"channel_type": "channel", "group_public_id": None,
                        "parent_channel_id": None},
    # project_project_project_date_greater: date >= date_start
    "project_project": {"date_start": "2025-01-01", "date": "2025-12-31"},
    # project_task_recurring_task_has_no_parent
    # project_task_private_task_has_no_parent: a task with no project has no parent
    "project_task": {"recurring_task": "f", "parent_id": None},
    # sale_order_line_non_accountable_null_fields (display_type NULL => the
    # accountable fields must be set) and sale_order_line_accountable_required_fields
    "sale_order_line": {"display_type": None, "product_id": "7",
                        "product_uom": "1", "is_downpayment": "f"},
}


PREAMBLE = """--
-- PostgreSQL database dump
--

-- Dumped from database version 16.11 (Ubuntu 16.11-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.11 (Ubuntu 16.11-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


SET default_tablespace = '';

SET default_table_access_method = heap;

"""


_UNSET = object()


def esc(value):
    """Escape one field for PostgreSQL COPY text format."""
    if value is None:
        return r"\N"
    s = str(value)
    return (s.replace("\\", "\\\\").replace("\t", "\\t")
             .replace("\n", "\\n").replace("\r", "\\r"))


def gen_value(col, dtype, row_id, nullable, maxlen=None, override=_UNSET):
    """One type-correct synthetic value for a column."""
    if col == "id":
        return row_id
    if override is not _UNSET:
        return row_id if override == "ROWID" else override
    # A tenth of nullable columns come through empty, as a real dump would.
    if nullable and random.random() < 0.10:
        return None

    d = dtype.lower()
    if d in ("integer", "bigint", "smallint"):
        if col.endswith("_id"):
            return random.randint(1, 40)
        if col in ("sequence", "priority", "color"):
            return random.randint(0, 10)
        return random.randint(1, 5000)
    if d in ("numeric", "double precision", "real"):
        return f"{random.uniform(-5000, 25000):.2f}"
    if d == "boolean":
        return random.choice(["t", "f"])
    if d.startswith("timestamp"):
        return (f"2025-{random.randint(1,12):02d}-{random.randint(1,28):02d} "
                f"{random.randint(0,23):02d}:{random.randint(0,59):02d}:00")
    if d == "date":
        return f"2025-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
    if d == "jsonb":
        # Odoo 18 keeps translatable fields as jsonb. Quotes and backslashes in
        # here are exactly what shakes out escaping bugs.
        return json.dumps({"en_US": f"{col} {row_id}",
                           "fr_CA": f"{col} \u00ab {row_id} \u00bb"})
    if d == "bytea":
        return "\\\\x" + "".join(random.choice("0123456789abcdef") for _ in range(16))
    if d in ("text", "character varying", "character"):
        if col == "body":
            return f"<p>Message {row_id}<br>Deuxi\u00e8me ligne &amp; suite</p>"
        if col in ("state", "type", "move_type"):
            return "draft"
        if col == "email":
            return f"contact{row_id}@example.org"
        return f"{col}-{row_id}"
    return f"v{row_id}"


def unique_index_columns(conn, table):
    """One column per UNIQUE index on the Community side, to force distinct.

    Random values collide in a table of a few hundred rows, and a collision
    reads exactly like a tool bug in the run output. Composite indexes matter
    as much as single-column ones: `account_journal` is UNIQUE (code,
    company_id), and leaving both columns random means the fixture passes or
    fails on luck. Making one column of each index row-unique makes the whole
    tuple unique.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT i.indexrelid, a.attname, a.attnum "
            "FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid "
            "                   AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = %s::regclass AND i.indisunique", (table,))
        rows = cur.fetchall()
    per_index = {}
    for idx, col, attnum in rows:
        per_index.setdefault(idx, []).append((attnum, col))
    picked = set()
    for cols in per_index.values():
        names = [c for _n, c in sorted(cols)]
        if names == ["id"]:
            continue
        # Prefer a column that is not "id" and not an FK, so the value stays
        # plausible; fall back to the first one.
        choice = next((c for c in names if c != "id" and not c.endswith("_id")),
                      next((c for c in names if c != "id"), names[0]))
        picked.add(choice)
    return picked


def community_schema(conn, table):
    """(columns, types, nullability) for a Community table, in ordinal order."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type, is_nullable, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s "
            "ORDER BY ordinal_position", (table,))
        rows = cur.fetchall()
    return ([r[0] for r in rows],
            {r[0]: r[1] for r in rows},
            {r[0]: r[2] == "YES" for r in rows},
            {r[0]: r[3] for r in rows if r[3]})


def interleave(base_cols, extras):
    """Place Enterprise-only columns *among* the Community ones, not after them.

    Appending them at the end would let a buggy index map still line up by
    accident; scattering them is what makes the position mapping load-bearing.
    """
    cols = list(base_cols)
    for i, (name, _t) in enumerate(extras):
        pos = min(len(cols), 2 + (i * 7) % max(1, len(cols) - 2))
        cols.insert(pos, name)
    return cols


def copy_block(out, table, columns, types, nullables, nrows,
               maxlens=None, overrides=None):
    maxlens = maxlens or {}
    quoted = ", ".join(f'"{c}"' if c in ("order", "user", "default") else c for c in columns)
    out.write(f"--\n-- Data for Name: {table}; Type: TABLE DATA; Schema: public; Owner: -\n--\n\n")
    out.write(f"COPY public.{table} ({quoted}) FROM stdin;\n")
    for rid in range(1, nrows + 1):
        fields = []
        for c in columns:
            ov = overrides.get(c, _UNSET) if overrides else _UNSET
            v = gen_value(c, types.get(c, "text"), rid, nullables.get(c, True),
                          maxlen=maxlens.get(c), override=ov)
            ml = maxlens.get(c)
            if isinstance(v, str) and ml and len(v) > ml:
                # Cutting from the right throws away the row id -- the only
                # part that varies -- and every row lands on the same value.
                tail = str(rid)
                v = (v[:max(0, ml - len(tail))] + tail)[:ml]
            fields.append(esc(v))
        out.write("\t".join(fields) + "\n")
    out.write("\\.\n\n\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", default="5432")
    ap.add_argument("--db", required=True, help="Live Community DB to read the schema from")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--seed", type=int, default=22156,
                    help="RNG seed. Vary it to check the run does not pass on "
                         "luck -- a constraint this generator does not model "
                         "shows up as a failure on some seeds and not others.")
    ap.add_argument("--source-db", default="enterprise-source",
                    help="Source DB name written into manifest.json")
    args = ap.parse_args()
    random.seed(args.seed)

    os.makedirs(args.out, exist_ok=True)
    conn = psycopg2.connect(host=args.host, port=args.port, dbname=args.db,
                            user=args.user, password=args.password)

    dump_path = os.path.join(args.out, "dump.sql")
    stats = {"shared": 0, "ee_cols_added": 0, "rejected_ee_cols": [], "rows": 0}

    with open(dump_path, "w", encoding="utf-8") as out:
        out.write(PREAMBLE)

        # Enterprise-only tables: DDL plus data, so the planner has to notice
        # the Community target simply has no such table.
        for table, nrows in sorted(ENTERPRISE_ONLY.items()):
            cols = ["id", "create_uid", "create_date", "write_uid", "write_date",
                    "name", "active", "sequence", "company_id"]
            types = {"id": "integer", "create_uid": "integer", "write_uid": "integer",
                     "create_date": "timestamp", "write_date": "timestamp",
                     "name": "jsonb", "active": "boolean", "sequence": "integer",
                     "company_id": "integer"}
            nullables = {c: c != "id" for c in cols}
            out.write(f"--\n-- Name: {table}; Type: TABLE; Schema: public; Owner: -\n--\n\n")
            out.write(f"CREATE TABLE public.{table} (\n    id integer NOT NULL,\n"
                      "    name jsonb\n);\n\n\n")
            copy_block(out, table, cols, types, nullables, nrows)
            stats["rows"] += nrows

        # Framework tables the importer is expected to skip.
        for table, nrows in sorted(SKIPPABLE.items()):
            maxlens = {}
            try:
                cols, types, nullables, maxlens = community_schema(conn, table)
            except Exception:
                cols = []
            if not cols:
                cols = ["id", "name"]
                types = {"id": "integer", "name": "text"}
                nullables = {"id": False, "name": True}
            copy_block(out, table, cols, types, nullables, min(nrows, 60),
                       maxlens=maxlens)

        # Shared tables: the column-intersection path.
        for table, nrows in sorted(SHARED.items()):
            cols, types, nullables, maxlens = community_schema(conn, table)
            if not cols:
                print(f"  !! {table} absent from Community target, skipped")
                continue
            proposed = EE_COLUMNS.get(table, [])
            extras = []
            for name, dtype in proposed:
                if name in types:
                    stats["rejected_ee_cols"].append(f"{table}.{name}")
                    continue
                extras.append((name, dtype))
                types[name] = dtype
                nullables[name] = True
            ee_cols = interleave(cols, extras)
            ov = dict(COLUMN_OVERRIDES.get(table) or {})
            for uc in unique_index_columns(conn, table):
                if uc == "id" or uc in ov:
                    continue
                # NULLs never collide; a NOT NULL unique column gets the row id.
                ov[uc] = None if nullables.get(uc, True) else "ROWID"
            copy_block(out, table, ee_cols, types, nullables, nrows,
                       maxlens=maxlens, overrides=ov)
            stats["shared"] += 1
            stats["ee_cols_added"] += len(extras)
            stats["rows"] += nrows

        out.write("--\n-- PostgreSQL database dump complete\n--\n\n")

    # manifest.json + a filestore nested the way a SaaS export nests it
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump({"odoo_dump": "1", "db_name": args.source_db,
                   "version": "saas~18.3", "version_info": [18, 3, 0, "final", 0, ""],
                   "major_version": "saas~18.3", "pg_version": "16.11"}, f, indent=2)

    fs_root = os.path.join(args.out, "filestore", args.source_db)
    for i in range(12):
        h = f"{i:02x}" + "".join(random.choice("0123456789abcdef") for _ in range(38))
        d = os.path.join(fs_root, h[:2])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, h), "wb") as f:
            f.write(os.urandom(256))

    size = os.path.getsize(dump_path)
    print(f"  dump.sql            {size/1e6:.1f} MB")
    print(f"  shared tables       {stats['shared']}")
    print(f"  EE-only columns     {stats['ee_cols_added']} added across shared tables")
    print(f"  EE-only tables      {len(ENTERPRISE_ONLY)}")
    print(f"  skippable tables    {len(SKIPPABLE)}")
    print(f"  total rows          {stats['rows']:,d}")
    if stats["rejected_ee_cols"]:
        print(f"  rejected (exist in Community): {', '.join(stats['rejected_ee_cols'])}")


if __name__ == "__main__":
    main()

"""Export the Enterprise data the import had nowhere to put.

The pipeline drops Enterprise-only tables on the floor: the freshly
initialized Community target has no `helpdesk_ticket`, no `knowledge_article`,
no `sign_template`, so those rows are skipped and that is the end of them. The
summary counts them, but the data is gone the moment the dump is deleted.

This module writes them out instead, as one small JSON file. Small is the
point: the tables are narrow and short next to the business data -- a couple of
dozen tickets, a few dozen articles, a handful of templates -- so the file is
something a person can attach to a form, which is how `bf_oe2oc` picks it up
inside the migrated instance and re-homes the rows onto Community or OCA
models.

The file is a faithful dump of what was in those tables, not an interpretation
of it. Deciding that a helpdesk ticket becomes an `helpdesk.ticket` is the
module's job, on the other side, where the target models actually exist.
"""

import json
import os
from datetime import datetime, timezone

from odoo18_ee2ce.config import is_enterprise_data
from odoo18_ee2ce.parser import extract_copy_data

FORMAT = "odoo18-ee2ce/leftovers"
FORMAT_VERSION = 1


def unescape_field(field):
    """Turn one PostgreSQL text-COPY field into a Python value.

    `\\N` is NULL. The rest is the standard backslash escaping, and the order
    matters: unescaping the backslash first would turn a literal `\\` followed
    by `n` into a newline.
    """
    if field == r"\N":
        return None
    out = []
    i = 0
    while i < len(field):
        c = field[i]
        if c == "\\" and i + 1 < len(field):
            nxt = field[i + 1]
            mapped = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\",
                      "b": "\b", "f": "\f", "v": "\v"}.get(nxt)
            if mapped is not None:
                out.append(mapped)
                i += 2
                continue
        out.append(c)
        i += 1
    return "".join(out)


def collect(blocks, target_tables, imported_tables, max_rows=100000):
    """Pick the tables worth exporting.

    Returns a list of (table_name, block, row_count), longest first, so the
    report reads top-down by how much is at stake.
    """
    imported = set(imported_tables or ())
    chosen = []
    for name, block in blocks.items():
        if name in imported:
            continue
        in_target = target_tables is None or name in target_tables
        if not is_enterprise_data(name, in_target):
            continue
        rows = (block.data_end - block.data_start) if block.data_end else 0
        if rows <= 0:
            continue
        chosen.append((name, block, rows))
    chosen.sort(key=lambda t: (-t[2], t[0]))
    return chosen


def export_leftovers(dump_path, blocks, target_tables, imported_tables,
                     out_path, manifest=None, target_db=None, max_rows=100000):
    """Write the Enterprise-only rows to `out_path` as JSON.

    Returns (table_count, row_count, out_path) or (0, 0, None) when there is
    nothing to write -- in which case no file is created, so an empty file
    never gets mistaken for a successful export of an empty set.
    """
    chosen = collect(blocks, target_tables, imported_tables, max_rows)
    if not chosen:
        print("  Nothing to export: no Enterprise-only data in this dump")
        return 0, 0, None

    payload = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "dump": os.path.basename(dump_path),
            "db_name": (manifest or {}).get("db_name"),
            "version": (manifest or {}).get("version"),
        },
        "target_db": target_db,
        "tables": {},
    }

    total_rows = 0
    for name, block, row_count in chosen:
        lines = extract_copy_data(dump_path, block)
        truncated = False
        if len(lines) > max_rows:
            lines = lines[:max_rows]
            truncated = True
        rows = [[unescape_field(f) for f in line.rstrip("\n").split("\t")]
                for line in lines]
        payload["tables"][name] = {
            "columns": list(block.columns),
            "row_count": len(rows),
            "truncated": truncated,
            "rows": rows,
        }
        total_rows += len(rows)
        flag = "  TRUNCATED" if truncated else ""
        print(f"    {name:45s} {len(rows):>8,d}{flag}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    size = os.path.getsize(out_path)
    print(f"  Wrote {len(chosen)} tables, {total_rows:,d} rows "
          f"({size/1e6:.1f} MB) to {out_path}")
    return len(chosen), total_rows, out_path

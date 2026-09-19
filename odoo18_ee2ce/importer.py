"""Per-table import logic with column filtering and constraint relaxation."""

import io

from odoo18_ee2ce.parser import extract_copy_data
from odoo18_ee2ce.schema import get_check_constraints, get_not_null_columns


def filter_data_row(row_line, keep_indices):
    """Filter a tab-delimited row to keep only specified column indices."""
    fields = row_line.rstrip("\n").split("\t")
    filtered = [fields[i] if i < len(fields) else "\\N" for i in keep_indices]
    return "\t".join(filtered) + "\n"


def import_table(conn, dump_path, block, community_columns):
    """Import one table's data with column filtering.

    Drops Enterprise-only columns from each row before COPY. Empties the
    table first so module-seeded rows don't conflict with imported rows.
    """
    ent_cols = block.columns
    comm_set = set(community_columns)

    shared = [c for c in ent_cols if c in comm_set]
    if not shared:
        return 0, "no shared columns"

    dropped = [c for c in ent_cols if c not in comm_set]
    keep_indices = [ent_cols.index(c) for c in shared]

    quoted = ", ".join(f'"{c}"' for c in shared)
    copy_sql = f'COPY "{block.table}" ({quoted}) FROM STDIN'

    data_lines = extract_copy_data(dump_path, block)
    if not data_lines:
        return 0, "empty"

    if len(shared) < len(ent_cols):
        buf = io.StringIO()
        for line in data_lines:
            buf.write(filter_data_row(line, keep_indices))
        buf.seek(0)
        data_source = buf
    else:
        data_source = io.StringIO("".join(data_lines))

    with conn.cursor() as cur:
        cur.execute(f'DELETE FROM "{block.table}"')
        deleted = cur.rowcount

    with conn.cursor() as cur:
        cur.copy_expert(copy_sql, data_source)
        imported = cur.rowcount

    drop_info = ""
    if dropped:
        preview = ", ".join(dropped[:5])
        drop_info = f" (dropped {len(dropped)} cols: {preview}{'...' if len(dropped) > 5 else ''})"
    del_info = f" [deleted {deleted} seed rows]" if deleted > 0 else ""
    return imported, f"OK{drop_info}{del_info}"


def import_table_relaxed(conn, dump_path, block, community_columns, defaults):
    """Import a table after temporarily dropping NOT NULL and CHECK constraints.

    Used for tables where Community has mandatory columns that the Enterprise
    rows don't populate. After import, fills NULLs with defaults from
    `defaults` and re-enables NOT NULL where possible.
    """
    nn_cols = get_not_null_columns(conn, block.table)
    check_cons = get_check_constraints(conn, block.table)

    with conn.cursor() as cur:
        cur.execute(f'DELETE FROM "{block.table}"')
        for col in nn_cols:
            try:
                cur.execute(f'ALTER TABLE "{block.table}" ALTER COLUMN "{col}" DROP NOT NULL')
            except Exception:
                conn.rollback()
                cur.execute("SET session_replication_role = 'replica'")
        for cn in check_cons:
            try:
                cur.execute(f'ALTER TABLE "{block.table}" DROP CONSTRAINT "{cn}"')
            except Exception:
                conn.rollback()
                cur.execute("SET session_replication_role = 'replica'")
    conn.commit()

    count, status = import_table(conn, dump_path, block, community_columns)
    conn.commit()

    # Apply defaults for NULL values.
    #
    # A fixup entry may name a column this particular Community install does
    # not have: NOT_NULL_FIXUPS is a static map, but the target schema depends
    # on which modules were installed. Skip those, and never let one bad fixup
    # abort the rest -- the NOT NULL constraints were dropped above, and the
    # restore loop below is the only thing that puts them back.
    comm_set = set(community_columns)
    skipped_fixups = []
    failed_fixups = []
    for col, (default_val, custom_sql) in defaults.items():
        if col not in comm_set:
            skipped_fixups.append(col)
            continue
        try:
            with conn.cursor() as cur:
                if custom_sql:
                    cur.execute(f'UPDATE "{block.table}" {custom_sql}')
                else:
                    cur.execute(
                        f'UPDATE "{block.table}" SET "{col}" = {default_val} '
                        f'WHERE "{col}" IS NULL'
                    )
            conn.commit()
        except Exception as e:
            conn.rollback()
            failed_fixups.append(f"{col}: {str(e).splitlines()[0][:60]}")

    # Re-add NOT NULL where all values are non-null
    restored = 0
    for col in nn_cols:
        try:
            with conn.cursor() as cur:
                cur.execute(f'SELECT COUNT(*) FROM "{block.table}" WHERE "{col}" IS NULL')
                if cur.fetchone()[0] == 0:
                    cur.execute(f'ALTER TABLE "{block.table}" ALTER COLUMN "{col}" SET NOT NULL')
                    restored += 1
            conn.commit()
        except Exception:
            conn.rollback()
    conn.commit()

    notes = []
    if skipped_fixups:
        notes.append(f"fixups n/a: {', '.join(skipped_fixups)}")
    if failed_fixups:
        notes.append(f"fixups failed: {'; '.join(failed_fixups)}")
    if len(nn_cols) and restored < len(nn_cols):
        notes.append(f"NOT NULL restored {restored}/{len(nn_cols)}")
    if notes:
        status = f"{status} [{' | '.join(notes)}]"

    return count, status

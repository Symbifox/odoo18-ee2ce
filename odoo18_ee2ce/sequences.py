"""Sequence reset after data import."""


def fix_sequences(conn):
    """Reset every sequence in the public schema to max(linked column)."""
    print("\n  Fixing sequences...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.relname, t.relname, a.attname
            FROM pg_class s
            JOIN pg_depend d ON d.objid = s.oid AND d.deptype = 'a'
            JOIN pg_class t ON t.oid = d.refobjid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
            WHERE s.relkind = 'S'
        """)
        sequences = cur.fetchall()

    fixed = 0
    for seq_name, table_name, col_name in sequences:
        try:
            with conn.cursor() as cur:
                cur.execute(f'SELECT MAX("{col_name}") FROM "{table_name}"')
                max_val = cur.fetchone()[0]
                if max_val is not None:
                    cur.execute(f"SELECT setval('{seq_name}', {max_val})")
                    fixed += 1
        except Exception:
            conn.rollback()
    conn.commit()
    print(f"  Fixed {fixed}/{len(sequences)} sequences")

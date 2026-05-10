"""PostgreSQL schema introspection helpers."""


def get_table_columns(conn, table_name):
    """Ordered column names for a table."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s "
            "ORDER BY ordinal_position",
            (table_name,),
        )
        return [r[0] for r in cur.fetchall()]


def get_all_tables(conn):
    """Set of all table names in the public schema."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        return {r[0] for r in cur.fetchall()}


def get_not_null_columns(conn, table_name):
    """NOT NULL column names for a table (excluding 'id')."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s "
            "AND is_nullable = 'NO' AND column_name != 'id'",
            (table_name,),
        )
        return [r[0] for r in cur.fetchall()]


def get_check_constraints(conn, table_name):
    """CHECK constraint names for a table."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND contype = 'c'",
            (table_name,),
        )
        return [r[0] for r in cur.fetchall()]

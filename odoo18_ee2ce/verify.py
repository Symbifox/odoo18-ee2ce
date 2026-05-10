"""Post-import row-count verification."""


def verify(conn, expected_counts=None, imported_tables=None):
    """Print row counts for verification.

    If `expected_counts` is given, compares actual counts and flags
    tables that fall short. Otherwise, prints actual counts for every
    table that was imported (or a sensible default subset).

    Returns True if all expected counts are met (or no expectations set).
    """
    print("\n  --- Verification ---")
    all_ok = True

    if expected_counts:
        for table, expected in sorted(expected_counts.items()):
            try:
                with conn.cursor() as cur:
                    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                    actual = cur.fetchone()[0]
                status = "OK" if actual >= expected else f"LOW (expected {expected})"
                if actual < expected:
                    all_ok = False
                print(f"    {table:40s} {actual:>8,d}  {status}")
            except Exception:
                print(f"    {table:40s}  MISSING")
                all_ok = False
        return all_ok

    # No expectations: print actual counts for the imported tables
    tables_to_show = imported_tables or _DEFAULT_VERIFY_TABLES
    for table in sorted(tables_to_show):
        try:
            with conn.cursor() as cur:
                cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                actual = cur.fetchone()[0]
            print(f"    {table:40s} {actual:>8,d}")
        except Exception:
            # Table doesn't exist in target — skip silently
            pass
    return True


# Common business tables — used when no `imported_tables` list is provided
_DEFAULT_VERIFY_TABLES = (
    "res_partner",
    "res_users",
    "account_move",
    "account_move_line",
    "account_journal",
    "account_account",
    "crm_lead",
    "project_project",
    "project_task",
    "sale_order",
    "sale_order_line",
    "account_analytic_line",
    "mail_message",
    "ir_attachment",
)

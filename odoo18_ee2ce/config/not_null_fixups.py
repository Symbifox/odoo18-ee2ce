"""NOT NULL relaxation map for tables with Community-only mandatory columns.

When the Community schema has a NOT NULL column that the Enterprise dump
doesn't populate, importing fails. This dict tells the importer to:

  1. Drop the NOT NULL constraint before COPY
  2. Run the import
  3. Apply a default value (or custom UPDATE) to fill NULLs
  4. Restore the NOT NULL constraint if all rows are now valid

Format::

    {
        "table_name": {
            "column_name": ("default_value_sql", "custom_update_sql_or_None"),
        },
    }

If `custom_update_sql_or_None` is None, the default UPDATE is::

    UPDATE "table" SET "column" = <default_value> WHERE "column" IS NULL
"""

NOT_NULL_FIXUPS = {
    "product_template": {
        "uom_po_id": ("1", "SET uom_po_id = uom_id WHERE uom_po_id IS NULL"),
        "ticket_active": ("false", None),
        "categ_id": ("1", None),
        "sale_line_warn": ("'no'", None),
    },
    "account_reconcile_model": {
        "rule_type": ("'writeoff_button'", None),
        "matching_order": ("'1'", None),
        "match_nature": ("'amount_received'", None),
        "payment_tolerance_type": ("'percentage'", None),
    },
}

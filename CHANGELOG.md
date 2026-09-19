# Changelog

## 0.3.0 — 2026-09-18

**Changed**

- Relicensed from MIT to **LGPL-3.0-or-later**. This is not an Odoo module and
  imports nothing from Odoo, so no licence was inherited and none was owed;
  copyleft is a deliberate choice. What makes this tool worth anything is its
  skip lists and its NOT NULL fixups, which grow one migration at a time — the
  lesser variant asks for those back while still letting you import
  `odoo18_ee2ce` as a library inside your own tooling.
- The fixture's row counts are now the measured inventory rounded to orders of
  magnitude rather than its exact figures. Nothing in the pipeline depends on
  their precision, and exact counts published a company's activity profile.

**Fixed**

- `tests/make_ee_fixture.py` only forced distinct values on single-column
  UNIQUE indexes, so composite ones — `account_journal` is UNIQUE (code,
  company_id) — were left to chance and the suite passed or failed on the draw.
  One column of every unique index is now row-unique.
- Values were truncated to the column width from the right, which threw away
  the row id: every `account_journal.code` became `code-` in a `varchar(5)`.
  Truncation now keeps the id.
- New `--seed`, so the run can be repeated on different draws. The result above
  holds on four of them.

## 0.2.0 — 2026-09-18

**Fixed**

- A `NOT_NULL_FIXUPS` entry naming a column the target does not have no longer
  sinks the table. `NOT_NULL_FIXUPS` is a static map while the target schema
  depends on the `--modules` list, so a mismatch is routine —
  `product_template.ticket_active` only exists once the event modules are
  installed. Previously that raised mid-way through the fixups, which left the
  table's `NOT NULL` constraints dropped and never restored, skipped every
  remaining fixup, and reported a table whose rows had in fact already been
  committed as a failure. Absent columns are now skipped and named in the status
  line, a fixup that fails for any other reason is reported rather than raised,
  and the `NOT NULL` restore always runs.

**Added**

- `tests/make_ee_fixture.py` — generates an Enterprise-shaped `dump.sql` from a
  live Community schema, so the column-intersection path can be exercised
  without an Enterprise database. See "Validation status" in the README.
- `tests/test_relaxed_import.py` — three regression tests covering the above.

## 0.1.0

Initial release.

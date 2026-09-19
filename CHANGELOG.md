# Changelog

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

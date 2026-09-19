"""Tests for the NOT NULL relaxation path.

NOT_NULL_FIXUPS is a static map, but the target schema is whatever the
`--modules` list produced. A fixup can therefore name a column this install
does not have -- `product_template.ticket_active` only exists once the event
modules are in. That case used to raise mid-way through the fixups, which
left the table's NOT NULL constraints dropped and reported a table whose rows
had already been committed as a failure.
"""

import pytest

from odoo18_ee2ce import importer


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._result = (0,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.statements.append(sql)
        for missing in self.conn.missing_columns:
            # Postgres rejects the whole statement when a column is unknown.
            if f'"{missing}"' in sql and "ALTER TABLE" not in sql:
                raise RuntimeError(f'column "{missing}" does not exist')
        self.rowcount = 0

    def fetchone(self):
        return self._result

    def copy_expert(self, sql, source):
        self.conn.statements.append(sql)
        self.rowcount = len(source.getvalue().splitlines())


class FakeConn:
    def __init__(self, missing_columns=()):
        self.statements = []
        self.missing_columns = set(missing_columns)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def block(tmp_path):
    dump = tmp_path / "dump.sql"
    dump.write_text(
        "COPY public.product_template (id, name, uom_po_id, categ_id) FROM stdin;\n"
        "1\tWidget\t\\N\t\\N\n"
        "2\tGadget\t\\N\t\\N\n"
        "\\.\n"
    )
    blocks = importer.extract_copy_data  # noqa: F841  (imported for symmetry)
    from odoo18_ee2ce.parser import parse_dump
    return str(dump), parse_dump(str(dump))["product_template"]


def _patch_schema(monkeypatch, not_null=("categ_id",), checks=()):
    monkeypatch.setattr(importer, "get_not_null_columns", lambda c, t: list(not_null))
    monkeypatch.setattr(importer, "get_check_constraints", lambda c, t: list(checks))


def test_fixup_for_absent_column_is_skipped(block, monkeypatch):
    dump_path, blk = block
    _patch_schema(monkeypatch)
    conn = FakeConn()
    community_columns = ["id", "name", "uom_po_id", "categ_id"]
    fixups = {
        "uom_po_id": ("1", "SET uom_po_id = uom_id WHERE uom_po_id IS NULL"),
        "ticket_active": ("false", None),   # absent from this install
        "categ_id": ("1", None),
    }

    count, status = importer.import_table_relaxed(
        conn, dump_path, blk, community_columns, fixups)

    assert count == 2
    assert "fixups n/a: ticket_active" in status
    # The fixup after the absent one still ran.
    assert any("categ_id" in s and s.startswith("UPDATE") for s in conn.statements)
    # No statement was ever issued for the column that does not exist.
    assert not any("ticket_active" in s for s in conn.statements)


def test_not_null_is_restored_after_an_absent_fixup(block, monkeypatch):
    dump_path, blk = block
    _patch_schema(monkeypatch, not_null=("categ_id", "uom_po_id"))
    # The absent column must actually blow up when touched, the way Postgres
    # would -- otherwise this test passes against the unfixed code too.
    conn = FakeConn(missing_columns={"ticket_active"})

    importer.import_table_relaxed(
        conn, dump_path, blk, ["id", "name", "uom_po_id", "categ_id"],
        {"ticket_active": ("false", None)})

    dropped = [s for s in conn.statements if "DROP NOT NULL" in s]
    restored = [s for s in conn.statements if "SET NOT NULL" in s]
    assert len(dropped) == 2
    assert len(restored) == 2, "constraints dropped for the import must be put back"


def test_a_failing_fixup_does_not_sink_the_table(block, monkeypatch):
    """A fixup that errors for another reason is reported, not raised."""
    dump_path, blk = block
    _patch_schema(monkeypatch)
    conn = FakeConn(missing_columns={"categ_id"})

    count, status = importer.import_table_relaxed(
        conn, dump_path, blk, ["id", "name", "uom_po_id", "categ_id"],
        {"categ_id": ("1", None)})

    assert count == 2
    assert "fixups failed: categ_id" in status

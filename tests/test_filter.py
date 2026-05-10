"""Tests for column-intersection filtering."""

from odoo18_ee2ce.importer import filter_data_row


def test_filter_keeps_only_specified_indices():
    row = "1\tACME\tcontact@acme.com\tpremium\n"
    # Keep id (0), email (2). Drop name (1), enterprise_only_field (3).
    out = filter_data_row(row, [0, 2])
    assert out == "1\tcontact@acme.com\n"


def test_filter_handles_short_row_with_null():
    # Row has 3 fields, but we ask for index 5 — should fill with \N
    row = "1\tACME\tcontact@acme.com\n"
    out = filter_data_row(row, [0, 5])
    assert out == "1\t\\N\n"


def test_filter_preserves_order():
    row = "a\tb\tc\td\n"
    out = filter_data_row(row, [3, 0, 2])
    assert out == "d\ta\tc\n"


def test_filter_handles_null_fields():
    row = "1\tACME\t\\N\tpremium\n"
    out = filter_data_row(row, [0, 1, 2])
    assert out == "1\tACME\t\\N\n"

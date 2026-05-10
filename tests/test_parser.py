"""Tests for the dump parser."""

import os

import pytest

from odoo18_ee2ce.parser import parse_dump, extract_copy_data


FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "mini_dump.sql")


def test_parse_finds_both_blocks():
    blocks = parse_dump(FIXTURE)
    assert set(blocks.keys()) == {"res_partner", "account_move"}


def test_parse_records_columns():
    blocks = parse_dump(FIXTURE)
    assert blocks["res_partner"].columns == [
        "id", "name", "email", "enterprise_only_field"
    ]
    assert blocks["account_move"].columns == ["id", "name", "state"]


def test_parse_records_data_range():
    blocks = parse_dump(FIXTURE)
    rp = blocks["res_partner"]
    assert rp.data_end > rp.data_start
    assert rp.data_end - rp.data_start == 3  # 3 data rows


def test_extract_copy_data_returns_rows():
    blocks = parse_dump(FIXTURE)
    rows = extract_copy_data(FIXTURE, blocks["res_partner"])
    assert len(rows) == 3
    assert rows[0].startswith("1\tACME Corp\t")
    assert rows[2].rstrip("\n").endswith("\\N")  # NULL field


def test_extract_copy_data_account_move():
    blocks = parse_dump(FIXTURE)
    rows = extract_copy_data(FIXTURE, blocks["account_move"])
    assert len(rows) == 2
    assert rows[0].startswith("100\tINV/2026/0001\tposted")

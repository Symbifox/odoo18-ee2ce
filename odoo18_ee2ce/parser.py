"""Single-pass parser for Odoo Enterprise pg_dump SQL files.

Locates every COPY ... FROM stdin block and records its location and
column list, but does not load row data into memory. Data is streamed
later by `extract_copy_data` for each block actually selected for import.
"""

import re


class CopyBlock:
    """A COPY ... FROM stdin block found in the dump."""

    __slots__ = ("table", "columns", "data_start", "data_end")

    def __init__(self, table, columns, data_start, data_end=None):
        self.table = table
        self.columns = columns
        self.data_start = data_start
        self.data_end = data_end


_COPY_RE = re.compile(
    r'^COPY\s+(?:public\.)?\"?(\w+)\"?\s*\((.+?)\)\s+FROM\s+stdin',
    re.IGNORECASE,
)


def parse_dump(dump_path):
    """Single-pass parse of dump.sql to find all COPY blocks.

    Returns a dict mapping table name → CopyBlock.
    """
    print(f"  Parsing {dump_path} ...")
    blocks = {}
    current_block = None
    with open(dump_path, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f):
            if current_block is not None:
                if line.startswith("\\."):
                    current_block.data_end = line_num
                    blocks[current_block.table] = current_block
                    current_block = None
                continue
            m = _COPY_RE.match(line)
            if m:
                table = m.group(1)
                cols = [c.strip().strip('"') for c in m.group(2).split(",")]
                current_block = CopyBlock(table, cols, line_num + 1)

    print(f"  Found {len(blocks)} COPY blocks")
    return blocks


def extract_copy_data(dump_path, block):
    """Read the raw data lines for one COPY block."""
    lines = []
    with open(dump_path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i < block.data_start:
                continue
            if i >= block.data_end:
                break
            lines.append(line)
    return lines

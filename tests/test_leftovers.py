"""Tests for the Enterprise-only data export."""

import json

from odoo18_ee2ce.config import is_enterprise_data
from odoo18_ee2ce.leftovers import collect, export_leftovers, unescape_field
from odoo18_ee2ce.parser import parse_dump


class TestUnescape:
    def test_null(self):
        assert unescape_field(r"\N") is None

    def test_plain(self):
        assert unescape_field("hello") == "hello"

    def test_tab_and_newline(self):
        assert unescape_field(r"a\tb\nc") == "a\tb\nc"

    def test_backslash_is_not_reread(self):
        # A literal backslash followed by 'n' must stay two characters, not
        # become a newline. Unescaping left to right is what guarantees it.
        assert unescape_field(r"a\\nb") == "a\\nb"

    def test_lone_backslash_at_end(self):
        assert unescape_field("trailing\\") == "trailing\\"

    def test_json_text_survives(self):
        # Odoo 18 keeps translations as jsonb; pg_dump escapes nothing inside
        # but the field still has to come back parseable.
        raw = '{"en_US": "Ticket", "fr_CA": "Billet"}'
        assert json.loads(unescape_field(raw))["fr_CA"] == "Billet"


class TestClassification:
    def test_framework_is_not_data(self):
        assert is_enterprise_data("ir_model_data", in_target=False) is False
        assert is_enterprise_data("res_country", in_target=True) is False
        assert is_enterprise_data("saas_trial_template", in_target=False) is False
        assert is_enterprise_data("web_gantt_view", in_target=False) is False

    def test_enterprise_business_data_is_data(self):
        assert is_enterprise_data("documents_document", in_target=False) is True
        assert is_enterprise_data("sign_template", in_target=False) is True
        assert is_enterprise_data("knowledge_article", in_target=False) is True
        assert is_enterprise_data("sale_subscription_plan", in_target=False) is True

    def test_absent_from_community_is_data(self):
        # No prefix marks it, but Community has no such table, so the rows
        # have nowhere to go.
        assert is_enterprise_data("helpdesk_ticket", in_target=False) is True
        assert is_enterprise_data("account_return", in_target=False) is True

    def test_present_in_community_is_not_leftover(self):
        assert is_enterprise_data("res_partner", in_target=True) is False

    def test_ocr_scratch_is_not_data(self):
        # Extraction state is scratch from a service that is not coming along.
        assert is_enterprise_data("account_invoice_extract_words", in_target=False) is False


def _dump(tmp_path):
    p = tmp_path / "dump.sql"
    p.write_text(
        "COPY public.helpdesk_ticket (id, name, description) FROM stdin;\n"
        "1\tPrinter down\tThe printer is\\ndown\n"
        "2\tVPN\t\\N\n"
        "\\.\n"
        "\n"
        "COPY public.res_partner (id, name) FROM stdin;\n"
        "1\tACME\n"
        "\\.\n"
        "\n"
        "COPY public.ir_model_data (id, name) FROM stdin;\n"
        "1\tbase.main_company\n"
        "\\.\n"
    )
    return str(p)


class TestCollectAndExport:
    def test_collect_leaves_out_imported_and_framework(self, tmp_path):
        path = _dump(tmp_path)
        blocks = parse_dump(path)
        picked = collect(blocks, target_tables={"res_partner", "ir_model_data"},
                         imported_tables=["res_partner"])
        assert [name for name, _b, _r in picked] == ["helpdesk_ticket"]

    def test_export_writes_rows_and_nulls(self, tmp_path):
        path = _dump(tmp_path)
        blocks = parse_dump(path)
        out = tmp_path / "leftovers.json"
        tables, rows, written = export_leftovers(
            path, blocks, {"res_partner", "ir_model_data"}, ["res_partner"],
            str(out), manifest={"db_name": "src", "version": "saas~18.3"},
            target_db="target")

        assert (tables, rows) == (1, 2)
        assert written == str(out)
        payload = json.loads(out.read_text())
        assert payload["format_version"] == 1
        assert payload["source"]["db_name"] == "src"
        t = payload["tables"]["helpdesk_ticket"]
        assert t["columns"] == ["id", "name", "description"]
        assert t["rows"][0][2] == "The printer is\ndown"
        assert t["rows"][1][2] is None
        assert t["truncated"] is False

    def test_nothing_to_export_writes_no_file(self, tmp_path):
        path = _dump(tmp_path)
        blocks = parse_dump(path)
        out = tmp_path / "leftovers.json"
        tables, rows, written = export_leftovers(
            path, blocks, {"res_partner", "ir_model_data", "helpdesk_ticket"},
            ["res_partner", "helpdesk_ticket"], str(out))
        # An empty file would read as "exported, and there was nothing".
        assert (tables, rows, written) == (0, 0, None)
        assert not out.exists()

    def test_truncation_is_flagged(self, tmp_path):
        path = _dump(tmp_path)
        blocks = parse_dump(path)
        out = tmp_path / "leftovers.json"
        export_leftovers(path, blocks, {"res_partner", "ir_model_data"},
                         ["res_partner"], str(out), max_rows=1)
        t = json.loads(out.read_text())["tables"]["helpdesk_ticket"]
        assert t["truncated"] is True
        assert t["row_count"] == 1

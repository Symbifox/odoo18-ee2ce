"""Tests for the should_skip decision."""

from odoo18_ee2ce.config import should_skip


def test_skip_known_framework_table():
    assert should_skip("ir_model_data") is True
    assert should_skip("ir_ui_view") is True
    assert should_skip("res_groups") is True


def test_keep_business_table():
    assert should_skip("res_partner") is False
    assert should_skip("account_move") is False
    assert should_skip("project_task") is False


def test_skip_ir_prefix_except_attachment():
    assert should_skip("ir_logging") is True
    assert should_skip("ir_attachment") is False  # business data — needed for filestore


def test_skip_enterprise_prefix():
    assert should_skip("documents_document") is True
    assert should_skip("sign_request") is True
    assert should_skip("planning_slot") is True


def test_extra_skip_table_param():
    assert should_skip("my_custom_table", extra_skip={"my_custom_table"}) is True
    assert should_skip("my_custom_table") is False

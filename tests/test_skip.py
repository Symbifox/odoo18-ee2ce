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


def test_oca_name_collision_is_never_imported():
    """`helpdesk_mgmt` (OCA) owns a table named exactly like the Enterprise one.

    Importing into it would DELETE the OCA rows and then column-intersect two
    unrelated schemas, silently: `number` and `description` are required by the
    ORM, not by Postgres, so the COPY succeeds and the tickets are wrong.
    """
    from odoo18_ee2ce.config import should_skip, is_enterprise_data

    assert should_skip("helpdesk_ticket") is True
    # And it must not simply vanish: skipped here means exported there.
    assert is_enterprise_data("helpdesk_ticket", in_target=True) is True
    assert is_enterprise_data("helpdesk_ticket", in_target=False) is True

"""Tables to skip during the import.

These are managed by Odoo module installation (XML/CSV data files) or are
Enterprise-only with no Community equivalent. Importing the Enterprise
versions causes endless metadata conflicts; the freshly initialized
Community database already has correct versions.
"""

SKIP_TABLES = {
    # ── Odoo core framework ──
    "ir_module_module", "ir_module_module_dependency", "ir_module_module_exclusion",
    "ir_module_category",
    "ir_model", "ir_model_fields", "ir_model_constraint", "ir_model_relation",
    "ir_model_fields_selection", "ir_model_fields_group_rel",
    "ir_model_data",
    "ir_ui_view", "ir_ui_view_custom", "ir_ui_menu",
    "ir_act_window", "ir_act_window_view", "ir_act_window_group_rel",
    "ir_act_server", "ir_act_report_xml", "ir_act_url",
    "ir_actions", "ir_server_object_lines",
    "ir_rule", "ir_model_access",
    "ir_config_parameter", "ir_default",
    "ir_sequence", "ir_sequence_date_range",
    "ir_cron",
    "ir_logging", "ir_mail_server", "ir_asset",
    "ir_exports", "ir_exports_line", "ir_filters", "ir_property",
    "ir_translation",
    # ── Security groups (module-managed) ──
    "res_groups", "res_groups_implied_rel", "res_groups_users_rel",
    "res_config", "res_config_settings",
    # ── Reference data (seeded by base module CSVs) ──
    "res_country", "res_country_state", "res_country_group",
    "res_country_res_country_group_rel",
    "res_currency", "res_lang",
    "uom_uom", "uom_category",
    # ── Module-managed reference/config data ──
    "module_country",
    "payment_method", "payment_provider",
    "payment_method_payment_provider_rel",
    "payment_method_res_country_rel", "payment_method_res_currency_rel",
    "payment_currency_rel",
    "rule_group_rel", "res_groups_report_rel", "res_groups_spreadsheet_dashboard_rel",
    "mail_template", "mail_template_preview", "mail_template_reset",
    "mail_template_ir_actions_report_rel",
    "mail_message_subtype",
    "mail_alias", "mail_alias_domain",
    "report_layout", "report_paperformat",
    "bus_bus", "bus_presence",
    "fetchmail_server",
    "web_tour", "web_tour_step", "web_tour_tour",
    "base_import_mapping", "base_import_tests_models_char",
    "saas_trial_category", "saas_trial_template",
    "digest_digest", "digest_tip",
    "gamification_badge", "gamification_goal_definition", "gamification_challenge",
    "gamification_goal", "gamification_badge_user",
    "gamification_challenge_line", "gamification_challenge_users_rel",
    "gamification_karma_rank", "gamification_karma_tracking",
    "onboarding_onboarding", "onboarding_onboarding_step",
    "onboarding_progress", "onboarding_progress_step",
    "onboarding_onboarding_onboarding_onboarding_step_rel",
    "onboarding_progress_onboarding_progress_step_rel",
    "website", "website_menu", "website_page",
    "theme_ir_ui_view", "theme_ir_asset", "theme_website_menu", "theme_website_page",
    "spreadsheet_dashboard", "spreadsheet_dashboard_group",
    "spreadsheet_collaborative_revision", "spreadsheet_cell_thread",
    "crm_iap_lead_industry", "crm_iap_lead_role", "crm_iap_lead_seniority",
    "crm_lead_scoring_frequency", "crm_lead_scoring_frequency_field",
    "crm_recurring_plan",
    "account_incoterms", "decimal_precision", "sms_template",
    "hr_contract_type", "hr_departure_reason", "hr_resume_line_type",
    "hr_skill", "hr_skill_level", "hr_skill_type",
    "website_configurator_feature", "website_snippet_filter", "website_lang_rel",
}

# Prefix-based skip for Enterprise-only module tables that have no Community equivalent
SKIP_PREFIXES = (
    "saas_", "documents_", "sign_", "planning_", "social_",
    "marketing_automation_", "knowledge_", "studio_",
    "web_gantt_", "web_grid_",
    "appointment_", "helpdesk_sla",
    "sale_subscription_", "project_forecast",
    "account_asset", "account_report", "account_accountant",
    "account_consolidation", "account_avatax",
    "account_bank_statement_extract", "account_debit_note",
    "account_extract", "account_invoice_extract", "account_loans",
    "account_online_", "account_predictive",
    "timer_", "voip_", "whatsapp_", "pos_",
)


def should_skip(table_name, extra_skip=None, extra_prefixes=None):
    """Return True if this table should be skipped during the import.

    Args:
        table_name: PostgreSQL table name from the dump.
        extra_skip: Additional set of exact table names to skip (override).
        extra_prefixes: Additional tuple of prefixes to skip (override).
    """
    if table_name in SKIP_TABLES:
        return True
    if extra_skip and table_name in extra_skip:
        return True
    for prefix in SKIP_PREFIXES:
        if table_name.startswith(prefix):
            return True
    if extra_prefixes:
        for prefix in extra_prefixes:
            if table_name.startswith(prefix):
                return True
    # Skip all ir_* except ir_attachment (needed for filestore references)
    if table_name.startswith("ir_") and table_name != "ir_attachment":
        return True
    return False

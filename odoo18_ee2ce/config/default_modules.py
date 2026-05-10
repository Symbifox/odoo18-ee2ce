"""Default module set installed in the fresh Community database.

This list covers the major functional areas common to most Odoo deployments.
Module dependencies auto-install. Override via `--modules` to suit your
specific install.

Notable substitutions vs Odoo Enterprise:
  - `helpdesk_mgmt` (OCA) replaces Enterprise `helpdesk`
  - No replacement for: documents, sign, planning, knowledge, marketing_automation,
    sale_subscription (data from these modules will be skipped on import)
"""

DEFAULT_MODULES = ",".join([
    "base",
    "account",
    "contacts",
    "crm",
    "project",
    "sale",
    "sale_management",
    "hr",
    "hr_timesheet",
    "website",
    "website_blog",
    "mass_mailing",
    "calendar",
    "helpdesk_mgmt",
    "survey",
    "product",
])

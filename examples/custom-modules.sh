#!/bin/bash
# Custom modules example — install stock + manufacturing on top of the defaults
# and supply your own NOT_NULL_FIXUPS for some custom modules.
#
# This is the typical invocation when your Odoo install includes manufacturing,
# inventory management, or industry-specific OCA modules.

set -e

DB_PASSWORD=mypass odoo18-ee2ce \
    --dump      /tmp/enterprise/dump.sql \
    --filestore /tmp/enterprise/filestore/source-db-name \
    --target-db my-community-db \
    --db-container my-db \
    --odoo-container my-odoo \
    --db-user odoo \
    --modules base,account,contacts,crm,project,sale,sale_management,hr,hr_timesheet,website,website_blog,mass_mailing,calendar,helpdesk_mgmt,survey,product,stock,purchase,mrp,account_invoice_extract,industry_fsm \
    --not-null-fixups ./my-fixups.json \
    --skip-tables-extra ./my-skip.txt

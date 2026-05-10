#!/bin/bash
# Basic example — minimal invocation with default modules and defaults.
#
# Assumes:
#   - Odoo 18 CE container `my-odoo` is running
#   - PostgreSQL 15+ container `my-db` is running
#   - DB user `odoo` with password in env var DB_PASSWORD
#   - Enterprise SaaS dump extracted to /tmp/enterprise/

set -e

DB_PASSWORD=mypass odoo18-ee2ce \
    --dump      /tmp/enterprise/dump.sql \
    --filestore /tmp/enterprise/filestore/source-db-name \
    --target-db my-community-db \
    --db-container  my-db \
    --odoo-container my-odoo \
    --db-user   odoo

# After completion:
#   1. Edit your odoo.conf:    dbfilter = ^my-community-db$
#   2. docker restart my-odoo
#   3. Visit http://localhost:8069/web
#   4. Login with the Enterprise admin credentials (password is preserved)

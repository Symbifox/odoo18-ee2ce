from odoo18_ee2ce.config.skip_tables import SKIP_TABLES, SKIP_PREFIXES, should_skip
from odoo18_ee2ce.config.not_null_fixups import NOT_NULL_FIXUPS
from odoo18_ee2ce.config.default_modules import DEFAULT_MODULES

__all__ = [
    "SKIP_TABLES",
    "SKIP_PREFIXES",
    "should_skip",
    "NOT_NULL_FIXUPS",
    "DEFAULT_MODULES",
]

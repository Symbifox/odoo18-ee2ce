"""Post-import neutralization: disable outbound mail, reset URLs, regen UUID."""


NEUTRALIZE_STATEMENTS = [
    "UPDATE ir_mail_server SET active = false",
    "UPDATE ir_config_parameter SET value = 'http://localhost:8069' "
    "WHERE key = 'web.base.url'",
    "UPDATE ir_config_parameter SET value = 'invalid.local' "
    "WHERE key = 'mail.catchall.domain'",
    "UPDATE ir_cron SET active = false WHERE ir_actions_server_id IN "
    "(SELECT id FROM ir_act_server WHERE model_name IN "
    "('mail.mail','mail.message','fetchmail.server','bus.presence'))",
    "UPDATE ir_config_parameter SET value = gen_random_uuid()::text "
    "WHERE key = 'database.uuid'",
    "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%'",
    # Ensure mail_alias_domain has at least one entry (needed for message_post)
    "INSERT INTO mail_alias_domain "
    "(id, sequence, create_uid, write_uid, name, bounce_alias, catchall_alias, "
    " default_from, create_date, write_date) "
    "SELECT 1, 10, 2, 2, 'localhost', 'bounce', 'catchall', 'notifications', "
    "       now(), now() "
    "WHERE NOT EXISTS (SELECT 1 FROM mail_alias_domain WHERE id = 1)",
]


def neutralize(conn, extra_statements=None):
    """Run the neutralization statements. Failures on individual statements
    are tolerated so a missing table (e.g. mail_alias_domain on a minimal
    install) does not abort the rest.
    """
    print("\n  Neutralizing database...")
    statements = list(NEUTRALIZE_STATEMENTS)
    if extra_statements:
        statements.extend(extra_statements)
    for sql in statements:
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        except Exception:
            conn.rollback()
    print("  Done")

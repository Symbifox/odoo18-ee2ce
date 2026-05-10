"""Database credential loading and connection helpers."""

import os
import psycopg2


def load_db_creds(args):
    """Build DB credentials from CLI args, env vars, and .env file."""
    creds = {
        "host": args.db_host,
        "port": args.db_port,
        "user": args.db_user,
        "password": args.db_password or "",
    }
    # Try .env file for password if not provided
    if not creds["password"]:
        for env_dir in [os.getcwd(), os.path.join(os.getcwd(), "..")]:
            env_file = os.path.join(env_dir, ".env")
            if os.path.exists(env_file):
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DB_PASSWORD=") or line.startswith("POSTGRES_PASSWORD="):
                            creds["password"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
                if creds["password"]:
                    break
    # Env var overrides
    if os.environ.get("PGPASSWORD"):
        creds["password"] = os.environ["PGPASSWORD"]
    if os.environ.get("DB_PASSWORD"):
        creds["password"] = os.environ["DB_PASSWORD"]
    return creds


def connect(creds, dbname):
    """Open a psycopg2 connection to the named database."""
    dsn = (
        f"host={creds['host']} port={creds['port']} "
        f"user={creds['user']} password={creds['password']} dbname={dbname}"
    )
    return psycopg2.connect(dsn)

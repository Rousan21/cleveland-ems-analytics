"""Read-only readiness check for Render + Neon deployments.

Run from webapp directory: python check_setup.py
Does not print the database URL (which contains a password).
"""
import os
from sqlalchemy import text
from db import engine, init_database


def main():
    configured = bool(os.environ.get("EMS_DATABASE_URL"))
    print("External EMS_DATABASE_URL:", "configured" if configured else "not set (local SQLite default)")
    print("Database type:", engine.dialect.name)
    if not configured:
        print("NOTE: Hosted Render service requires a persistent PostgreSQL URL.")
    with engine.connect() as connection:
        print("Database connectivity:", "ok" if connection.scalar(text("SELECT 1")) == 1 else "FAILED")
    init_database()
    with engine.connect() as connection:
        print("Imported EMS records:", connection.scalar(text("SELECT COUNT(*) FROM ems_calls_v2")))
    print("Ready for read-only web requests. Check importer schedule separately.")


if __name__ == "__main__":
    main()

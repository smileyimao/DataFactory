#!/usr/bin/env python3
# scripts/db/migrate_sqlite_to_pg.py — one-shot SQLite → PostgreSQL data migration
"""
Reads every row from each table in the SQLite factory_admin.db and inserts
them into the PostgreSQL database specified by DATABASE_URL.

Idempotent: rows that already exist (same primary key) are skipped via
ON CONFLICT DO NOTHING, so it is safe to run multiple times.

Usage:
  DATABASE_URL=postgresql://datafactory:datafactory@localhost:5432/datafactory \
    python scripts/db/migrate_sqlite_to_pg.py

Requirements:
  - PostgreSQL tables must already exist (run db_tools.init_db first)
  - psycopg2-binary must be installed
"""
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

from config import config_loader

# Tables to migrate (in dependency order)
_TABLES = [
    "production_history",
    "batch_metrics",
    "batch_lineage",
    "label_import",
    "model_train",
]


def _get_columns(cur, table: str):
    cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def migrate(sqlite_path: str, pg_url: str) -> None:
    print(f"\n  Source (SQLite): {sqlite_path}")
    print(f"  Target (PG):     {pg_url}\n")

    if not os.path.isfile(sqlite_path):
        print(f"  ❌ SQLite file not found: {sqlite_path}")
        sys.exit(1)

    import psycopg2
    sq_conn = sqlite3.connect(sqlite_path)
    sq_conn.row_factory = sqlite3.Row
    sq_cur = sq_conn.cursor()

    pg_conn = psycopg2.connect(pg_url)
    pg_conn.autocommit = False
    pg_cur = pg_conn.cursor()

    for table in _TABLES:
        # Check table exists in SQLite
        sq_cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if not sq_cur.fetchone():
            print(f"  [skip] {table} — not in SQLite")
            continue

        cols = _get_columns(sq_cur, table)
        if not cols:
            print(f"  [skip] {table} — no columns")
            continue

        sq_cur.execute(f"SELECT COUNT(*) FROM {table}")
        sq_count = sq_cur.fetchone()[0]

        sq_cur.execute(f"SELECT {', '.join(cols)} FROM {table}")
        rows = sq_cur.fetchall()

        placeholders = ", ".join(["%s"] * len(cols))
        cols_str = ", ".join(cols)
        insert_sql = (
            f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) "
            f"ON CONFLICT DO NOTHING"
        )

        inserted = 0
        for row in rows:
            try:
                pg_cur.execute(insert_sql, tuple(row))
                inserted += pg_cur.rowcount
            except Exception as e:
                pg_conn.rollback()
                print(f"  ⚠️  {table}: row error — {e}")
                pg_conn.autocommit = False
                continue

        pg_conn.commit()

        pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
        pg_count = pg_cur.fetchone()[0]

        print(
            f"  {table:30s}  SQLite={sq_count:5d}  inserted={inserted:5d}  "
            f"PG total={pg_count:5d}"
        )

    sq_conn.close()
    pg_cur.close()
    pg_conn.close()
    print("\n  Migration complete.")


def main() -> None:
    config_loader.set_base_dir(BASE_DIR)
    cfg = config_loader.load_config()

    sqlite_path = cfg.get("paths", {}).get("db_file", "")
    if not sqlite_path:
        sqlite_path = os.path.join(BASE_DIR, "db", "factory_admin.db")

    pg_url = os.environ.get("DATABASE_URL", "").strip()
    if not pg_url:
        print("❌ DATABASE_URL environment variable is not set.")
        print("   Example: export DATABASE_URL=postgresql://datafactory:datafactory@localhost:5432/datafactory")
        sys.exit(1)

    if not pg_url.startswith(("postgresql://", "postgres://")):
        print(f"❌ DATABASE_URL does not look like a PostgreSQL URL: {pg_url}")
        sys.exit(1)

    migrate(sqlite_path, pg_url)


if __name__ == "__main__":
    main()

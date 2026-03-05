# db/db_connection.py — SQLite / PostgreSQL thin adapter
"""
Single place to swap database backends.  All other code imports this module
instead of sqlite3 or psycopg2 directly.

URL conventions
---------------
  PostgreSQL : postgresql://user:pass@host:port/dbname
  SQLite     : /absolute/path/to/file.db  OR  sqlite:///path/to/file.db

If the DATABASE_URL environment variable is set it always wins.
"""
import os
import sqlite3
from typing import Any, Dict, List


def get_db_url(cfg: Dict[str, Any], base_dir: str) -> str:
    """
    Resolve the database URL.
    Priority: DATABASE_URL env var > cfg paths.db_file > default sqlite path.
    """
    env_url = os.environ.get("DATABASE_URL", "").strip()
    if env_url:
        return env_url
    db_file = cfg.get("paths", {}).get("db_file", "")
    if db_file:
        return db_file
    return os.path.join(base_dir, "db", "factory_admin.db")


def is_postgres(url: str) -> bool:
    """Return True if *url* is a PostgreSQL connection string."""
    return url.startswith(("postgresql://", "postgres://"))


def connect(url: str):
    """
    Return a live database connection for the given URL.

    - postgresql:// or postgres://  → psycopg2 connection
    - everything else               → sqlite3 connection
      (strips sqlite:// / sqlite:/// prefix if present)
    """
    if is_postgres(url):
        import psycopg2  # noqa: F401 — optional dependency
        return psycopg2.connect(url)
    # SQLite: strip URI scheme if present
    path = url
    for prefix in ("sqlite:///", "sqlite://"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    return sqlite3.connect(path)


def ph(url: str) -> str:
    """Return the SQL parameter placeholder for *url*: '%s' (PG) or '?' (SQLite)."""
    return "%s" if is_postgres(url) else "?"


def upsert_sql(table: str, pk: str, columns: List[str], url: str) -> str:
    """
    Build a dialect-appropriate upsert statement.

    *columns* should include *pk* as well as all non-PK columns, in the
    intended insertion order.

    SQLite :  INSERT OR REPLACE INTO t (pk, a, b) VALUES (?, ?, ?)
    PG     :  INSERT INTO t (pk, a, b) VALUES (%s, %s, %s)
              ON CONFLICT (pk) DO UPDATE SET a=EXCLUDED.a, b=EXCLUDED.b
    """
    # Ensure pk comes first, dedup
    all_cols = [pk] + [c for c in columns if c != pk]
    p = ph(url)
    placeholders = ", ".join([p] * len(all_cols))
    cols_str = ", ".join(all_cols)

    if is_postgres(url):
        non_pk = [c for c in all_cols if c != pk]
        set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in non_pk)
        return (
            f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) "
            f"ON CONFLICT ({pk}) DO UPDATE SET {set_clause}"
        )
    return f"INSERT OR REPLACE INTO {table} ({cols_str}) VALUES ({placeholders})"

# db/db_connection.py — SQLite / PostgreSQL thin adapter
"""
Single place to swap database backends.  All other code imports this module
instead of sqlite3 or psycopg2 directly.

URL conventions
---------------
  PostgreSQL : postgresql://user:pass@host:port/dbname
  SQLite     : /absolute/path/to/file.db  OR  sqlite:///path/to/file.db

If the DATABASE_URL environment variable is set it always wins.

PostgreSQL 连接池
-----------------
PG 模式下使用 ThreadedConnectionPool（psycopg2），避免每次 connect() 都建立 TCP 握手。
connect() 返回的 _PooledConn 在调用 .close() 时将连接归还池而非真正关闭，
因此所有现有 `conn = connect(url) … conn.close()` 调用无需修改。

池大小通过环境变量控制：
  PG_POOL_MIN  （默认 1）
  PG_POOL_MAX  （默认 10）
"""
import os
import sqlite3
import threading
from typing import Any, Dict, List

# -- PostgreSQL 连接池（懒初始化）--------------------------------------------
_pg_pool = None
_pg_pool_url: str = ""
_pg_pool_lock = threading.Lock()
_PG_MIN_CONN = int(os.environ.get("PG_POOL_MIN", "1"))
_PG_MAX_CONN = int(os.environ.get("PG_POOL_MAX", "10"))


class _PooledConn:
    """
    psycopg2 连接的轻量代理：将 .close() 重定向为归还连接池，
    其余方法/属性透传到底层连接。
    """
    __slots__ = ("_pool", "_conn")

    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn

    # 透传所有未在 __slots__ 中显式定义的属性（如 autocommit、notices …）
    def __getattr__(self, name):
        return getattr(self._conn, name)

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        """将连接归还池（不真正断开）。"""
        try:
            self._pool.putconn(self._conn)
        except Exception:
            # 池已关闭时安全降级：直接关闭底层连接
            try:
                self._conn.close()
            except Exception:
                pass


def _get_pg_pool(url: str):
    """返回（懒初始化）模块级 ThreadedConnectionPool。"""
    global _pg_pool, _pg_pool_url
    if _pg_pool is None or _pg_pool_url != url:
        with _pg_pool_lock:
            if _pg_pool is None or _pg_pool_url != url:
                import psycopg2.pool  # noqa: F401
                _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                    _PG_MIN_CONN, _PG_MAX_CONN, url
                )
                _pg_pool_url = url
    return _pg_pool


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

    - postgresql:// or postgres://  → _PooledConn（从 ThreadedConnectionPool 取）
    - everything else               → sqlite3 connection
      (strips sqlite:// / sqlite:/// prefix if present)
    """
    if is_postgres(url):
        pool = _get_pg_pool(url)
        conn = pool.getconn()
        return _PooledConn(pool, conn)
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

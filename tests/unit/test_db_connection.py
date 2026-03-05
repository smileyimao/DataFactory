# tests/unit/test_db_connection.py — db_connection thin adapter 单元测试
"""覆盖 is_postgres / ph / upsert_sql / get_db_url / connect 五个函数。"""
import os
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

import pytest

import db.db_connection as dbc

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# is_postgres
# ---------------------------------------------------------------------------

class TestIsPostgres:
    def test_postgresql_scheme(self):
        assert dbc.is_postgres("postgresql://user:pass@localhost:5432/db") is True

    def test_postgres_short_scheme(self):
        assert dbc.is_postgres("postgres://user:pass@localhost/db") is True

    def test_sqlite_path(self):
        assert dbc.is_postgres("/tmp/factory.db") is False

    def test_sqlite_uri(self):
        assert dbc.is_postgres("sqlite:///tmp/factory.db") is False

    def test_empty_string(self):
        assert dbc.is_postgres("") is False


# ---------------------------------------------------------------------------
# ph
# ---------------------------------------------------------------------------

class TestPh:
    def test_pg_placeholder(self):
        assert dbc.ph("postgresql://localhost/db") == "%s"

    def test_sqlite_placeholder(self):
        assert dbc.ph("/tmp/factory.db") == "?"

    def test_sqlite_uri_placeholder(self):
        assert dbc.ph("sqlite:///tmp/factory.db") == "?"


# ---------------------------------------------------------------------------
# upsert_sql
# ---------------------------------------------------------------------------

SQLITE_URL = "/tmp/test.db"
PG_URL = "postgresql://user:pass@localhost:5432/db"


class TestUpsertSql:
    def test_sqlite_syntax(self):
        sql = dbc.upsert_sql("t", "id", ["id", "name", "val"], SQLITE_URL)
        assert sql.startswith("INSERT OR REPLACE INTO t")
        assert "?" in sql
        assert "ON CONFLICT" not in sql

    def test_pg_syntax(self):
        sql = dbc.upsert_sql("t", "id", ["id", "name", "val"], PG_URL)
        assert sql.startswith("INSERT INTO t")
        assert "%s" in sql
        assert "ON CONFLICT (id) DO UPDATE SET" in sql
        assert "name=EXCLUDED.name" in sql
        assert "val=EXCLUDED.val" in sql

    def test_pk_not_in_set_clause(self):
        """PG upsert 的 SET 子句不能包含主键自身。"""
        sql = dbc.upsert_sql("t", "id", ["id", "a"], PG_URL)
        set_part = sql.split("DO UPDATE SET")[1]
        assert "id=EXCLUDED" not in set_part

    def test_pk_dedup_when_repeated(self):
        """columns 中重复传入 pk 时不应出现重复列。"""
        sql = dbc.upsert_sql("t", "id", ["id", "id", "name"], SQLITE_URL)
        cols_part = sql[sql.index("("):sql.index(")") + 1]
        assert cols_part.count("id") == 1

    def test_pk_first_in_columns(self):
        """pk 总是排在列列表首位。"""
        sql = dbc.upsert_sql("t", "pk_col", ["a", "b", "pk_col"], SQLITE_URL)
        cols_part = sql.split("VALUES")[0]
        assert cols_part.index("pk_col") < cols_part.index("a")

    def test_placeholder_count_matches_columns(self):
        """VALUES 占位符数量 == 列数量。"""
        cols = ["id", "a", "b", "c"]
        sql = dbc.upsert_sql("t", "id", cols, SQLITE_URL)
        placeholders = sql.split("VALUES (")[1].rstrip(")").split(", ")
        assert len(placeholders) == len(cols)


# ---------------------------------------------------------------------------
# get_db_url
# ---------------------------------------------------------------------------

class TestGetDbUrl:
    def test_env_var_wins(self):
        """DATABASE_URL 环境变量优先级最高。"""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://env/db"}):
            url = dbc.get_db_url({}, "/base")
        assert url == "postgresql://env/db"

    def test_cfg_db_file_second(self):
        """无 env var 时取 cfg paths.db_file。"""
        cfg = {"paths": {"db_file": "/data/factory.db"}}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            url = dbc.get_db_url(cfg, "/base")
        assert url == "/data/factory.db"

    def test_default_fallback(self):
        """两者都没有时回落到 base_dir/db/factory_admin.db。"""
        os.environ.pop("DATABASE_URL", None)
        url = dbc.get_db_url({}, "/base")
        assert url == os.path.join("/base", "db", "factory_admin.db")

    def test_env_var_whitespace_stripped(self):
        """env var 前后空白被去掉后若为空，仍走 fallback。"""
        with patch.dict(os.environ, {"DATABASE_URL": "   "}):
            url = dbc.get_db_url({}, "/base")
        assert url == os.path.join("/base", "db", "factory_admin.db")


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

class TestConnect:
    def test_sqlite_returns_connection(self):
        """SQLite 路径返回真实可用的 sqlite3.Connection。"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = dbc.connect(path)
            assert isinstance(conn, sqlite3.Connection)
            conn.close()
        finally:
            os.unlink(path)

    def test_sqlite_uri_prefix_stripped(self):
        """sqlite:/// 前缀被正确剥离后能打开文件。"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = dbc.connect(f"sqlite:///{path}")
            assert isinstance(conn, sqlite3.Connection)
            conn.close()
        finally:
            os.unlink(path)

    def test_pg_delegates_to_psycopg2(self):
        """PostgreSQL URL 时通过连接池取连接，不实际建 TCP 连接。"""
        import importlib
        import db.db_connection as dbc2

        mock_raw_conn = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_raw_conn

        mock_psycopg2 = MagicMock()
        mock_psycopg2.pool.ThreadedConnectionPool.return_value = mock_pool

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2, "psycopg2.pool": mock_psycopg2.pool}):
            importlib.reload(dbc2)
            conn = dbc2.connect("postgresql://user:pass@localhost/db")

        # conn 是 _PooledConn 包装器，底层持有 mock_raw_conn
        assert conn._conn is mock_raw_conn
        mock_pool.getconn.assert_called_once()

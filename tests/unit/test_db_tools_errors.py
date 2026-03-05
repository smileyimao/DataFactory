# tests/unit/test_db_tools_errors.py
"""db_tools：DB 异常时返回 False/None，不崩溃。"""
import sqlite3
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.unit


def test_init_db_returns_false_on_sqlite_error():
    """init_db 在 sqlite3.Error 时返回 False。"""
    from db import db_tools

    with patch("db.db_connection.sqlite3.connect", side_effect=sqlite3.OperationalError("Disk full")):
        result = db_tools.init_db("/nonexistent/path/db.sqlite")

    assert result is False


def test_get_reproduce_info_returns_none_on_db_error():
    """get_reproduce_info 在 DB 异常时返回 None。"""
    from db import db_tools

    with patch("db.db_connection.sqlite3.connect", side_effect=sqlite3.OperationalError("Connection refused")):
        result = db_tools.get_reproduce_info("/tmp/db.sqlite", "abc123")

    assert result is None


def test_init_db_succeeds_with_valid_path(temp_dir):
    """init_db 在合法路径下返回 True。"""
    import os
    from db import db_tools

    db_path = os.path.join(temp_dir, "test.db")
    result = db_tools.init_db(db_path)
    assert result is True
    assert os.path.isfile(db_path)

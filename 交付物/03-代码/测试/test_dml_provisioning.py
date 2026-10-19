# -*- coding: utf-8 -*-
"""DML-only 账号下的建库／建表降级与错误提示（独立审查 2026-10-19）。

回归背景：切到 `ashare_app`（仅 DML）后，`db.ensure_database()`／`init_schema()`
在库表已存在时仍无条件执行 DDL，导致 `tools/import_data.py` 抛裸 1044/1142。
修复口径：库／六表已存在 → 完全不发 DDL；确实缺库表且无权限 → SystemExit 给出
迁移账号处置提示，且不回显账号名／原始消息中的凭据碎片。
"""

from __future__ import annotations

import os
import sys

import pymysql
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bootstrap  # noqa: E402

db = _bootstrap.load_backend("db")
config = _bootstrap.component_config("后端")


def test_ensure_database_skips_ddl_when_database_exists(monkeypatch):
    monkeypatch.setattr(db, "database_exists", lambda: True)

    def _must_not_connect(*_a, **_k):
        raise AssertionError("库已存在时不得再执行 CREATE DATABASE（DML-only 账号会 1044）")

    monkeypatch.setattr(db, "connect", _must_not_connect)
    assert db.ensure_database() == config.db_database()


def test_init_schema_skips_ddl_when_all_tables_exist(monkeypatch):
    monkeypatch.setattr(db, "schema_ready", lambda: True)

    def _must_not_connect():
        raise AssertionError("六表已存在时不得再执行 CREATE TABLE（DML-only 账号会 1142）")

    monkeypatch.setattr(db, "get_conn", _must_not_connect)
    assert db.init_schema() == 0


def test_schema_ready_requires_all_six_tables(monkeypatch):
    rows = [{"name": t.upper()} for t in config.TABLES]
    monkeypatch.setattr(db, "query", lambda *_a, **_k: rows)
    assert db.schema_ready() is True

    monkeypatch.setattr(db, "query", lambda *_a, **_k: rows[:-1])
    assert db.schema_ready() is False


def test_ddl_privilege_error_is_actionable_and_does_not_echo_account():
    exc = pymysql.err.OperationalError(
        1142, "CREATE command denied to user 'ashare_app'@'localhost' for table 'document'")
    err = db._ddl_privilege_error(exc, "CREATE TABLE")
    assert isinstance(err, SystemExit)
    message = str(err)
    assert "1142" in message
    assert "迁移账号" in message
    assert "ASHARE_MYSQL_USER" in message
    # 原生错误里的 `user '…'@'…'` 不应被回显到终端／日志
    assert "ashare_app" not in message
    assert "@'localhost'" not in message


def test_init_schema_maps_denied_ddl_to_systemexit(monkeypatch, tmp_path):
    ddl = tmp_path / "schema.sql"
    ddl.write_text("CREATE TABLE IF NOT EXISTS `x` (`id` INT);\n", encoding="utf-8")

    class _Cursor:
        def execute(self, _stmt):
            raise pymysql.err.OperationalError(1142, "CREATE command denied")

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cursor()

        def rollback(self):
            pass

        def commit(self):
            pass

    monkeypatch.setattr(db, "schema_ready", lambda: False)
    monkeypatch.setattr(db, "get_conn", lambda: _Conn())
    with pytest.raises(SystemExit) as caught:
        db.init_schema(str(ddl))
    assert "1142" in str(caught.value)
